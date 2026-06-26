# dlc/darbuka/darbuka_engine.py
import os
import numpy as np
import taichi as ti
import scipy.io.wavfile as wav
from scipy.signal import lfilter, butter, fftconvolve
import pyroomacoustics as pra

from engine.grid_builder import build_heterogeneous_grids
from engine.tactile import generate_tactile_profile
from engine.shell_texture import apply_dynamic_shell_texture
from config.materials import MATERIAL_PHYSICS
from config.instruments import PERCUSSION_PRESETS
from engine.core_taichi import generate_fdtd_ir

def get_effective_properties(mat: dict) -> dict:
    density = mat.get("density", 1.0)
    E_long = mat.get("E_long", 10.0)
    E_trans = mat.get("E_trans", mat.get("E_long", 10.0))
    loss = mat.get("loss_factor", 0.02)
    visco = mat.get("visco_gamma", 1e-5)
    poisson = mat.get("poisson", 0.3)
    
    tactile = mat.get("tactile_profile", {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0}).copy()
    
    inclusions = mat.get("inclusions", [])
    total_inc_ratio = sum(float(inc.get("density_ratio", 0.0)) for inc in inclusions)
    base_ratio = max(0.01, 1.0 - total_inc_ratio)
    
    for inc in inclusions:
        inc_mat = inc["material"]
        if isinstance(inc_mat, str):
            inc_mat = MATERIAL_PHYSICS.get(inc_mat, {})
        
        ratio = float(inc.get("density_ratio", 0.1))
        density = density * (1.0 - ratio) + inc_mat.get("density", density) * ratio
        E_long = E_long * (1.0 - ratio) + inc_mat.get("E_long", E_long) * ratio
        E_trans = E_trans * (1.0 - ratio) + inc_mat.get("E_trans", inc_mat.get("E_long", E_trans)) * ratio
        loss = loss * (1.0 - ratio) + inc_mat.get("loss_factor", loss) * ratio
        visco = visco * (1.0 - ratio) + inc_mat.get("visco_gamma", visco) * ratio
        
        inc_tactile = inc_mat.get("tactile_profile", {})
        for key in tactile:
            tactile[key] = tactile.get(key, 0.0) * (1-ratio) + inc_tactile.get(key, 0.0) * ratio
            
    effective_mat = mat.copy()
    effective_mat.update({
        "density": density, "E_long": E_long, "E_trans": E_trans,
        "loss_factor": loss, "visco_gamma": visco, "poisson": poisson,
        "tactile_profile": tactile
    })
    return effective_mat

def note_to_frequency(note_name: str) -> float:
    """Перевод ноты (например, D3) в точную частоту для тюнинга."""
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    name = note_name[:-1]
    octave = int(note_name[-1])
    if name.endswith('b'):
        flat_to_sharp = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}
        name = flat_to_sharp.get(name, name)
    key_number = notes.index(name) + (octave + 1) * 12
    return 440.0 * (2.0 ** ((key_number - 69) / 12.0))

N_MAX = 512
N_REF = 128
_BODY_IR_CACHE = {}

def init_taichi_headless():
    try:
        if ti.lang.impl.get_runtime().prog is not None: return
    except Exception: pass
    try:
        ti.init(arch=ti.gpu, device_memory_GB=1.5, log_level=ti.WARN)
        print("✅ [DARBUKA] GPU FDTD инициализирован.")
    except Exception:
        ti.init(arch=ti.cpu, log_level=ti.WARN)

init_taichi_headless()

# === ПОЛЯ ДЛЯ ОДНОЙ МЕМБРАНЫ (Дарбука) ===
p = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_past = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_future = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
mask = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

stat_vol = ti.field(dtype=ti.f32, shape=())
stat_strain = ti.field(dtype=ti.f32, shape=())

c_sq_x_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
c_sq_y_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
loss_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
visco_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

@ti.kernel
def init_darbuka_fields(N: ti.i32):
    stat_vol[None] = 0.0
    stat_strain[None] = 0.0
    for i, j in ti.ndrange(N, N):
        p[i, j] = 0.0
        p_past[i, j] = 0.0
        p_future[i, j] = 0.0

@ti.kernel
def compute_darbuka_stats(N: ti.i32):
    stat_vol[None] = 0.0
    stat_strain[None] = 0.0
    for i, j in ti.ndrange(N, N):
        stat_vol[None] += p[i, j] * mask[i, j]
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask[i, j] > 0.5:
            dx = p[i+1, j] - p[i, j]
            dy = p[i, j+1] - p[i, j]
            stat_strain[None] += dx*dx + dy*dy

@ti.kernel
def step_darbuka_fdtd(
    N: ti.i32,
    coupling_k: ti.f32, vol: ti.f32, vol_delayed: ti.f32,
    strike_x: ti.i32, strike_y: ti.i32, strike_val: ti.f32, radius: ti.f32,
    bend: ti.f32, strain: ti.f32,
    damp_val: ti.f32, damp_cov: ti.i32
):
    p_air = -coupling_k * (vol + vol_delayed * 0.5) * 0.02
    safe_r = ti.max(radius, 0.001)

    for i, j in ti.ndrange(N, N):
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask[i, j] > 0.5:
            base_cx = c_sq_x_field[i, j]
            base_cy = c_sq_y_field[i, j]
            local_loss = loss_field[i, j]
            local_visco = visco_field[i, j]
            
            dyn_c_x = ti.min(base_cx * (1.0 + bend * strain * 10000.0), 0.24)
            dyn_c_y = ti.min(base_cy * (1.0 + bend * strain * 10000.0), 0.24)

            lap_curr_x = p[i-1, j] + p[i+1, j] - 2.0 * p[i, j]
            lap_curr_y = p[i, j-1] + p[i, j+1] - 2.0 * p[i, j]
            lap_past_x = p_past[i-1, j] + p_past[i+1, j] - 2.0 * p_past[i, j]
            lap_past_y = p_past[i, j-1] + p_past[i, j+1] - 2.0 * p_past[i, j]
            
            lap_curr = dyn_c_x * lap_curr_x + dyn_c_y * lap_curr_y
            lap_past = dyn_c_x * lap_past_x + dyn_c_y * lap_past_y
            
            force = lap_curr + local_visco * (lap_curr - lap_past)
            force += p_air * mask[i, j]
            
            if radius > 0.1:
                dist = ti.cast((i - strike_x)**2 + (j - strike_y)**2, ti.f32)
                if dist < radius:
                    force += strike_val * ti.exp(-dist / (safe_r * 0.3))
                    
            total_loss = local_loss
            if i < damp_cov:
                total_loss += damp_val
                
            p_future[i, j] = (2.0 * p[i, j] - p_past[i, j] * (1.0 - total_loss) + force) / (1.0 + total_loss)
        else:
            p_future[i, j] = 0.0

@ti.kernel
def apply_darbuka_tactile_forces(
    N: ti.i32, gran: ti.f32, brit: ti.f32, strike_force: ti.f32,
    slap_fric: ti.f32, strike_x: ti.i32, strike_y: ti.i32, r_strike: ti.f32
):
    limit = 75 + ti.cast(strike_force * 100.0, ti.i32)
    for idx in range(180):
        if idx < limit:
            i = ti.cast(ti.random() * N, ti.i32)
            j = ti.cast(ti.random() * N, ti.i32)
            if i > 0 and i < N-1 and j > 0 and j < N-1 and mask[i, j] > 0.5:
                strain_val = ti.abs(p[i, j] - p_past[i, j])
                if gran > 0.0 and strain_val > 0.00001:
                    if ti.random() < gran: p_future[i, j] += (ti.random() - 0.5) * gran * strain_val * 0.3
                if brit > 0.0 and strain_val > 0.002:
                    if ti.random() < brit * 0.1: 
                        p_future[i, j] += (ti.random() - 0.5) * brit * strain_val * 1.5
                        p_future[i, j] *= 0.90 

    # Трение ладони при артикуляции SLAP
    if slap_fric > 0.0 and r_strike > 0.1:
        for idx in range(150):
            i = ti.cast(ti.random() * N, ti.i32)
            j = ti.cast(ti.random() * N, ti.i32)
            if mask[i, j] > 0.5:
                dist = ti.cast((i - strike_x)**2 + (j - strike_y)**2, ti.f32)
                if dist < r_strike**2:
                    p_future[i, j] += (ti.random() - 0.5) * slap_fric * 0.04

@ti.kernel
def update_darbuka_fields(N: ti.i32):
    for i, j in ti.ndrange(N, N):
        p_past[i, j] = p[i, j]
        p[i, j] = p_future[i, j]

def apply_darbuka_shell(membrane_signal, fs, mat_properties, base_hz, articulation, strike_force):
    E_long = mat_properties.get("E_long", 70.0)
    density = mat_properties.get("density", 2.7)
    
    body_damping = 0.045
    loss = mat_properties.get("loss_factor", 0.001) + body_damping
    
    f_helmholtz = np.clip(base_hz * 0.45, 60.0, 110.0)
    mid_body_hz = np.clip(base_hz * 2.8, 300.0, 800.0)
    upper_body_hz = np.clip(base_hz * 4.5, 600.0, 1200.0)
    
    v_sound = np.sqrt((E_long * 1e9) / (density * 1000.0))
    metal_zing_1 = np.clip(v_sound * 0.12, 2500.0, 6000.0)
    metal_zing_2 = np.clip(v_sound * 0.22, 4500.0, 11000.0)
    metal_zing_3 = np.clip(v_sound * 0.35, 7000.0, 16000.0)

    freqs = [f_helmholtz, mid_body_hz, upper_body_hz, metal_zing_1, metal_zing_2, metal_zing_3]
    
    base_q = np.clip(1.0 / loss, 10.0, 45.0)
    is_metal = E_long > 30.0
    metal_q_boost = 2.5 if is_metal else 1.0
    
    q_factors = [
        base_q * 0.4,
        base_q * 0.2,
        base_q * 0.4,
        base_q * 1.2 * metal_q_boost,
        base_q * 1.5 * metal_q_boost,
        base_q * 1.8 * metal_q_boost
    ]
    
    shell_gain = 0.12
    mids_gain = 0.5 if is_metal else 1.2
    highs_gain = 1.6 if is_metal else 0.4
    
    gains = [
        0.85,
        shell_gain * mids_gain,
        shell_gain * 0.7 * mids_gain,
        shell_gain * 0.6 * highs_gain,
        shell_gain * 0.4 * highs_gain,
        shell_gain * 0.2 * highs_gain
    ]
    
    if articulation in ["tek", "ka"]:
        gains[0] *= 0.1
        gains[1] *= 0.2
        gains[2] *= 0.5
        gains[3] *= 2.5
        gains[4] *= 2.5
        gains[5] *= 2.5
    elif articulation == "slap":
        gains[0] *= 0.3
        gains[1] *= 0.5
        q_factors = [q * 0.4 for q in q_factors]
    elif articulation == "doum":
        gains[0] *= 1.2
        
    out = np.zeros_like(membrane_signal)
    for f, q, g in zip(freqs, q_factors, gains):
        if f < fs / 2.1:
            w0 = 2.0 * np.pi * f / fs
            alpha = np.sin(w0) / (2.0 * q)
            a0 = 1.0 + alpha
            b = [np.sin(w0) / (2.0 * a0), 0.0, -np.sin(w0) / (2.0 * a0)]
            a = [1.0, -2.0 * np.cos(w0) / a0, (1.0 - alpha) / a0]
            out += lfilter(b, a, membrane_signal) * g
            
    return out

def apply_darbuka_fat(sig, fs, articulation, strike_force, saturation=0.0):
    """Компрессия и сатурация (Meat & Fat)."""
    out = sig.copy()
    t_arr = np.arange(len(out)) / fs
    
    # Мощный ударный транзиент
    punch_env = 1.0 + 0.5 * np.exp(-t_arr / 0.015) * strike_force
    out *= punch_env
    
    # Allpass дисперсия для металлического щелчка
    if articulation in ["tek", "ka", "roll"]:
        out = lfilter([-0.5, 1.0], [1.0, -0.5], out)
        
    # Сатурация
    headroom = 0.4
    drive = 1.0 + (saturation * 0.2)
    out = np.tanh(out * headroom * drive) / (headroom * drive)
    
    return out

# --- ИМПУЛЬСНАЯ СВЁРТКА КУБКА (IR BODY) ---
def generate_air_column_ir(base_shell_hz, fs=44100, duration=0.4, articulation="doum"):
    t_arr = np.arange(int(fs * duration)) / fs
    air_ir = np.zeros_like(t_arr)
    freqs = [base_shell_hz, base_shell_hz * 2.0, base_shell_hz * 3.0]
    decay_times = [0.080, 0.035, 0.015] if articulation == "slap" else [0.060, 0.025, 0.010]
    amplitudes = [1.0, 0.5, 0.2]
    
    for f, tau, amp in zip(freqs, decay_times, amplitudes):
        if f < fs / 2.1:
            phase = np.random.uniform(0, 2 * np.pi)
            decay = np.exp(-t_arr / tau)
            air_ir += amp * decay * np.sin(2 * np.pi * f * t_arr + phase)
            
    reflections = [int(0.0015 * fs), int(0.0030 * fs), int(0.0045 * fs)]
    ref_gains = [0.35, 0.18, 0.08]
    for delay, gain in zip(reflections, ref_gains):
        if len(air_ir) > delay:
            air_ir[delay:] += air_ir[:-delay] * gain
            
    b, a = butter(2, 7500.0 / (fs / 2.0), btype='low')
    air_ir = lfilter(b, a, air_ir)
    if np.max(np.abs(air_ir)) > 0: air_ir /= np.max(np.abs(air_ir))
    return air_ir

def generate_body_ir(shell_mat_dict, base_shell_hz, fs=44100, duration=0.4, articulation="doum"):
    ir_instrument = PERCUSSION_PRESETS.get("darbuka_shell", PERCUSSION_PRESETS["tom_low"]).copy()
    ir_instrument['f0'] = base_shell_hz  
    
    exciter_impulse = np.zeros(int(fs * duration))
    pulse_len = int(0.002 * fs)
    noise = np.random.normal(0, 1.0, pulse_len)
    env = (1.0 - np.linspace(0, 1, pulse_len)) ** 2
    b, a = butter(2, 1000.0 / (fs / 2.0), btype='high')
    filtered_noise = lfilter(b, a, noise * env)
    
    if np.max(np.abs(filtered_noise)) > 0: filtered_noise /= np.max(np.abs(filtered_noise))
    exciter_impulse[0] = 0.7
    exciter_impulse[:pulse_len] += filtered_noise * 0.3
    exciter_impulse /= np.max(np.abs(exciter_impulse))

    body_ir_stereo = generate_fdtd_ir(
        inst_dict=ir_instrument,
        mat_dict=shell_mat_dict,
        sample_rate=fs,
        duration=duration,
        exciter_signal=exciter_impulse,
        is_stereo=False,
        strike_force=1.0,
        N_grid=128,
        show_gui=False
    )
    
    body_ir_mono = (body_ir_stereo[:, 0] + body_ir_stereo[:, 1]) * 0.5
    if np.max(np.abs(body_ir_mono)) > 0: body_ir_mono /= np.max(np.abs(body_ir_mono))
        
    target_len = len(body_ir_mono)
    air_ir = generate_air_column_ir(base_shell_hz, fs, target_len / fs, articulation=articulation)
    
    if len(air_ir) > target_len: air_ir = air_ir[:target_len]
    elif len(air_ir) < target_len: air_ir = np.pad(air_ir, (0, target_len - len(air_ir)))
    
    mixed_ir = 0.5 * body_ir_mono + 0.5 * air_ir
    if np.max(np.abs(mixed_ir)) > 0: mixed_ir /= np.max(np.abs(mixed_ir))
    return mixed_ir

def apply_body_convolution(input_signal, ir_signal, fs, mix=0.35):
    if mix == 0.0: return input_signal
    nyquist = fs / 2.0
    b, a = butter(4, 300.0 / nyquist, btype='high')
    ir_highpass = lfilter(b, a, ir_signal)
    ir_len = int(0.15 * fs)
    if len(ir_highpass) > ir_len:
        ir_faded = ir_highpass[:ir_len]
        ir_faded *= (np.linspace(1.0, 0.0, ir_len)**2)
    else: 
        ir_faded = ir_highpass
        
    if np.max(np.abs(ir_faded)) > 0: ir_faded /= np.max(np.abs(ir_faded))
    wet_signal = fftconvolve(input_signal, ir_faded, mode='full')
    wet_signal = wet_signal[:len(input_signal)]
    if np.max(np.abs(wet_signal)) > 0:
        wet_signal *= np.max(np.abs(input_signal)) / np.max(np.abs(wet_signal))
    output = input_signal * (1.0 - mix) + wet_signal * mix
    return output

# === ГЛАВНАЯ ФУНКЦИЯ СИНТЕЗА ===
def synthesize_darbuka_strike(
    target_freq: float, # <-- Настройка (Tuning)
    articulation: str = "doum", 
    strike_force: float = 1.0, 
    skin_mat_name: str = "mylar_standard", 
    shell_mat_name: str = "aluminum",
    duration: float = 1.5, 
    fs: int = 44100, 
    yield_cb=None,
    saturation: float = 0.0,
    mat_boost: float = 0.0,
    show_gui: bool = False,
    N_grid: int = 128,
    rr_index: int = 1
):
    init_taichi_headless()
    N_grid = min(N_grid, N_MAX)
    init_darbuka_fields(N_grid)
    
    skin_mat = get_effective_properties(MATERIAL_PHYSICS.get(skin_mat_name, MATERIAL_PHYSICS["mylar_standard"]))
    shell_mat = get_effective_properties(MATERIAL_PHYSICS.get(shell_mat_name, MATERIAL_PHYSICS["aluminum"]))

    if rr_index > 1:
        state = np.random.RandomState(int(rr_index * 137 + strike_force * 997))
        strike_force = np.clip(strike_force + state.uniform(-0.05, 0.05), 0.05, 1.0)

    # Круглая маска Дарбуки
    r_mask = np.zeros((N_MAX, N_MAX), dtype=np.float32)
    radius_pixels = 0.45 * N_grid
    center = N_grid / 2.0
    for i in range(N_grid):
        for j in range(N_grid):
            if (i - center)**2 + (j - center)**2 < radius_pixels**2:
                r_mask[i, j] = 1.0
    mask.from_numpy(r_mask)
    grid_area = np.pi * (radius_pixels ** 2)

    # --- ТЮНИНГ (Основа) ---
    # Вычисляем CFL-субстеппинг так, чтобы волна выдавала нужную частоту
    ideal_c_step = target_freq * np.pi * N_grid / (2.4048 * fs)
    M = int(np.ceil(ideal_c_step / 0.40)) if ideal_c_step > 0.40 else 1
    
    # Генерируем гетерогенную карту
    grids_raw, _ = build_heterogeneous_grids(r_mask, skin_mat, MATERIAL_PHYSICS)
    
    base_v_sq = skin_mat.get("E_long", 10.0) / skin_mat.get("density", 1.0)
    local_v_sq_map = grids_raw["E_l"] / (grids_raw["rho"] + 1e-9)
    v_sq_ratio_map = local_v_sq_map / base_v_sq
    
    base_c_sq = (target_freq * np.pi * N_grid / (2.4048 * fs * M)) ** 2
    c_x_map = np.clip(base_c_sq * v_sq_ratio_map, 0.001, 0.24).astype(np.float32)
    c_y_map = np.clip(base_c_sq * v_sq_ratio_map, 0.001, 0.24).astype(np.float32)
    
    c_sq_x_field.from_numpy(c_x_map)
    c_sq_y_field.from_numpy(c_y_map)
    
    # Края мембраны всегда задемпфированы ободом
    edge_multiplier = np.ones((N_MAX, N_MAX), dtype=np.float32)
    for i in range(N_grid):
        for j in range(N_grid):
            if r_mask[i, j] > 0.5:
                dist = np.sqrt((i - center)**2 + (j - center)**2)
                if radius_pixels - dist < 6.0:
                    edge_multiplier[i, j] = 8.0
                    
    loss_map = ((grids_raw["loss"] * 0.5) * edge_multiplier / M).astype(np.float32)
    visco_map = ((grids_raw["visco"] * 25.0) * edge_multiplier / M).astype(np.float32)
    loss_field.from_numpy(loss_map)
    visco_field.from_numpy(visco_map)

    # --- АРТИКУЛЯЦИИ ---
    contact_time_ms = 4.0
    r_strike = 15.0 * (N_grid / 128.0)
    strike_x, strike_y = int(center), int(center)
    exc_multiplier = 0.25
    
    if articulation == "doum":
        contact_time_ms = 4.5 - (1.0 * strike_force)
        r_strike = (18.0 + 5.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 0.35
        strike_y = int(center + 0.15 * radius_pixels)
        
    elif articulation in ["tek", "ka"]:
        contact_time_ms = 1.5 - (0.8 * strike_force)
        r_strike = 3.0 * (N_grid / 128.0)
        exc_multiplier = 0.55
        # Тэк бьется по краю, Ка бьется чуть дальше
        offset = 0.88 if articulation == "tek" else 0.78
        strike_y = int(center + offset * radius_pixels)
        if rr_index % 2 == 0: strike_x = int(center + 0.2 * radius_pixels)
        
    elif articulation == "slap":
        contact_time_ms = 1.2
        r_strike = (6.0 + 4.0 * strike_force) * (N_grid / 128.0)
        exc_multiplier = 1.2
        strike_y = int(center + 0.4 * radius_pixels)
        
    elif articulation == "roll":
        contact_time_ms = 0.8
        r_strike = 2.0 * (N_grid / 128.0)
        exc_multiplier = 0.4
        strike_y = int(center + 0.85 * radius_pixels)

    # === ГЕНЕРАТОР БИОМЕХАНИЧЕСКОГО ЭКСАЙТЕРА (ФАЛАНГА + КОСТЬ + КОЖА) ===
    pulse_len = max(8, int((contact_time_ms / 1000.0) * fs * M))
    click_len = max(2, int(0.002 * fs * M))
    
    exciter_len = max(pulse_len, click_len)
    exciter = np.zeros(exciter_len, dtype=np.float32)
    
    t_pulse = np.linspace(0, np.pi, pulse_len)
    flesh_bump = np.sin(t_pulse) * np.exp(-np.linspace(0, 3.0, pulse_len))
    
    noise_raw = np.random.normal(0, 1.0, click_len)
    b_click, a_click = butter(2, [3500.0 / (fs * M / 2.0), 14000.0 / (fs * M / 2.0)], btype='bandpass')
    bone_snap = lfilter(b_click, a_click, noise_raw) * np.exp(-np.linspace(0, 8.0, click_len))

    if articulation == "doum":
        b_thud, a_thud = butter(2, 400.0 / (fs * M / 2.0), btype='low')
        noise_thud = np.random.normal(0, 1.0, pulse_len)
        air_thud = lfilter(b_thud, a_thud, noise_thud) * np.exp(-np.linspace(0, 5.0, pulse_len))
        
        exciter[:pulse_len] += flesh_bump * (strike_force ** 1.3) * exc_multiplier
        exciter[:pulse_len] += air_thud * 0.4 * strike_force
        exciter[:click_len] += bone_snap * 0.1 * strike_force
        
    elif articulation in ["tek", "ka", "roll"]:
        exciter[:pulse_len] += flesh_bump * 0.3 * exc_multiplier * (strike_force ** 1.2)
        exciter[:click_len] += bone_snap * 1.5 * strike_force
        
        squeak = np.sin(np.linspace(0, 50.0, click_len)) * bone_snap * 0.6
        exciter[:click_len] += squeak * strike_force
        
    elif articulation == "slap":
        exciter[:pulse_len] += flesh_bump * 0.8 * exc_multiplier
        exciter[:click_len] += bone_snap * 0.8 * strike_force
        
        b_pop, a_pop = butter(2, 1500.0 / (fs * M / 2.0), btype='low')
        pop = lfilter(b_pop, a_pop, noise_raw) * np.exp(-np.linspace(0, 6.0, click_len))
        exciter[:click_len] += pop * 1.2 * strike_force

    exciter *= float(N_REF) / float(N_grid)

    max_steps = int(duration * fs)
    fdtd_signal = np.zeros(max_steps)
    velocity_arr = np.zeros(max_steps, dtype=np.float32)
    
    coupling_k_step = 0.02 / M
    
    p_bend = 0.15 * (strike_force ** 3.0) if articulation == "doum" else 0.05
    smoothed_strain = 0.0
    
    strain_alpha = 1.0 - np.exp(-1.0 / (fs * 0.002))
    
    delay_substeps = max(1, int(0.0015 * fs * M))
    vol_history = np.zeros(delay_substeps, dtype=np.float32)
    history_idx = 0
    
    base_shell_hz = np.clip(np.sqrt((shell_mat.get("E_long", 70.0) * 1e9) / (shell_mat.get("density", 2.7) * 1000.0)) * 0.05, 400.0, 3500.0)
    cache_key = (round(shell_mat.get("E_long", 70.0), 3), round(shell_mat.get("density", 2.7), 3), round(shell_mat.get("loss_factor", 0.001), 4), round(base_shell_hz, 1), fs, articulation)
    
    global _BODY_IR_CACHE
    if cache_key in _BODY_IR_CACHE:
        body_ir = _BODY_IR_CACHE[cache_key]
    else:
        body_ir = generate_body_ir(shell_mat, base_shell_hz=base_shell_hz, fs=fs, articulation=articulation)
        _BODY_IR_CACHE[cache_key] = body_ir

    gui = ti.GUI(f"Darbuka: {articulation.upper()}", res=(N_grid, N_grid), background_color=0x00) if show_gui else None
    
    actual_steps_rendered = 0

    # === ГЛАВНЫЙ ЦИКЛ ===
    for step in range(max_steps):
        actual_steps_rendered += 1
        
        if step % 800 == 0:
            if yield_cb:
                yield_cb(step, max_steps)
                
            if show_gui and gui:
                if not gui.running: break
                
                field = p.to_numpy()[:N_grid, :N_grid]
                mask_vis = r_mask[:N_grid, :N_grid]
                
                ac_field = field - np.mean(field)
                real_energy = np.max(np.abs(ac_field))
                
                # --- АВТОМАТИЧЕСКАЯ ОСТАНОВКА (Скип пустых кадров) ---
                if step > int(fs * 0.15) and real_energy < 1e-5:
                    break
                
                norm_field = ac_field / (real_energy + 1e-10)
                
                img = np.zeros((N_grid, N_grid, 3), dtype=np.float32)
                img[:, :, :] += mask_vis[:, :, None] * 0.12
                img[:, :, 0] += np.clip(norm_field * 1.5, 0, 1) * mask_vis
                img[:, :, 2] += np.clip(-norm_field * 1.5, 0, 1) * mask_vis
                
                gui.set_image(img)
                gui.show()
            else:
                # Авто-остановка для режима без GUI (Пакетный рендер)
                compute_darbuka_stats(N_grid)
                if step > int(fs * 0.15) and stat_strain[None] < 1e-9:
                    break

        compute_darbuka_stats(N_grid)
        raw_strain = stat_strain[None] / grid_area * ((N_grid / float(N_REF)) ** 2)
        
        # ЗАЩИТА ОТ КРАША: Если FDTD всё-таки сорвался
        if np.isnan(raw_strain) or np.isinf(raw_strain):
            print("⚠️ Аварийная остановка: нестабильность физического движка на шаге", step)
            break
            
        smoothed_strain += strain_alpha * (raw_strain - smoothed_strain)
        avg_vol = stat_vol[None] / grid_area

        # Динамическое демпфирование (Slap/Mute)
        damp_val, damp_cov = 0.0, 0
        if articulation == "slap" and step > int(0.008 * fs):
            ramp = min(1.0, (step - int(0.008 * fs)) / (0.005 * fs))
            damp_val, damp_cov = 0.08 * ramp, int(N_grid * 0.6) # Рука накрывает центр
        elif articulation == "mute":
            damp_val, damp_cov = 0.04, int(N_grid * 0.8)

        for sub in range(M):
            step_internal = step * M + sub
            exc_val = exciter[step_internal] if step_internal < exciter_len else 0.0

            vol_delayed = vol_history[history_idx]
            vol_history[history_idx] = avg_vol
            history_idx = (history_idx + 1) % delay_substeps

            step_darbuka_fdtd(
                N_grid, coupling_k_step, avg_vol, vol_delayed,
                strike_x, strike_y, exc_val, r_strike,
                p_bend, smoothed_strain, damp_val / M, damp_cov
            )
            
            # Трение при слапе
            fric = 6.0 * (strike_force**1.2) / M if articulation == "slap" and step < int(0.05 * fs) else 0.0
            apply_darbuka_tactile_forces(
                N_grid, 0.0, 0.0, strike_force, fric, strike_x, strike_y, r_strike
            )
            update_darbuka_fields(N_grid)

        # Съем звука с края (чтобы ловить звонкие моды)
        fdtd_signal[step] = p[int(N_grid * 0.3), int(N_grid * 0.75)]
        velocity_arr[step] = p[strike_x, strike_y] - p_past[strike_x, strike_y]

    if show_gui and gui: gui.close()

    # Отрезаем пустые хвосты, если симуляция завершилась досрочно
    fdtd_signal = fdtd_signal[:actual_steps_rendered]
    velocity_arr = velocity_arr[:actual_steps_rendered]

    # === ПОСТОБРАБОТКА ===
    pad_samples = int(fs * 1.0)
    padded_signal = np.pad(fdtd_signal, (0, pad_samples))
    velocity_arr = np.pad(velocity_arr, (0, pad_samples))
    
    # 1. Акустика металлического кубка
    shell_signal = apply_darbuka_shell(padded_signal, fs, shell_mat, target_freq, articulation, strike_force)
    
    # 2. Базовый микс
    mixed = padded_signal * 0.8 + shell_signal * 0.4
    
    # 3. Интеграция 3D-тела (Body IR Convolution)
    mixed = apply_body_convolution(mixed, body_ir, fs, mix=0.3)

    # 4. ТАКТИЛЬНЫЙ ШУМ
    t_arr = np.arange(len(mixed)) / fs
    tactile_noise = generate_tactile_profile(
        skin_mat, t_arr, mixed, velocity_arr, np.diff(velocity_arr, append=0), np.zeros_like(mixed),
        fs, fs/2.0, is_space=False, fatness=mat_boost, strike_force=strike_force
    )
    
    tactile_env = np.exp(-t_arr / 0.06)
    tactile_mix = 0.6 * (1.0 + mat_boost * 1.5) * (strike_force ** 1.2)
    
    final_out = mixed + tactile_noise * tactile_env * tactile_mix

    # 5. Сатурация
    final_out = apply_darbuka_fat(final_out, fs, articulation, strike_force, saturation)
    
    # 6. Стерео комната
    room = pra.ShoeBox([4.0, 5.0, 3.0], fs=fs, max_order=4)
    room.add_source([2.0, 2.0, 1.0], signal=final_out)
    room.add_microphone_array(np.array([[1.8, 2.5, 1.2], [2.2, 2.5, 1.2]]).T)
    room.simulate()
    
    stereo_out = room.mic_array.signals.T
    stereo_out = stereo_out[:len(final_out)]
    
    wet_mix = 0.15
    stereo_out = np.column_stack((final_out, final_out)) * (1.0 - wet_mix) + stereo_out * wet_mix

    # Нормализация с сохранением динамики
    max_val = np.max(np.abs(stereo_out))
    if max_val > 0:
        dyn_scale = 10.0 ** (-8.0 / 20.0) + (1.0 - 10.0 ** (-8.0 / 20.0)) * strike_force
        stereo_out = (stereo_out / max_val) * dyn_scale * 0.85

    return stereo_out