# --- START OF FILE engine/core_taichi.py ---
import numpy as np
import taichi as ti
import pyroomacoustics as pra
from scipy.signal import butter, lfilter

import scipy.fft as fft
from scipy.ndimage import gaussian_filter1d

from engine.tactile import generate_tactile_profile
from engine.geometry import generate_instrument_mask, get_strike_point, get_pickup_point, get_pickup_points_stereo
from engine.core_logging import core_logger

try:
    taichi_is_ready = ti.lang.impl.get_runtime().prog is not None
except Exception:
    taichi_is_ready = False

if not taichi_is_ready:
    ti.init()

# Выделяем максимальный буфер памяти с запасом
N_MAX = 512

# Базовые поля на максимум
p = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_past = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_future = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
mask = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

# Поля для гетерогенных материалов
rho_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
E_l_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
E_t_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX)) 
loss_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
visco_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

# Вспомогательная функция для безопасного импорта numpy-карт в Taichi
def pad_to_max(arr, target_shape=(N_MAX, N_MAX)):
    h, w = arr.shape
    return np.pad(arr, ((0, target_shape[0] - h), (0, target_shape[1] - w)))

@ti.kernel
def init_fields(N: ti.i32):
    # Обнуляем строго активную зону N x N
    for i, j in ti.ndrange(N, N):
        p[i, j] = 0.0
        p_past[i, j] = 0.0
        p_future[i, j] = 0.0

@ti.kernel
def excite_strike(N: ti.i32, x: ti.i32, y: ti.i32):
    scale = N / 128.0
    for i, j in ti.ndrange(N, N):
        dist_sq = ti.cast((i - x)**2 + (j - y)**2, ti.f32)
        # Масштабируем радиус возбуждения в зависимости от разрешения сетки N
        if dist_sq < (9.0 * scale**2) and mask[i, j] > 0.5:
            amp = ti.exp(-dist_sq / (3.0 * scale**2))
            p[i, j] = amp
            p_past[i, j] = amp

@ti.kernel
def apply_tactile_forces(N: ti.i32, gran: ti.f32, fluid: ti.f32, brit: ti.f32, fibr: ti.f32, fatness: ti.f32):
    limit = 75 + ti.cast(fatness * 100.0, ti.i32)
    for idx in range(180):
        if idx < limit:
            i = ti.cast(ti.random() * N, ti.i32)
            j = ti.cast(ti.random() * N, ti.i32)
            if i > 0 and i < N-1 and j > 0 and j < N-1 and mask[i, j] > 0.5:
                strain = ti.abs(p[i, j] - p_past[i, j])
                mult = 1.0 + fatness * 0.8
                
                if gran > 0.0 and strain > 0.00001:
                    if ti.random() < gran: p_future[i, j] += (ti.random() - 0.5) * gran * strain * 0.5 * mult
                if brit > 0.0 and strain > 0.0001:
                    if ti.random() < brit * 0.5:
                        p_future[i, j] += (ti.random() - 0.5) * brit * strain * 1.5 * mult
                        p_future[i, j] *= 0.99
                if fibr > 0.0 and strain > 0.00005:
                    if ti.random() < fibr: p_future[i, j] += (ti.random() - 0.5) * fibr * strain * 0.8 * mult
                if fluid > 0.0 and strain > 0.00001:
                    if ti.random() < fluid * 0.1: p_future[i, j] += (ti.random() - 0.5) * fluid * strain * 1.0 * mult

@ti.kernel
def step_fdtd_anisotropic_ultimate(
    N: ti.i32,
    damp_start: ti.f32, damp_end: ti.f32,
    c_sq_x: ti.f32, c_sq_y: ti.f32,
    visco_start: ti.f32, visco_end: ti.f32,
    fluid: ti.f32,
    strike_x: ti.i32, strike_y: ti.i32,
    exciter_val: ti.f32,
    progress: ti.f32,
    yield_stress: ti.f32,
    shatter_amt: ti.f32,
    noise_amp: ti.f32, fatness: ti.f32
):
    damp = damp_start + (damp_end - damp_start) * progress
    visco = visco_start + (visco_end - visco_start) * progress

    for i, j in ti.ndrange(N, N):
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask[i, j] > 0.5:
            lap_curr_x = p[i-1, j] + p[i+1, j] - 2.0 * p[i, j]
            lap_curr_y = p[i, j-1] + p[i, j+1] - 2.0 * p[i, j]
            lap_past_x = p_past[i-1, j] + p_past[i+1, j] - 2.0 * p_past[i, j]
            lap_past_y = p_past[i, j-1] + p_past[i, j+1] - 2.0 * p_past[i, j]
            
            local_c_x = c_sq_x
            local_c_y = c_sq_y
            
            strain = ti.abs(p[i, j] - p_past[i, j])
            
            if yield_stress > 0.0 and strain > yield_stress:
                local_c_x *= 0.1
                local_c_y *= 0.1
                force_shatter = (ti.random() - 0.5) * strain * shatter_amt
                p[i, j] += force_shatter
            
            lap_curr = local_c_x * lap_curr_x + local_c_y * lap_curr_y
            lap_past = local_c_x * lap_past_x + local_c_y * lap_past_y
            
            force = lap_curr + visco * (lap_curr - lap_past)
            
            if fluid > 0.0:
                force += fluid * ti.sin(p[i, j] * 20.0) * lap_curr * 0.05
                
            if i == strike_x and j == strike_y:
                force += exciter_val
                
                if noise_amp > 0.0:
                    v_p = p[i, j] - p_past[i, j]
                    v_bow = 0.055
                    v_rel = v_bow - v_p
                    friction_dir = ti.tanh(v_rel * 300.0)
                    mu = 0.22 + (0.85 - 0.22) * ti.exp(-(v_rel / 0.012)**2)
                    squeak_mod = ti.sin(p[i, j] * 150.0 + v_p * 20.0) * 0.38 * (1.0 + fatness)
                    surface_grit = (ti.random() - 0.5) * 0.32 * ti.abs(friction_dir) * (1.0 + fatness * 1.5)
                    force += friction_dir * mu * noise_amp * (1.0 + squeak_mod + surface_grit)
                
            p_future[i, j] = (2.0 * p[i, j] - p_past[i, j] * (1.0 - damp) + force) / (1.0 + damp)
        else:
            p_future[i, j] = 0.0

def load_material_grids(grids_dict):
    rho_field.from_numpy(pad_to_max(grids_dict["rho"]))
    E_l_field.from_numpy(pad_to_max(grids_dict["E_l"]))
    E_t_field.from_numpy(pad_to_max(grids_dict["E_t"])) 
    loss_field.from_numpy(pad_to_max(grids_dict["loss"]))
    visco_field.from_numpy(pad_to_max(grids_dict["visco"])) 

@ti.kernel
def step_fdtd_heterogeneous(
    N: ti.i32,
    global_speed_factor: ti.f32,
    fluid: ti.f32,
    strike_x: ti.i32, strike_y: ti.i32,
    exciter_val: ti.f32,
    progress: ti.f32,
    yield_stress: ti.f32,
    shatter_amt: ti.f32,
    noise_amp: ti.f32, fatness: ti.f32,
    deg_damp: ti.f32, deg_visco: ti.f32,
    substeps_M: ti.f32
):
    for i, j in ti.ndrange(N, N):
        if i > 0 and i < N-1 and j > 0 and j < N-1 and mask[i, j] > 0.5:
            local_rho = rho_field[i, j] * 1000.0 + 1e-6
            local_E_l = E_l_field[i, j] * 1e9
            local_E_t = E_t_field[i, j] * 1e9
            
            local_v_x = ti.sqrt(local_E_l / local_rho)
            local_v_y = ti.sqrt(local_E_t / local_rho)
            
            c_sq_x = ti.max(0.005, ti.min(0.24, ti.cast(local_v_x * global_speed_factor, ti.f32)))
            c_sq_y = ti.max(0.005, ti.min(0.24, ti.cast(local_v_y * global_speed_factor, ti.f32)))
            
            local_loss = (loss_field[i, j] * 0.15 + 0.00005) / substeps_M
            local_visco = (visco_field[i, j] * 25000.0 + 0.001) / substeps_M
            
            damp = local_loss + deg_damp * progress
            visco = local_visco + deg_visco * progress
            
            total_energy = c_sq_x + c_sq_y + visco
            if total_energy > 0.49:
                scale_limit = 0.49 / total_energy
                c_sq_x *= scale_limit
                c_sq_y *= scale_limit
                visco *= scale_limit
            
            lap_curr_x = p[i-1, j] + p[i+1, j] - 2.0 * p[i, j]
            lap_curr_y = p[i, j-1] + p[i, j+1] - 2.0 * p[i, j]
            lap_past_x = p_past[i-1, j] + p_past[i+1, j] - 2.0 * p_past[i, j]
            lap_past_y = p_past[i, j-1] + p_past[i, j+1] - 2.0 * p_past[i, j]
            
            strain = ti.abs(p[i, j] - p_past[i, j])
            
            if yield_stress > 0.0 and strain > yield_stress:
                c_sq_x *= 0.1
                c_sq_y *= 0.1
            
            lap_curr = c_sq_x * lap_curr_x + c_sq_y * lap_curr_y
            lap_past = c_sq_x * lap_past_x + c_sq_y * lap_past_y
            
            force = lap_curr + visco * (lap_curr - lap_past)
            
            if yield_stress > 0.0 and strain > yield_stress:
                force += (ti.random() - 0.5) * strain * shatter_amt
            
            if fluid > 0.0:
                force += fluid * ti.sin(p[i, j] * 20.0) * lap_curr * 0.05
                
            if i == strike_x and j == strike_y:
                force += exciter_val
                
                if noise_amp > 0.0:
                    v_p = p[i, j] - p_past[i, j]
                    v_bow = 0.055
                    v_rel = v_bow - v_p
                    friction_dir = ti.tanh(v_rel * 300.0)
                    mu = 0.22 + (0.85 - 0.22) * ti.exp(-(v_rel / 0.012)**2)
                    squeak_mod = ti.sin(p[i, j] * 150.0 + v_p * 20.0) * 0.38 * (1.0 + fatness)
                    surface_grit = (ti.random() - 0.5) * 0.32 * ti.abs(friction_dir) * (1.0 + fatness * 1.5)
                    force += friction_dir * mu * noise_amp * (1.0 + squeak_mod + surface_grit)
                
            p_future[i, j] = (2.0 * p[i, j] - p_past[i, j] * (1.0 - damp) + force) / (1.0 + damp)
        else:
            p_future[i, j] = 0.0

@ti.kernel
def update_fields(N: ti.i32):
    for i, j in ti.ndrange(N, N):
        p_past[i, j] = p[i, j]
        p[i, j] = p_future[i, j]

def get_physical_size(inst_dict, user_scale):
    f0 = inst_dict.get("A0", inst_dict.get("f0", 150.0))
    template_name = inst_dict.get("resonator_template", "isotropic_plate")
    if "space" in template_name:
        base_L = inst_dict.get("base_size", 15.0)
    else:
        base_L = (343.0 / max(15.0, f0)) / 2.0
    return base_L * user_scale

def note_name_to_hz(note_name: str) -> float:
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    name = note_name[:-1]
    octave = int(note_name[-1])
    if name.endswith('b'):
        flat_to_sharp = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}
        name = flat_to_sharp.get(name, name)
    key_number = notes.index(name) + (octave + 1) * 12
    return 440.0 * (2.0 ** ((key_number - 69) / 12.0))

def get_resonance_info(inst_dict, user_scale):
    base_f0 = inst_dict.get("f0", None)
    base_A0 = inst_dict.get("A0", None)
    freqs = inst_dict.get("sympathetic_strings", [])
    tuned_freqs = [f / user_scale for f in freqs]
    info = {
        "lowest_string_hz": base_f0 / user_scale if base_f0 is not None else None,
        "helmholtz_hz": base_A0 / user_scale if base_A0 is not None else None,
        "sympathetic_hz": tuned_freqs,
    }
    return info

def generate_fdtd_ir(inst_dict, mat_dict, user_scale=1.0, duration=1.5, sample_rate=44100, 
                     custom_strike=None, custom_pickup_L=None, custom_pickup_R=None, is_friction=False, fatness=0.0,
                     exciter_signal=None,
                     is_stereo=False,
                     use_degradation=False,
                     degradation_amt=0.0,
                     nonlinearity=0.0,
                     heterogeneous_grids=None,
                     visual_map=None,
                     strike_force=1.0,
                     demud_db=3.0,
                     N_grid=128,      # <-- НОВОЕ: Гибкий размер сетки (128, 256, 512)
                     show_gui=True    # <-- НОВОЕ: Отключение дисплея для Google Colab (headless)
                     ):
    
    # Ограничиваем сверху буфером
    N_grid = min(N_grid, N_MAX)
    init_fields(N_grid)
    
    np_mask = generate_instrument_mask(inst_dict, N_grid)
    mask.from_numpy(pad_to_max(np_mask))
    
    use_heterogeneous = heterogeneous_grids is not None
    if use_heterogeneous:
        load_material_grids(heterogeneous_grids)
    
    if custom_strike:
        strike_x, strike_y = custom_strike
    else:
        strike_x, strike_y = get_strike_point(inst_dict, N_grid)
    
    if is_stereo:
        default_L, default_R = get_pickup_points_stereo(inst_dict, N_grid)
        pickup_L = custom_pickup_L if custom_pickup_L is not None else default_L
        pickup_R = custom_pickup_R if custom_pickup_R is not None else default_R
    else:
        if custom_pickup_L:
            px, py = custom_pickup_L
        else:
            px, py = get_pickup_point(inst_dict, N_grid)
        pickup_L, pickup_R = (px, py), (px, py)
        
    W_meters = get_physical_size(inst_dict, user_scale)
    size_factor = 0.4 / max(0.01, W_meters)
    poisson_factor = np.sqrt(1.0 / (1.0 - mat_dict.get("poisson", 0.3)**2))
    thickness_factor = np.sqrt(mat_dict["base_thickness"] * user_scale / 0.003)
    
    rho_kg = mat_dict["density"] * 1000.0
    
    # Физические скорости материала
    v_x_phys = np.sqrt((mat_dict["E_long"] * 1e9) / rho_kg) * poisson_factor * thickness_factor * size_factor
    v_y_phys = np.sqrt((mat_dict["E_trans"] * 1e9) / rho_kg) * poisson_factor * thickness_factor * size_factor
    
    # Масштабируем физическую скорость под плотность выбранной сетки N_grid
    v_x_scaled = v_x_phys * (N_grid / 128.0)
    v_y_scaled = v_y_phys * (N_grid / 128.0)
    
    # === АВТОМАТИЧЕСКИЙ СУБСТЕППИНГ ДЛЯ CFL-СТАБИЛЬНОСТИ ===
    max_scaled_v = max(v_x_scaled, v_y_scaled)
    ideal_c_step = (max_scaled_v / 5000.0) * 0.22
    
    M = 1
    if ideal_c_step > 0.23:
        M = int(np.ceil(ideal_c_step / 0.23))
        
    print(f"📊 Сетка: {N_grid}x{N_grid} | Стабильность CFL: требуется {M} субстепов за сэмпл.")
    # =======================================================
    
    # Рассчитываем скорости FDTD на внутренней субстеп-частоте (sample_rate * M)
    c_sq_x = np.clip((v_x_scaled / M / 5000.0) * 0.22, 0.005, 0.24)
    c_sq_y = np.clip((v_y_scaled / M / 5000.0) * 0.22, 0.005, 0.24)
    
    # Затухания и вязкость масштабируем на шаг субстепа (1/M)
    damp_start = np.clip((mat_dict["loss_factor"] * 0.15 + 0.00005) / M, 0.00005, 0.05)
    visco_start = np.clip((mat_dict["visco_gamma"] * 25000.0 + 0.001) / M, 0.001, 0.2)

    if core_logger is not None:
        core_logger.log_physics_summary(mat_dict, "Resolved physics after material blend", {
            "density": float(mat_dict["density"]),
            "E_long": float(mat_dict["E_long"]),
            "E_trans": float(mat_dict["E_trans"]),
            "loss_factor": float(mat_dict["loss_factor"]),
            "visco_gamma": float(mat_dict["visco_gamma"]),
            "base_thickness": float(mat_dict.get("base_thickness", 0.003)),
            "c_sq_x": float(c_sq_x),
            "c_sq_y": float(c_sq_y),
            "damp_start": float(damp_start),
            "visco_start": float(visco_start)
        })
        core_logger.log_modal_dispersion(mat_dict, core_logger.estimate_modal_dispersion(mat_dict, num_modes=10))
        core_logger.log_energy_decay(mat_dict, core_logger.estimate_energy_decay(mat_dict))

    if use_degradation:
        deg_damp = (degradation_amt * 0.04) / M
        deg_visco = (degradation_amt * 0.15) / M
        damp_end = np.clip(damp_start + deg_damp, 0.00005, 0.05)
        visco_end = np.clip(visco_start + deg_visco, 0.001, 0.2)
    else:
        deg_damp = 0.0
        deg_visco = 0.0
        damp_end = damp_start
        visco_end = visco_start
        
    global_speed_factor_scaled = ((poisson_factor * thickness_factor * size_factor / 5000.0) * 0.22) * (N_grid / 128.0) / M
        
    if nonlinearity > 0.0:
        brittleness = mat_dict.get("tactile_profile", {}).get("brittleness", 0.0)
        if brittleness == 0.0:
            if mat_dict.get("category") in ["stone", "metal"]:
                brittleness = 0.5
            elif mat_dict.get("category") == "wood":
                brittleness = 0.2
            else:
                brittleness = 0.05
                
        e_factor = np.log10(1.0 + mat_dict.get("E_long", 10.0))
        shatter_amt = 0.6 * nonlinearity * brittleness * e_factor
        yield_stress_threshold = np.clip(0.25 / (nonlinearity * brittleness + 0.1), 0.005, 10.0)
    else:
        yield_stress_threshold = 0.0
        shatter_amt = 0.0

    tactile = mat_dict.get("tactile_profile", {})
    fibr = np.clip(tactile.get("fibrousness", 0.0), 0.0, 1.0)
    fluid_val = np.clip(tactile.get("fluidity", 0.0), 0.0, 1.0)
    gran = np.clip(tactile.get("granularity", 0.0), 0.0, 1.0)
    brit = np.clip(tactile.get("brittleness", 0.0), 0.0, 1.0)
    
    if nonlinearity > 0.0:
        brit = np.clip(brit + nonlinearity * 0.15, 0.0, 1.0)
        gran = np.clip(gran + nonlinearity * 0.12, 0.0, 1.0)
        
    has_tactile = (fibr > 0 or fluid_val > 0 or gran > 0 or brit > 0)

    num_steps = int(duration * sample_rate)
    
    # [NEW] Массивы физической телеметрии (Сенсоры) для Tactile Engine V6
    velocity_arr = np.zeros(num_steps, dtype=np.float32)
    acceleration_arr = np.zeros(num_steps, dtype=np.float32)
    stress_arr = np.zeros(num_steps, dtype=np.float32)
    prev_vel = 0.0
    
    # Генерация сигнала эксайтера на частоте субстеппинга
    exciter_signal_sub = None
    if exciter_signal is not None:
        raw_exc = np.array(exciter_signal, dtype=np.float32)
        # Интерполируем входной сигнал под частоту субстепов M
        from scipy.interpolate import interp1d
        t_orig = np.linspace(0, duration, len(raw_exc))
        t_sub = np.linspace(0, duration, num_steps * M)
        exciter_signal_sub = interp1d(t_orig, raw_exc, kind='linear', fill_value="extrapolate")(t_sub)
        exciter_signal_sub *= (0.1 * strike_force)
    else:
        exciter_signal_sub = np.zeros(num_steps * M, dtype=np.float32)
        if not is_friction:
            base_pulse_ms = 0.0006 * max(0.5, W_meters) 
            pulse_len = max(2, int(sample_rate * M * base_pulse_ms)) # Длина импульса масштабируется под M
            
            t_pulse = np.linspace(-1.0, 2.0, pulse_len)
            pulse = np.exp(-(t_pulse**2))
            pulse = pulse / np.max(pulse)
            
            click_amt = 0.55  
            mallet_amt = 0.45 
            
            exciter_signal_sub[0] = strike_force * click_amt
            exciter_signal_sub[:pulse_len] += pulse * strike_force * mallet_amt
            
    noise_amp = (0.12 * strike_force) if is_friction else 0.0

    dry_audio_L = np.zeros(num_steps, dtype=np.float32)
    dry_audio_R = np.zeros(num_steps, dtype=np.float32)
    
    if show_gui:
        if visual_map is not None:
            bg_img = (visual_map.astype(np.float32) / 255.0) * 0.35
        else:
            bg_img = np.zeros((N_grid, N_grid, 3), dtype=np.float32)
            bg_img += np_mask[..., None] * 0.12
        gui = ti.GUI("Troakar Engine", res=(2 * N_grid, 2 * N_grid), background_color=0x000000)
    
    for step in range(num_steps):
        # === ВНУТРЕННИЙ ЦИКЛ СУБСТЕППИНГА ===
        # Просчитываем M шагов физики за 1 аудио-сэмпл
        for sub in range(M):
            step_internal = step * M + sub
            progress = step_internal / float(max(1, num_steps * M - 1))
            
            exc_val = exciter_signal_sub[step_internal]
            
            if use_heterogeneous:
                step_fdtd_heterogeneous(
                    N_grid, global_speed_factor_scaled, fluid_val,
                    strike_x, strike_y, exc_val, progress, yield_stress_threshold, shatter_amt, noise_amp, fatness,
                    deg_damp, deg_visco,
                    float(M)
                )
            else:
                step_fdtd_anisotropic_ultimate(
                    N_grid, damp_start, damp_end, c_sq_x, c_sq_y, visco_start, visco_end, 
                    fluid_val,
                    strike_x, strike_y, exc_val, progress, yield_stress_threshold, shatter_amt, noise_amp, fatness
                )
            
            if has_tactile:
                apply_tactile_forces(N_grid, gran, fluid_val, brit, fibr, fatness)
            
            update_fields(N_grid)
        # ===================================
        
        # [NEW] Снятие телеметрии с точки удара (как датчики для DSP)
        sx, sy = strike_x, strike_y
        p_curr = p[sx, sy]
        p_past_val = p_past[sx, sy]
        
        # Аппроксимация тензора напряжений (Лапласиан вокруг точки удара)
        local_stress = p[sx+1, sy] + p[sx-1, sy] + p[sx, sy+1] + p[sx, sy-1] - 4.0 * p_curr
        
        current_vel = p_curr - p_past_val
        current_accel = current_vel - prev_vel
        prev_vel = current_vel
        
        velocity_arr[step] = current_vel
        acceleration_arr[step] = current_accel
        stress_arr[step] = local_stress
        
        # Снимаем звук на стандартной частоте дискретизации
        dry_audio_L[step] = p[pickup_L[0], pickup_L[1]]
        dry_audio_R[step] = p[pickup_R[0], pickup_R[1]]
        
        # Обновляем GUI на частоте сэмпл-рейта
        if show_gui and step % 1200 == 0:
            if not gui.running: break
            field_np = p.to_numpy()[:N_grid, :N_grid]
            
            img = bg_img.copy()
            norm_field = field_np / (np.max(np.abs(field_np)) + 1e-10)
            
            img[:,:,0] += np.clip(norm_field * 1.5, 0, 1)
            img[:,:,2] += np.clip(-norm_field * 1.5, 0, 1)
            img = np.clip(img, 0, 1)
            
            img[strike_x, strike_y] = [1.0, 0.0, 0.0]
            img[pickup_L[0], pickup_L[1]] = [1.0, 1.0, 0.0]
            if is_stereo:
                img[pickup_R[0], pickup_R[1]] = [1.0, 0.5, 0.0]
            
            gui.set_image(np.repeat(np.repeat(img, 2, axis=0), 2, axis=1))
            
            progress_val = step / float(num_steps)
            gui.line(begin=(0.1, 0.06), end=(0.9, 0.06), color=0x222222, radius=3)
            gui.line(begin=(0.1, 0.06), end=(0.1 + 0.8 * progress_val, 0.06), color=0x00ff96, radius=3)
            gui.text(content=f"Size: {W_meters:.2f}m | {int(progress_val * 100)}%", pos=(0.28, 0.11), color=0xffffff, font_size=11)
            
            gui.show()
            
    if show_gui:
        gui.close()
    
    stereo_ir = np.vstack((dry_audio_L, dry_audio_R)).T
    stereo_ir = np.nan_to_num(stereo_ir, copy=False)
    
    nyquist = sample_rate / 2.0
    
    if np.max(np.abs(stereo_ir)) > 0:
        stereo_ir /= np.max(np.abs(stereo_ir))

    local_mat = mat_dict.copy()
    if "tactile_profile" in local_mat:
        local_mat["tactile_profile"] = local_mat["tactile_profile"].copy()
    else:
        local_mat["tactile_profile"] = {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0}
        
    if nonlinearity > 0.0:
        local_mat["tactile_profile"]["brittleness"] = np.clip(
            local_mat["tactile_profile"].get("brittleness", 0.0) + nonlinearity * 0.15, 0.0, 1.0
        )
        local_mat["tactile_profile"]["granularity"] = np.clip(
            local_mat["tactile_profile"].get("granularity", 0.0) + nonlinearity * 0.12, 0.0, 1.0
        )

    t_array = np.arange(len(stereo_ir)) / sample_rate
    
    if is_stereo:
        ir_tactile_L = generate_tactile_profile(
            local_mat, t_array, stereo_ir[:, 0], 
            velocity_arr, acceleration_arr, stress_arr,
            sample_rate, nyquist, is_space=False, fatness=fatness, strike_force=strike_force
        )
        ir_tactile_R = generate_tactile_profile(
            local_mat, t_array, stereo_ir[:, 1], 
            velocity_arr, acceleration_arr, stress_arr,
            sample_rate, nyquist, is_space=False, fatness=fatness, strike_force=strike_force
        )
    else:
        ir_tactile_L = generate_tactile_profile(
            local_mat, t_array, stereo_ir[:, 0], 
            velocity_arr, acceleration_arr, stress_arr,
            sample_rate, nyquist, is_space=False, fatness=fatness, strike_force=strike_force
        )
        ir_tactile_R = ir_tactile_L
        
    sympathetic_ring = np.zeros_like(stereo_ir[:, 0])
    for string_f in inst_dict.get("sympathetic_strings", []):
        sf = string_f / user_scale 
        if sf < nyquist:
            decay_str = np.exp(-t_array / min(0.4, duration / 4.0))
            sympathetic_ring += 0.003 * decay_str * np.sin(2 * np.pi * sf * t_array)
            sympathetic_ring += 0.001 * decay_str * np.sin(2 * np.pi * (sf * 2.01) * t_array)
            
    dynamic_tactile_mix = 0.65 * (strike_force ** 1.5)
    dynamic_symp_mix = 1.0 * strike_force

    stereo_ir[:, 0] = stereo_ir[:, 0] * 0.75 + ir_tactile_L * dynamic_tactile_mix + sympathetic_ring * dynamic_symp_mix
    stereo_ir[:, 1] = stereo_ir[:, 1] * 0.75 + ir_tactile_R * dynamic_tactile_mix + sympathetic_ring * dynamic_symp_mix
    
    low_cut_hz = np.clip(inst_dict.get("low_cut", 50.0) / user_scale, 15.0, nyquist - 100.0)
    b_low, a_low = butter(3, low_cut_hz / nyquist, btype='high')
    stereo_ir[:, 0] = lfilter(b_low, a_low, stereo_ir[:, 0])
    stereo_ir[:, 1] = lfilter(b_low, a_low, stereo_ir[:, 1])
    
    if not is_stereo:
        stereo_ir[:, 1] = stereo_ir[:, 0]

    if np.max(np.abs(stereo_ir)) > 0:
        stereo_ir /= np.max(np.abs(stereo_ir))

    if demud_db > 0.0:
        import time
        import scipy.fft as fft
        from scipy.ndimage import gaussian_filter1d

        def suppress_resonances(channel_data, fs, max_db_reduction, f0_hz, ch_name="L"):
            start_time = time.time()
            pad_len = len(channel_data) 
            padded_data = np.pad(channel_data, (0, pad_len))
            sig_f = fft.rfft(padded_data)
            mag = np.abs(sig_f) + 1e-12
            freqs = fft.rfftfreq(len(padded_data), 1.0 / fs)
            
            mag_clean = gaussian_filter1d(mag, sigma=4)
            smoothed_mag = gaussian_filter1d(mag, sigma=60)
            
            peak_ratio = smoothed_mag / mag_clean
            intensity = 1.0 + (max_db_reduction / 8.0) 
            peak_ratio = peak_ratio ** intensity
            
            micro_limit_db = max_db_reduction + 4.0 
            min_gain = 10.0 ** (-micro_limit_db / 20.0)
            suppression_gain = np.clip(peak_ratio, min_gain, 1.0)
            
            center_f = np.clip(f0_hz * 2.5, 250.0, 700.0)
            extra_dip = 6.0 * (max_db_reduction / 10.0) 
            macro_dip_db = max_db_reduction + extra_dip
            macro_dip_lin = 10.0 ** (-macro_dip_db / 20.0)
            
            octaves_from_center = np.log2(freqs / center_f + 1e-6)
            bell = np.exp(-(octaves_from_center**2) / (2 * (1.6**2)))
            macro_gain = 1.0 - (1.0 - macro_dip_lin) * bell
            
            total_gain = suppression_gain * macro_gain
            
            safe_f0 = max(f0_hz, 30.0)
            x_points = [15.0, safe_f0 * 0.6, safe_f0, safe_f0 * 1.5, 1200.0, 1800.0]
            y_points = [0.0,  0.0,           0.35,    1.0,           1.0,    0.0]
            taper = np.interp(freqs, x_points, y_points)
            final_gain = 1.0 - taper * (1.0 - total_gain)
            
            boost_db = max_db_reduction * 0.35 
            boost_lin = 10.0 ** (boost_db / 20.0)
            shelf_taper = np.interp(freqs, [1500, 3500], [0.0, 1.0])
            shelf_gain = 1.0 + (boost_lin - 1.0) * shelf_taper
            
            final_gain *= shelf_gain
            final_gain = gaussian_filter1d(final_gain, sigma=8)
            
            sig_f *= final_gain
            processed = fft.irfft(sig_f, n=len(padded_data)).astype(np.float32)
            return processed[:len(channel_data)]

        f0_base = inst_dict.get("A0", inst_dict.get("f0", 150.0)) / user_scale
        stereo_ir[:, 0] = suppress_resonances(stereo_ir[:, 0], sample_rate, demud_db, f0_base, ch_name="L")
        if is_stereo:
            stereo_ir[:, 1] = suppress_resonances(stereo_ir[:, 1], sample_rate, demud_db, f0_base, ch_name="R")
        else:
            stereo_ir[:, 1] = stereo_ir[:, 0]

    import pyroomacoustics as pra
    
    room_w = np.clip(W_meters * 1.5, 0.2, 50.0)
    room_l = np.clip(W_meters * 2.0, 0.2, 50.0)
    
    preset_depth = inst_dict.get("body_depth", None)
    if preset_depth is not None:
        room_h = np.clip(preset_depth * user_scale, 0.05, 50.0)
    else:
        room_h = np.clip(W_meters * 1.2, 0.2, 50.0)

    room_dim = [room_w, room_l, room_h]

    is_space = "space" in inst_dict.get("resonator_template", "")
    wet_mix = 0.85 if is_space else 0.40

    absorption = np.clip(mat_dict.get("loss_factor", 0.01) * 10.0, 0.02, 0.95)
    material_pra = pra.Material(absorption, 0.15)

    room = pra.ShoeBox(room_dim, fs=sample_rate, materials=material_pra, max_order=12)
    
    mono_dry = (stereo_ir[:, 0] + stereo_ir[:, 1]) * 0.5
    room.add_source([room_dim[0]/2, room_dim[1]/2, room_dim[2]*0.2], signal=mono_dry)

    mic_dist = np.clip(W_meters * 0.5, 0.05, 5.0)
    mic_array = np.array([
        [room_dim[0]/2 - mic_dist*0.3, room_dim[1]/2 + mic_dist, room_dim[2]*0.3], 
        [room_dim[0]/2 + mic_dist*0.3, room_dim[1]/2 + mic_dist, room_dim[2]*0.3]
    ])

    mic_array[:, 0] = np.clip(mic_array[:, 0], 0.01, room_dim[0]-0.01)
    mic_array[:, 1] = np.clip(mic_array[:, 1], 0.01, room_dim[1]-0.01)

    room.add_microphone_array(mic_array.T)
    room.simulate()

    stereo_wet = room.mic_array.signals.T

    if len(stereo_wet) > len(stereo_ir):
        stereo_wet = stereo_wet[:len(stereo_ir)]
    else:
        stereo_wet = np.pad(stereo_wet, ((0, len(stereo_ir) - len(stereo_wet)), (0, 0)))

    stereo_ir[:, 0] = stereo_ir[:, 0] * (1.0 - wet_mix) + stereo_wet[:, 0] * wet_mix
    stereo_ir[:, 1] = stereo_ir[:, 1] * (1.0 - wet_mix) + stereo_wet[:, 1] * wet_mix

    env = np.abs(stereo_ir[:, 0]) + np.abs(stereo_ir[:, 1])
    max_amp = np.max(env)
    if max_amp > 0:
        threshold = max_amp * 0.001 
        active_indices = np.where(env > threshold)[0]
        if len(active_indices) > 0:
            crop_idx = min(len(stereo_ir), active_indices[-1] + int(sample_rate * 0.05))
            stereo_ir = stereo_ir[:crop_idx]

    fade_len = min(int(0.01 * sample_rate), len(stereo_ir))
    if fade_len > 0:
        stereo_ir[-fade_len:] *= (np.linspace(1.0, 0.0, fade_len) ** 2)[:, np.newaxis]

    max_val = np.max(np.abs(stereo_ir))
    if max_val > 0: 
        stereo_ir = (stereo_ir / max_val) * 0.6

    return stereo_ir
# --- END OF FILE engine/core_taichi.py ---