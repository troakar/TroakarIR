# dlc/drums/drums_engine.py
import os
import re
import numpy as np
import taichi as ti
from scipy.signal import lfilter, butter, fftconvolve

from engine.tactile import generate_tactile_profile
from engine.grid_builder import build_heterogeneous_grids
from config.materials import MATERIAL_PHYSICS

def get_effective_properties(mat: dict) -> dict:
    density = mat.get("density", 0.5)
    E_long = mat.get("E_long", 10.0)
    E_trans = mat.get("E_trans", mat.get("E_long", 10.0))
    loss = mat.get("loss_factor", 0.02)
    visco = mat.get("visco_gamma", 1e-5)
    poisson = mat.get("poisson", 0.3)

    tactile = mat.get("tactile_profile", {
        "fibrousness": 0.0,
        "fluidity": 0.0,
        "granularity": 0.0,
        "brittleness": 0.0,
    }).copy()

    inclusions = mat.get("inclusions", [])
    total_inc_ratio = sum(float(inc.get("density_ratio", 0.0)) for inc in inclusions)
    base_ratio = max(0.01, 1.0 - total_inc_ratio)

    for inc in inclusions:
        inc_mat = inc.get("material", {})
        if isinstance(inc_mat, str):
            inc_mat = MATERIAL_PHYSICS.get(inc_mat, {})

        ratio = float(inc.get("density_ratio", 0.0))
        if ratio <= 0.0 or not inc_mat:
            continue

        density = density * (1.0 - ratio) + inc_mat.get("density", density) * ratio
        E_long = E_long * (1.0 - ratio) + inc_mat.get("E_long", E_long) * ratio
        E_trans = E_trans * (1.0 - ratio) + inc_mat.get("E_trans", E_trans) * ratio
        loss = loss * (1.0 - ratio) + inc_mat.get("loss_factor", loss) * ratio
        visco = visco * (1.0 - ratio) + inc_mat.get("visco_gamma", visco) * ratio
        poisson = poisson * (1.0 - ratio) + inc_mat.get("poisson", poisson) * ratio

        inc_tactile = inc_mat.get("tactile_profile", {})
        for key in ["fibrousness", "fluidity", "granularity", "brittleness"]:
            tactile[key] = tactile.get(key, 0.0) * (1.0 - ratio) + inc_tactile.get(key, 0.0) * ratio

    effective_mat = mat.copy()
    effective_mat.update({
        "density": density,
        "E_long": E_long,
        "E_trans": E_trans,
        "loss_factor": loss,
        "visco_gamma": visco,
        "poisson": poisson,
        "tactile_profile": tactile,
    })

    for layer in ["granular", "fibrous", "fluid"]:
        if layer in effective_mat and isinstance(effective_mat[layer], dict):
            effective_mat[layer] = effective_mat[layer].copy()
            effective_mat[layer]["intensity"] = effective_mat[layer].get("intensity", 0.0) * base_ratio

    return effective_mat

def note_to_freq(note_name: str) -> float:
    note_name = note_name.strip()
    match = re.match(r"^([A-G](?:#|b)?)(-?\d+)$", note_name)
    if not match:
        raise ValueError(f"Unsupported note name: {note_name}")

    name, octave_text = match.groups()
    octave = int(octave_text)
    flat_to_sharp = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    name = flat_to_sharp.get(name, name)

    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    key_number = notes.index(name) + (octave + 1) * 12
    return 440.0 * (2.0 ** ((key_number - 69) / 12.0))

def init_taichi_headless():
    try:
        taichi_is_ready = ti.lang.impl.get_runtime().prog is not None
    except Exception:
        taichi_is_ready = False

    if taichi_is_ready:
        return

    try:
        ti.init(arch=ti.gpu, device_memory_GB=2.0, log_level=ti.WARN)
    except Exception:
        ti.init(arch=ti.cpu, log_level=ti.WARN)

init_taichi_headless()

N_MAX = 512
N_REF = 128

p_A = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_A_past = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_A_future = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
mask_A = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

p_B = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_B_past = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
p_B_future = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
mask_B = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

stat_vol_A = ti.field(dtype=ti.f32, shape=())
stat_vol_B = ti.field(dtype=ti.f32, shape=())
stat_strain_A = ti.field(dtype=ti.f32, shape=())

c_sq_x_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
c_sq_y_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
loss_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
visco_A_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

c_sq_x_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
c_sq_y_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
loss_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))
visco_B_field = ti.field(dtype=ti.f32, shape=(N_MAX, N_MAX))

@ti.kernel
def init_drums_fields(N: ti.i32):
    stat_vol_A[None] = 0.0
    stat_vol_B[None] = 0.0
    stat_strain_A[None] = 0.0
    for i, j in ti.ndrange(N, N):
        p_A[i, j] = 0.0
        p_A_past[i, j] = 0.0
        p_A_future[i, j] = 0.0
        p_B[i, j] = 0.0
        p_B_past[i, j] = 0.0
        p_B_future[i, j] = 0.0

@ti.kernel
def compute_drums_stats(N: ti.i32):
    stat_vol_A[None] = 0.0
    stat_vol_B[None] = 0.0
    stat_strain_A[None] = 0.0

    for i, j in ti.ndrange(N, N):
        stat_vol_A[None] += p_A[i, j] * mask_A[i, j]
        if i > 0 and i < N - 1 and j > 0 and j < N - 1 and mask_A[i, j] > 0.5:
            dx = p_A[i + 1, j] - p_A[i, j]
            dy = p_A[i, j + 1] - p_A[i, j]
            stat_strain_A[None] += dx * dx + dy * dy

    for i, j in ti.ndrange(N, N):
        stat_vol_B[None] += p_B[i, j] * mask_B[i, j]

@ti.kernel
def step_drums_fdtd(
    N: ti.i32,
    coupling_k: ti.f32,
    vol_A: ti.f32,
    vol_B: ti.f32,
    vol_A_delayed: ti.f32,
    vol_B_delayed: ti.f32,
    strike_x_A: ti.i32,
    strike_y_A: ti.i32,
    strike_val_A: ti.f32,
    radius_A: ti.f32,
    bend_A: ti.f32,
    strain_A: ti.f32,
    damp_A_val: ti.f32,
    pitch_drop_mod: ti.f32,
):
    p_air_A = -coupling_k * (vol_A + vol_B_delayed) * 0.08
    p_air_B = -coupling_k * (vol_A_delayed + vol_B) * 0.08
    safe_r_A = ti.max(radius_A, 0.001)

    for i, j in ti.ndrange(N, N):
        if i > 0 and i < N - 1 and j > 0 and j < N - 1 and mask_A[i, j] > 0.5:
            base_cx = c_sq_x_A_field[i, j]
            base_cy = c_sq_y_A_field[i, j]
            local_loss = loss_A_field[i, j]
            local_visco = visco_A_field[i, j]

            dyn_c_x = base_cx * (1.0 + bend_A * strain_A * pitch_drop_mod)
            dyn_c_y = base_cy * (1.0 + bend_A * strain_A * pitch_drop_mod)

            # CFL LIMITER
            total_c = dyn_c_x + dyn_c_y + local_visco
            if total_c > 0.49:
                scale = 0.49 / total_c
                dyn_c_x *= scale
                dyn_c_y *= scale

            lap_curr_x = p_A[i - 1, j] + p_A[i + 1, j] - 2.0 * p_A[i, j]
            lap_curr_y = p_A[i, j - 1] + p_A[i, j + 1] - 2.0 * p_A[i, j]
            lap_past_x = p_A_past[i - 1, j] + p_A_past[i + 1, j] - 2.0 * p_A_past[i, j]
            lap_past_y = p_A_past[i, j - 1] + p_A_past[i, j + 1] - 2.0 * p_A_past[i, j]

            lap_curr = dyn_c_x * lap_curr_x + dyn_c_y * lap_curr_y
            lap_past = dyn_c_x * lap_past_x + dyn_c_y * lap_past_y

            force = lap_curr + local_visco * (lap_curr - lap_past)
            force += p_air_A * mask_A[i, j]

            if radius_A > 0.1:
                dist = ti.cast((i - strike_x_A) ** 2 + (j - strike_y_A) ** 2, ti.f32)
                if dist < radius_A ** 2:
                    force += strike_val_A * ti.exp(-dist / (safe_r_A ** 2 * 0.5))

            total_loss = local_loss + damp_A_val
            p_A_future[i, j] = (2.0 * p_A[i, j] - p_A_past[i, j] * (1.0 - total_loss) + force) / (1.0 + total_loss)
        else:
            p_A_future[i, j] = 0.0

    for i, j in ti.ndrange(N, N):
        if i > 0 and i < N - 1 and j > 0 and j < N - 1 and mask_B[i, j] > 0.5:
            base_cx = c_sq_x_B_field[i, j]
            base_cy = c_sq_y_B_field[i, j]
            local_loss = loss_B_field[i, j]
            local_visco = visco_B_field[i, j]

            # CFL LIMITER B
            total_c_B = base_cx + base_cy + local_visco
            if total_c_B > 0.49:
                scale = 0.49 / total_c_B
                base_cx *= scale
                base_cy *= scale

            lap_curr_x = p_B[i - 1, j] + p_B[i + 1, j] - 2.0 * p_B[i, j]
            lap_curr_y = p_B[i, j - 1] + p_B[i, j + 1] - 2.0 * p_B[i, j]
            lap_past_x = p_B_past[i - 1, j] + p_B_past[i + 1, j] - 2.0 * p_B_past[i, j]
            lap_past_y = p_B_past[i, j - 1] + p_B_past[i, j + 1] - 2.0 * p_B_past[i, j]

            lap_curr = base_cx * lap_curr_x + base_cy * lap_curr_y
            lap_past = base_cx * lap_past_x + base_cy * lap_past_y

            force = lap_curr + local_visco * (lap_curr - lap_past)
            force += p_air_B * mask_B[i, j]

            total_loss = local_loss + damp_A_val * 0.5
            p_B_future[i, j] = (2.0 * p_B[i, j] - p_B_past[i, j] * (1.0 - total_loss) + force) / (1.0 + total_loss)
        else:
            p_B_future[i, j] = 0.0

@ti.kernel
def apply_drums_tactile_forces(
    N: ti.i32,
    gran: ti.f32,
    brit: ti.f32,
    fibr: ti.f32,
    fluid: ti.f32,
    strike_force: ti.f32,
):
    limit = 75 + ti.cast(strike_force * 100.0, ti.i32)
    for idx in range(180):
        if idx < limit:
            i = ti.cast(ti.random() * N, ti.i32)
            j = ti.cast(ti.random() * N, ti.i32)
            if i > 0 and i < N - 1 and j > 0 and j < N - 1 and mask_A[i, j] > 0.5:
                strain = ti.abs(p_A[i, j] - p_A_past[i, j])
                if gran > 0.0 and strain > 0.00001 and ti.random() < gran:
                    p_A_future[i, j] += (ti.random() - 0.5) * gran * strain * 0.35
                if brit > 0.0 and strain > 0.0001 and ti.random() < brit * 0.1:
                    p_A_future[i, j] += (ti.random() - 0.5) * brit * strain * 1.5
                    p_A_future[i, j] *= 0.99
                if fibr > 0.0 and strain > 0.00005 and ti.random() < fibr:
                    p_A_future[i, j] += (ti.random() - 0.5) * fibr * strain * 0.5
                if fluid > 0.0 and strain > 0.00001 and ti.random() < fluid * 0.1:
                    p_A_future[i, j] += (ti.random() - 0.5) * fluid * strain * 0.8

@ti.kernel
def update_drums_fields(N: ti.i32):
    for i, j in ti.ndrange(N, N):
        p_A_past[i, j] = p_A[i, j]
        p_A[i, j] = p_A_future[i, j]
        p_B_past[i, j] = p_B[i, j]
        p_B[i, j] = p_B_future[i, j]

def apply_acoustic_shell(membrane_signal, fs, mat_properties, note_hz, drum_type, strike_force=1.0, autotune_shell=False, ring_mod=0.0):
    if "cymbal" in drum_type or "hihat" in drum_type:
        return np.zeros_like(membrane_signal)

    E_long = mat_properties.get("E_long", 10.0)
    density = mat_properties.get("density", 0.5)
    loss = max(0.0001, mat_properties.get("loss_factor", 0.02))

    v_sound = np.sqrt((E_long * 1e9) / (density * 1000.0))
    f_helmholtz = np.clip(note_hz * 1.0, 40.0, 150.0)

    base_shell = np.clip(v_sound * 0.06, 150.0, 4500.0)
    if autotune_shell and note_hz > 0:
        ratio = base_shell / note_hz
        consonant_multipliers = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
        best_mult = min(consonant_multipliers, key=lambda x: abs(x - ratio))
        base_shell = note_hz * best_mult

    freqs = [f_helmholtz, base_shell, base_shell * 1.61, base_shell * 2.3, base_shell * 3.5, base_shell * 5.4, base_shell * 8.1]

    dynamic_q_scale = 0.76 + 0.24 * (strike_force ** 0.5)
    base_q = (0.85 / loss) * dynamic_q_scale

    q_helmholtz = np.clip(base_q * 2.2, 30.0, 110.0)
    q_factors = [q_helmholtz, base_q, base_q * 1.1, base_q * 1.3, base_q * 1.5, base_q * 1.8, base_q * 2.0]

    if ring_mod > 0:
        q_factors[0] *= (1.0 + ring_mod * 1.5)
        boost_mult = 3.5 if drum_type == "snare" else 1.8
        q_factors[1] *= (1.0 + ring_mod * boost_mult * (strike_force ** 1.2))
        q_factors[2] *= (1.0 + ring_mod * boost_mult * (strike_force ** 1.2))

    stiffness_ratio = np.clip(E_long / 10.0, 0.1, 30.0)
    shell_gain = 0.06 / np.sqrt(stiffness_ratio)
    gains = [0.35, shell_gain, shell_gain * 0.7, shell_gain * 0.5, shell_gain * 0.3, shell_gain * 0.15, shell_gain * 0.08]

    if drum_type == "snare":
        q_factors[1] *= 1.5
        q_factors[2] *= 1.8
        gains[0] *= 0.65
        gains[1] *= 1.40
        gains[2] *= 1.20
    elif drum_type == "kick":
        gains[0] *= 1.5
        q_factors[0] *= 1.2
        gains[1] *= 0.6
        gains[2] *= 0.4
    elif "tom" in drum_type:
        gains[0] *= 1.1
        gains[1] *= 1.2
        q_factors[1] *= 1.2

    # 1. Задаем естественное время затухания (T60) в секундах для каждого типа удара
    if drum_type == "snare":
        max_t60 = 0.22
    elif drum_type == "kick":
        max_t60 = 0.40
    elif "tom" in drum_type:
        max_t60 = 0.30
    else:
        max_t60 = 0.35
        
    # 2. ДИНАМИЧЕСКИЙ Q-CLAMP (Связываем Q-фактор с частотой фильтра)
    clamped_q_factors = []
    for f, q in zip(freqs, q_factors):
        q_max = (max_t60 * np.pi * f) / 6.9078
        q_clamped = np.clip(q, 3.0, q_max)
        q_clamped = np.clip(q_clamped, 3.0, 150.0) 
        clamped_q_factors.append(q_clamped)
        
    gains = [np.clip(g, 0.0, 2.5) for g in gains]
    
    shell_output = np.zeros_like(membrane_signal)
    
    for f, q, g in zip(freqs, clamped_q_factors, gains):
        if f < fs / 2.1:
            w0 = 2.0 * np.pi * f / fs
            alpha = np.sin(w0) / (2.0 * q)
            a0 = 1.0 + alpha
            b = [np.sin(w0) / (2.0 * a0), 0.0, -np.sin(w0) / (2.0 * a0)]
            a = [1.0, -2.0 * np.cos(w0) / a0, (1.0 - alpha) / a0]
            shell_output += lfilter(b, a, membrane_signal) * g
        
    return shell_output

def apply_meat_and_fat(sig, fs, drum_type, strike_force, saturation=0.0, skin_mat=None, shell_mat=None, shell_attack=0.5, shell_sustain=1.0, membrane_snap=1.0):
    out = sig.copy()
    t_arr = np.arange(len(out)) / fs
    punch_env = 1.0 + 0.45 * np.exp(-t_arr / 0.012) * strike_force
    out *= punch_env

    if "cymbal" not in drum_type and "hihat" not in drum_type:
        disp_stages = 2
        c = -0.15 if drum_type == "snare" else -0.65
        for _ in range(disp_stages):
            out = lfilter([c, 1.0], [1.0, c], out)

    if "cymbal" in drum_type or "hihat" in drum_type:
        room_mix = 0.0
    elif drum_type == "kick":
        room_mix = 0.05
    else:
        room_mix = 0.15

    if room_mix > 0:
        delay_samples = int(0.028 * fs)
        room = np.zeros_like(out)
        if len(out) > delay_samples:
            room[delay_samples:] += out[:-delay_samples] * (room_mix * 0.7)

        b_r, a_r = butter(1, 4000.0 / (fs / 2.0), btype="low")
        out += lfilter(b_r, a_r, room)

    E_skin = skin_mat.get("E_long", 1.5) if skin_mat else 1.5
    den_skin = skin_mat.get("density", 1.0) if skin_mat else 1.0
    loss_skin = skin_mat.get("loss_factor", 0.05) if skin_mat else 0.05

    E_shell = shell_mat.get("E_long", 11.2) if shell_mat else 11.2
    den_shell = shell_mat.get("density", 0.64) if shell_mat else 0.64
    loss_shell = shell_mat.get("loss_factor", 0.018) if shell_mat else 0.018

    if "cymbal" in drum_type or "hihat" in drum_type:
        E_eff, den_eff, loss_eff = E_shell, den_shell, loss_shell
    else:
        E_eff = (E_skin * 0.75) + (E_shell * 0.25)
        den_eff = (den_skin * 0.75) + (den_shell * 0.25)
        loss_eff = (loss_skin * 0.75) + (loss_shell * 0.25)

    v_sound = np.sqrt(max(E_eff, 0.01) / max(den_eff, 0.1))
    click_freq = 600.0 + 450.0 * (v_sound ** 1.5)
    click_freq = np.clip(click_freq, 600.0, 12000.0)

    damp_freq = 20000.0 * np.exp(-12.0 * loss_eff)
    damp_freq = np.clip(damp_freq, click_freq + 1500.0, fs / 2.1)

    b_hi, a_hi = butter(2, click_freq / (fs / 2.0), btype="high")
    hi_layer = lfilter(b_hi, a_hi, sig)

    b_damp, a_damp = butter(1, damp_freq / (fs / 2.0), btype="low")
    hi_layer = lfilter(b_damp, a_damp, hi_layer)

    try:
        from engine.shell_texture import apply_dynamic_shell_texture
        if "cymbal" in drum_type or "hihat" in drum_type:
            shell_texture = None
        else:
            shell_texture = apply_dynamic_shell_texture(shell_mat, fs, len(out), strike_force, saturation, drum_type) if shell_mat else None
    except Exception:
        shell_texture = None

    if shell_texture is not None:
        if drum_type == "snare": tex_mix = 0.50
        elif drum_type == "kick": tex_mix = 0.35
        elif "tom" in drum_type: tex_mix = 0.35
        else: tex_mix = 0.25

        tex_mix *= (0.5 + 0.5 * (strike_force ** 1.5)) * (1.0 + saturation)

        t_tex = np.arange(len(shell_texture)) / fs
        env_attack = np.exp(-t_tex / 0.04)
        shell_env = (env_attack * shell_attack) + ((1.0 - env_attack) * shell_sustain)
        out += shell_texture * tex_mix * shell_env

    headroom = 0.4
    saturation_drive = 1.0 + (saturation * 0.15)
    out = np.tanh(out * headroom * saturation_drive) / (headroom * saturation_drive)

    if drum_type == "snare": click_decay, snap_boost = 0.25, 2.0
    elif drum_type == "kick": click_decay, snap_boost = 0.08, 1.5
    else: click_decay, snap_boost = 0.04, 1.0

    click_env = np.exp(-t_arr / click_decay)
    out += hi_layer * click_env * (0.15 + membrane_snap * 0.35) * snap_boost * (strike_force ** 2.0)

    return out

def apply_3d_studio_room(mono_signal, fs):
    import pyroomacoustics as pra
    room_dim = [5.0, 6.0, 3.0]
    mat = pra.Material(0.45, 0.1)
    room = pra.ShoeBox(room_dim, fs=fs, materials=mat, max_order=8)
    source_pos = [2.5, 2.0, 0.8]
    room.add_source(source_pos, signal=mono_signal)

    mic_array = np.array([
        [source_pos[0] - 0.23, source_pos[1] + 1.48, 1.45],
        [source_pos[0] + 0.17, source_pos[1] + 1.52, 1.55],
    ])
    room.add_microphone_array(mic_array.T)
    room.simulate()

    stereo_room = room.mic_array.signals.T
    if len(stereo_room) > len(mono_signal):
        stereo_room = stereo_room[:len(mono_signal)]
    else:
        stereo_room = np.pad(stereo_room, ((0, len(mono_signal) - len(stereo_room)), (0, 0)))
    return stereo_room

def declick_ar_model(sig, fs, ms_window=5.0, slew_factor=2.5, cutoff_hz=8500.0):
    from scipy.ndimage import uniform_filter1d
    n_samples = len(sig)
    nyquist = fs / 2.0

    b, a = butter(2, cutoff_hz / nyquist, btype="high")
    hf = lfilter(b, a, sig)
    lf = sig - hf

    dy = np.diff(hf)
    dy = np.concatenate(([0.0], dy))

    window_samples = max(5, int((ms_window / 1000.0) * fs))
    smooth_env = uniform_filter1d(np.abs(dy), size=window_samples)
    max_slew = np.clip(slew_factor * smooth_env, 0.0005, 1.0)

    cleaned_hf = hf.copy()
    for i in range(1, n_samples):
        step = cleaned_hf[i] - cleaned_hf[i - 1]
        limit = max_slew[i]
        if np.abs(step) > limit:
            cleaned_hf[i] = cleaned_hf[i - 1] + np.sign(step) * limit

    return lf + cleaned_hf, {"total_clicks": 1, "frames_with_clicks": 1}

def generate_air_column_ir(base_shell_hz, fs=44100, duration=0.4, drum_type="snare"):
    t_arr = np.arange(int(fs * duration)) / fs
    air_ir = np.zeros_like(t_arr)
    freqs = [base_shell_hz, base_shell_hz * 2.0, base_shell_hz * 3.0]

    if drum_type == "snare":
        decay_times, amplitudes = [0.100, 0.045, 0.020], [1.0, 0.55, 0.25]
    elif "tom" in drum_type:
        decay_times, amplitudes = [0.200, 0.080, 0.040], [1.0, 0.60, 0.30]
    else: 
        decay_times, amplitudes = [0.080, 0.030, 0.015], [1.0, 0.30, 0.10]

    for f, tau, amp in zip(freqs, decay_times, amplitudes):
        if f < fs / 2.1:
            phase = np.random.uniform(0, 2 * np.pi)
            air_ir += amp * np.exp(-t_arr / tau) * np.sin(2 * np.pi * f * t_arr + phase)

    reflections = [int(0.0015 * fs), int(0.0030 * fs), int(0.0045 * fs)]
    ref_gains = [0.35, 0.18, 0.08]

    for delay, gain in zip(reflections, ref_gains):
        if len(air_ir) > delay:
            air_ir[delay:] += air_ir[:-delay] * gain

    b, a = butter(2, 7500.0 / (fs / 2.0), btype="low")
    air_ir = lfilter(b, a, air_ir)

    if np.max(np.abs(air_ir)) > 0: air_ir /= np.max(np.abs(air_ir))
    return air_ir

_BODY_IR_CACHE = {}

def generate_body_ir(shell_mat_dict, base_shell_hz, fs=44100, duration=0.4, drum_type="snare"):
    from engine.core_taichi import generate_fdtd_ir

    ir_instrument = {
        "f0": base_shell_hz,
        "resonator_template": "drum_shell",
        "mask_image": "circle",
        "sympathetic_strings": [],
        "base_size": 0.4
    }

    exciter_impulse = np.zeros(int(fs * duration))

    if drum_type == "snare":
        pulse_len, dirac_gain, noise_gain, cutoff_hz = int(0.0025 * fs), 0.60, 0.40, 1400.0
    elif drum_type == "kick":
        pulse_len, dirac_gain, noise_gain, cutoff_hz = int(0.0050 * fs), 0.80, 0.20, 200.0
    else: 
        pulse_len, dirac_gain, noise_gain, cutoff_hz = int(0.0030 * fs), 0.70, 0.30, 600.0

    noise = np.random.normal(0, 1.0, pulse_len)
    env = (1.0 - np.linspace(0, 1, pulse_len)) ** 2
    b, a = butter(2, cutoff_hz / (fs / 2.0), btype="high")
    filtered_noise = lfilter(b, a, noise * env)
    if np.max(np.abs(filtered_noise)) > 0: filtered_noise /= np.max(np.abs(filtered_noise))

    exciter_impulse[0] = dirac_gain
    exciter_impulse[:pulse_len] += filtered_noise * noise_gain
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
        show_gui=False,
    )

    body_ir_mono = (body_ir_stereo[:, 0] + body_ir_stereo[:, 1]) * 0.5
    if np.max(np.abs(body_ir_mono)) > 0: body_ir_mono /= np.max(np.abs(body_ir_mono))

    target_len = len(body_ir_mono)
    air_ir = generate_air_column_ir(base_shell_hz, fs, target_len / fs, drum_type=drum_type)

    if len(air_ir) > target_len: air_ir = air_ir[:target_len]
    elif len(air_ir) < target_len: air_ir = np.pad(air_ir, (0, target_len - len(air_ir)))

    mixed_ir = 0.4 * body_ir_mono + 0.6 * air_ir
    if np.max(np.abs(mixed_ir)) > 0: mixed_ir /= np.max(np.abs(mixed_ir))

    return mixed_ir

def apply_body_convolution(input_signal, ir_signal, fs, mix=0.35):
    if mix <= 0.0 or len(ir_signal) == 0: return input_signal
    b, a = butter(4, 900.0 / (fs/2.0), btype="high")
    ir_highpass = lfilter(b, a, ir_signal)

    ir_len = int(0.15 * fs)
    ir_faded = ir_highpass[:ir_len] * (np.linspace(1.0, 0.0, min(ir_len, len(ir_highpass))) ** 2) if len(ir_highpass) > ir_len else ir_highpass
    if np.max(np.abs(ir_faded)) > 0: ir_faded /= np.max(np.abs(ir_faded))

    wet_signal = fftconvolve(input_signal, ir_faded, mode="full")[:len(input_signal)]
    if np.max(np.abs(wet_signal)) > 0: wet_signal *= np.max(np.abs(input_signal)) / np.max(np.abs(wet_signal))
    return input_signal * (1.0 - mix) + wet_signal * mix

def apply_internal_bells(membrane_signal, acceleration_signal, fs, material_name="steel", mix=0.15, rr_index=1, strike_force=1.0):
    acoustic_mix = (mix ** 1.8) * 0.45
    kinetic_energy = strike_force ** 1.5
    seed = int(hash(material_name) % 10000) + int(rr_index * 997) + int(strike_force * 100)
    rng = np.random.RandomState(seed)

    mat = MATERIAL_PHYSICS.get(material_name, MATERIAL_PHYSICS.get("steel", {}))
    E, rho, loss = float(mat.get("E_long", 200.0)), float(mat.get("density", 7.8)), float(mat.get("loss_factor", 0.0005))
    f0 = np.clip(1400.0 * np.sqrt(max(0.1, E) / max(0.1, rho)), 2000.0, 7500.0)

    num_samples = len(membrane_signal)
    hit_idx = int(np.argmax(np.abs(acceleration_signal))) if np.max(np.abs(acceleration_signal)) > 0 else 0
    t_decay = np.maximum(0, np.arange(num_samples) - hit_idx) / fs

    base_freqs = [f0, f0 * 1.48, f0 * 2.12, f0 * 2.95]
    gains = [1.0, 0.75 * (kinetic_energy ** 0.3), 0.45 * (kinetic_energy ** 0.5), 0.20 * (kinetic_energy ** 0.8)]
    q_bell = np.clip((0.5 / max(1e-5, loss)) * (0.15 + 0.85 * kinetic_energy) * (0.3 + 0.7 * mix), 5.0, 400.0)

    abs_acc = np.abs(acceleration_signal)
    main_excitation = np.zeros_like(abs_acc)
    threshold = 0.0003 * np.sqrt(rho)
    active_mask = abs_acc > threshold
    main_excitation[active_mask] = abs_acc[active_mask] - threshold

    bounce_env = np.exp(-t_decay / (0.05 + 0.35 * (strike_force * mix))) * kinetic_energy
    bell_output = np.zeros(num_samples)

    for _ in range(4):
        bounce_prob = rng.rand(num_samples)
        bounce_triggers = (bounce_prob < (rng.uniform(0.0005, 0.002) * bounce_env)).astype(np.float32)
        bell_exc = (main_excitation + rng.uniform(0.1, 0.9, num_samples) * bounce_triggers * bounce_env) * rng.normal(0.4, 0.6, num_samples)

        bell_layer = np.zeros(num_samples)
        for f, g in zip(base_freqs, gains):
            f_det = f * rng.uniform(0.95, 1.05)
            if f_det < fs / 2.1:
                w0 = 2.0 * np.pi * f_det / fs
                alpha = np.sin(w0) / (2.0 * q_bell * rng.uniform(0.8, 1.2))
                a0 = 1.0 + alpha
                b, a = [np.sin(w0) / (2.0 * a0), 0.0, -np.sin(w0) / (2.0 * a0)], [1.0, -2.0 * np.cos(w0) / a0, (1.0 - alpha) / a0]
                bell_layer += lfilter(b, a, bell_exc) * g

        delay_samples = int(rng.uniform(0.0, 0.008) * fs)
        if delay_samples > 0:
            bell_layer = np.roll(bell_layer, delay_samples)
            bell_layer[:delay_samples] = 0
        bell_output += bell_layer * 0.25

    micro_excitation = np.zeros_like(abs_acc)
    micro_threshold = 0.00012 * np.sqrt(rho)
    micro_active_mask = abs_acc > micro_threshold
    micro_excitation[micro_active_mask] = abs_acc[micro_active_mask] - micro_threshold

    micro_bounce_env = np.exp(-t_decay / (0.03 + 0.18 * (strike_force * mix))) * kinetic_energy
    q_micro = np.clip(q_bell * 0.12 * (0.4 + 0.6 * mix), 4.0, 45.0)
    micro_bell_output = np.zeros(num_samples)

    for _ in range(12):
        f_micro = f0 * rng.uniform(1.65, 2.75)
        micro_prob = rng.rand(num_samples)
        micro_triggers = (micro_prob < (0.004 * micro_bounce_env)).astype(np.float32)
        micro_exc = (micro_excitation * 0.4 + rng.uniform(0.05, 0.35, num_samples) * micro_triggers * micro_bounce_env) * rng.normal(0.4, 0.6, num_samples)

        if f_micro < fs / 2.1:
            w0 = 2.0 * np.pi * f_micro / fs
            alpha = np.sin(w0) / (2.0 * q_micro)
            a0 = 1.0 + alpha
            b, a = [np.sin(w0) / (2.0 * a0), 0.0, -np.sin(w0) / (2.0 * a0)], [1.0, -2.0 * np.cos(w0) / a0, (1.0 - alpha) / a0]
            micro_layer = lfilter(b, a, micro_exc)

            delay_samples = int(rng.uniform(0.003, 0.018) * fs)
            if delay_samples > 0:
                micro_layer = np.roll(micro_layer, delay_samples)
                micro_layer[:delay_samples] = 0
            micro_bell_output += micro_layer

    nyquist = fs / 2.0
    b_hp, a_hp = butter(2, 2500.0 / nyquist, btype="high")
    bell_output = lfilter(b_hp, a_hp, bell_output)

    lp_cutoff = np.clip(2200.0 + 15000.0 * (kinetic_energy ** 0.8) * (0.4 + 0.6 * mix), 2000.0, nyquist - 200.0)
    b_lp, a_lp = butter(2, lp_cutoff / nyquist, btype="low")
    bell_output = lfilter(b_lp, a_lp, bell_output)

    b_hp_m, a_hp_m = butter(2, 5000.0 / nyquist, btype="high")
    micro_bell_output = lfilter(b_hp_m, a_hp_m, micro_bell_output)
    b_lp_m, a_lp_m = butter(2, 7500.0 / nyquist, btype="low")
    micro_bell_output = lfilter(b_lp_m, a_lp_m, micro_bell_output)

    max_main = np.max(np.abs(bell_output))
    if max_main > 0: bell_output /= max_main

    max_micro = np.max(np.abs(micro_bell_output))
    if max_micro > 0: micro_bell_output = (micro_bell_output / max_micro) * 0.18

    combined_bells = bell_output * 0.82 + micro_bell_output * 0.18
    dry_env = lfilter([0.05], [1.0, -0.95], np.abs(membrane_signal))
    duck_factor = np.clip(1.0 - (dry_env / (np.max(dry_env) + 1e-9)) * 1.4, 0.0, 1.0)
    combined_bells *= duck_factor

    fade_len = min(int(fs * 0.35), num_samples // 3)
    if fade_len > 0:
        combined_bells[-fade_len:] *= np.linspace(1.0, 0.0, fade_len) ** 2

    max_total = np.max(np.abs(combined_bells))
    if max_total > 0:
        combined_bells /= max_total
        combined_bells *= np.clip(np.max(main_excitation) * 3.5, 0.0, 1.0)

    return membrane_signal + combined_bells * acoustic_mix

def apply_snare_wires(bottom_accel, fs, tension=0.5, mix=0.5, strike_force=1.0):
    if mix <= 0.0: return np.zeros_like(bottom_accel)
    threshold = 0.0001 + tension * 0.001
    abs_accel = np.abs(bottom_accel)
    active_mask = abs_accel > threshold

    exc = np.zeros_like(bottom_accel)
    exc[active_mask] = abs_accel[active_mask] - threshold
    
    t = np.arange(len(bottom_accel)) / fs
    env = np.exp(-t / (0.35 - tension * 0.20))
    snare_raw = np.random.normal(0, 1.0, len(bottom_accel)) * exc * env * 2500.0

    b_hp, a_hp = butter(2, 2500.0 / (fs / 2.0), btype="high")
    snare_filtered = lfilter(b_hp, a_hp, snare_raw)

    b_bp, a_bp = butter(2, [3500.0 / (fs / 2.0), 10000.0 / (fs / 2.0)], btype="bandpass")
    snare_body = lfilter(b_bp, a_bp, snare_filtered)

    output = snare_filtered * 0.3 + snare_body * 0.7
    return np.tanh(output * 2.0) * mix * (strike_force ** 0.8)

def apply_tambourine_bells(sig, fs, mix=0.15, force=1.0):
    if mix <= 0.0: return np.zeros_like(sig)
    t = np.arange(len(sig)) / fs
    env = lfilter([0.05], [1.0, -0.95], np.abs(sig))
    noise = np.random.normal(0, 1.0, len(sig)) * env * 50.0
    b, a = butter(2, [5000.0 / (fs / 2.0), 9000.0 / (fs / 2.0)], btype="bandpass")
    bells = lfilter(b, a, noise)
    return bells * mix * np.exp(-t / 0.15) * (force ** 1.5)

def synthesize_drum_hit(
    drum_type="snare", note="G2", beater_type="wood_stick", strike_force=1.0,
    head_mat_name="animal_skin", shell_mat_name="maple", cym_mat_name="bronze",
    shell_depth_inches=5.5, muffling=0.1, tactile_boost=0.5, snare_tension=0.5,
    use_bells=False, bell_mix=0.0, duration=1.5, fs=44100, N_grid=256,
    show_gui=True, yield_cb=None, saturation=0.0, mat_boost=0.0,
    membrane_tactile=1.0, membrane_snap=1.0, shell_attack=0.5, shell_sustain=1.0,
    rr_index=1, autotune_shell=False, ring_mod=0.0, body_polish_mix=0.20, bell_material="steel",
):
    init_taichi_headless()

    if show_gui and os.environ.get("DISPLAY") is None and os.name != "nt":
        show_gui = False

    N_grid = min(N_grid, N_MAX)
    init_drums_fields(N_grid)

    freq_A = note_to_freq(note)
    is_cymbal = "cymbal" in drum_type or "hihat" in drum_type

    head_mat_raw = MATERIAL_PHYSICS.get(head_mat_name, MATERIAL_PHYSICS["animal_skin"])
    shell_mat_raw = MATERIAL_PHYSICS.get(shell_mat_name, MATERIAL_PHYSICS["maple"])
    cym_mat_raw = MATERIAL_PHYSICS.get(cym_mat_name, MATERIAL_PHYSICS["steel"])

    mat_raw = get_effective_properties(cym_mat_raw if is_cymbal else head_mat_raw)
    shell_mat_for_processing = get_effective_properties(cym_mat_raw if is_cymbal else shell_mat_raw)
    grid_mat_raw = cym_mat_raw if is_cymbal else head_mat_raw

    if rr_index > 1:
        state = np.random.RandomState(int(rr_index * 137 + strike_force * 997))
        strike_force = np.clip(strike_force + state.uniform(-0.04, 0.04), 0.05, 1.0)

    r_mask = np.zeros((N_MAX, N_MAX), dtype=np.float32)
    center = N_grid / 2.0
    radius = 0.45 * N_grid
    for i in range(N_grid):
        for j in range(N_grid):
            if (i - center) ** 2 + (j - center) ** 2 < radius ** 2:
                r_mask[i, j] = 1.0

    mask_A.from_numpy(r_mask)
    mask_B.from_numpy(r_mask)
    grid_area = np.pi * (radius ** 2)

    if drum_type == "kick": freq_B = freq_A * 0.9
    elif not is_cymbal: freq_B = freq_A * 1.35
    else: freq_B = freq_A
        
    M = int(np.ceil(max(freq_A, freq_B) * np.pi * N_grid / (2.4048 * fs) / 0.35))
    if is_cymbal: M = max(M, 4)

    grids_raw, _ = build_heterogeneous_grids(r_mask, grid_mat_raw, MATERIAL_PHYSICS)

    base_v_sq = grid_mat_raw.get("E_long", 10.0) / max(grid_mat_raw.get("density", 1.0), 1e-6)
    v_sq_ratio_map = (grids_raw["E_l"] / (grids_raw["rho"] + 1e-9)) / max(base_v_sq, 1e-9)

    sum_E_map = grids_raw["E_l"] + grids_raw["E_t"] + 1e-9
    aniso_x_map = 2.0 * grids_raw["E_l"] / sum_E_map
    aniso_y_map = 2.0 * grids_raw["E_t"] / sum_E_map

    base_c_sq_A = (freq_A * np.pi * N_grid / (2.4048 * fs * M)) ** 2
    base_c_sq_B = (freq_B * np.pi * N_grid / (2.4048 * fs * M)) ** 2

    c_sq_x_A_field.from_numpy(np.clip(base_c_sq_A * v_sq_ratio_map * aniso_x_map, 0.001, 0.24).astype(np.float32))
    c_sq_y_A_field.from_numpy(np.clip(base_c_sq_A * v_sq_ratio_map * aniso_y_map, 0.001, 0.24).astype(np.float32))
    c_sq_x_B_field.from_numpy(np.clip(base_c_sq_B * v_sq_ratio_map * aniso_x_map, 0.001, 0.24).astype(np.float32))
    c_sq_y_B_field.from_numpy(np.clip(base_c_sq_B * v_sq_ratio_map * aniso_y_map, 0.001, 0.24).astype(np.float32))

    edge_multiplier = np.ones((N_MAX, N_MAX), dtype=np.float32)
    for i in range(N_grid):
        for j in range(N_grid):
            if r_mask[i, j] > 0.5:
                dist_to_edge = radius - np.sqrt((i - center) ** 2 + (j - center) ** 2)
                if dist_to_edge < 3.5:
                    edge_multiplier[i, j] = 1.0 + 5.0 * np.exp(-dist_to_edge / 1.0)

    loss_mult, visco_mult = (0.55, 0.75) if is_cymbal else (1.35, 0.65) if drum_type == "kick" else (0.85, 0.85) if drum_type == "snare" else (0.75, 0.75)

    loss_A_field.from_numpy((grids_raw["loss"] * loss_mult * edge_multiplier / M).astype(np.float32))
    visco_A_field.from_numpy((grids_raw["visco"] * visco_mult * edge_multiplier / M).astype(np.float32))
    loss_B_field.from_numpy((grids_raw["loss"] * loss_mult * 0.8 * edge_multiplier / M).astype(np.float32))
    visco_B_field.from_numpy((grids_raw["visco"] * visco_mult * 0.8 * edge_multiplier / M).astype(np.float32))

    grid_scale = N_grid / 128.0
    if beater_type == "wood_stick": contact_ms, r_strike, exc_mult = 0.5, 2.0 * grid_scale, 1.8
    elif beater_type == "nylon_stick": contact_ms, r_strike, exc_mult = 0.3, 1.0 * grid_scale, 2.2
    else: contact_ms, r_strike, exc_mult = 4.0, 8.0 * grid_scale, 0.5

    if is_cymbal: r_strike, exc_mult = max(r_strike, 5.0 * grid_scale), exc_mult * 1.15

    pulse_len = max(5, int((contact_ms / 1000.0) * fs * M))
    exciter = (np.cos(np.linspace(-np.pi / 2, np.pi / 2, pulse_len)) ** 2) * (strike_force ** 1.3) * exc_mult * (float(N_REF) / float(N_grid))
    if beater_type in ["wood_stick", "nylon_stick"]: exciter[0] += strike_force * 0.6 * (float(N_REF) / float(N_grid))

    delay_substeps = max(1, int(shell_depth_inches * 0.0254 / 343.0 * fs * M))
    vol_history_A, vol_history_B = np.zeros(delay_substeps, dtype=np.float32), np.zeros(delay_substeps, dtype=np.float32)
    history_idx = 0

    max_steps = int(duration * fs)
    output_signal, bottom_accel = np.zeros(max_steps), np.zeros(max_steps)
    vel_arr, accel_arr, stress_arr = np.zeros(max_steps, dtype=np.float32), np.zeros(max_steps, dtype=np.float32), np.zeros(max_steps, dtype=np.float32)
    prev_vel_A, prev_vel_B = 0.0, 0.0

    strike_x, strike_y = (int(center), int(center + 0.1 * radius)) if drum_type == "snare" else (int(center), int(center)) if drum_type == "kick" else (int(center), int(center + 0.6 * radius)) if is_cymbal else (int(center + 0.2 * radius), int(center + 0.2 * radius))
    pickup_x, pickup_y = int(center - 0.2 * radius), int(center - 0.2 * radius)

    gui = None
    if show_gui:
        try: gui = ti.GUI(f"Drums: {drum_type.upper()} ({N_grid}x{N_grid})", res=(2 * N_grid, N_grid), background_color=0x000000)
        except Exception: pass

    tactile = mat_raw.get("tactile_profile", {})
    gran, brit, fibr, fluid = np.clip(tactile.get("granularity", 0.0), 0.0, 1.0), np.clip(tactile.get("brittleness", 0.0), 0.0, 1.0), np.clip(tactile.get("fibrousness", 0.0), 0.0, 1.0), np.clip(tactile.get("fluidity", 0.0), 0.0, 1.0)
    has_tactile = gran > 0 or brit > 0 or fibr > 0 or fluid > 0

    pitch_drop = 0.0 if is_cymbal else 15000.0 if drum_type in ["tom", "kick"] else 6000.0
    p_bend = 0.025 * (strike_force ** 2.5) * np.clip(1.0 - (brit * 1.5), 0.05, 1.0) * (0.15 if is_cymbal else 1.0)

    actual_steps = max_steps
    for step in range(max_steps):
        if step % 800 == 0:
            if step > int(fs * 0.1) and stat_strain_A[None] < 1e-8:
                actual_steps = max(step, 1024)
                break
            if yield_cb and yield_cb(step, max_steps) is False:
                actual_steps = max(step, 1024)
                break

            if gui is not None:
                if not gui.running:
                    gui.close()
                    actual_steps = max(step, 1024)
                    break
                
                field_A, field_B = p_A.to_numpy()[:N_grid, :N_grid], p_B.to_numpy()[:N_grid, :N_grid]
                img = np.zeros((2 * N_grid, N_grid, 3), dtype=np.float32)
                img[:N_grid, :, 0] += np.clip(field_A * 25.0, 0, 1)
                img[:N_grid, :, 2] += np.clip(-field_A * 25.0, 0, 1)
                if not is_cymbal:
                    img[N_grid:, :, 1] += np.clip(field_B * 25.0, 0, 1)
                    img[N_grid:, :, 2] += np.clip(-field_B * 25.0, 0, 1)
                gui.set_image(img)
                gui.show()

        compute_drums_stats(N_grid)
        avg_vol_A, avg_vol_B = stat_vol_A[None] / grid_area, stat_vol_B[None] / grid_area
        raw_strain_A = stat_strain_A[None] / grid_area * ((N_grid / float(N_REF)) ** 2)

        for sub in range(M):
            vol_A_del, vol_B_del = vol_history_A[history_idx], vol_history_B[history_idx]
            vol_history_A[history_idx], vol_history_B[history_idx] = avg_vol_A, avg_vol_B
            history_idx = (history_idx + 1) % delay_substeps

            step_drums_fdtd(
                N_grid, 0.0 if is_cymbal else 0.025 / M, avg_vol_A, avg_vol_B, vol_A_del, vol_B_del,
                strike_x, strike_y, exciter[step * M + sub] if (step * M + sub) < pulse_len else 0.0, r_strike, p_bend, raw_strain_A, (muffling * 0.05) / M, pitch_drop
            )
            if has_tactile: apply_drums_tactile_forces(N_grid, gran, brit, fibr, fluid, strike_force)
            update_drums_fields(N_grid)

        p_curr_A, p_curr_B = p_A[pickup_x, pickup_y], p_B[int(center), int(center)]
        v_A, v_B = p_curr_A - p_A_past[pickup_x, pickup_y], p_curr_B - p_B_past[int(center), int(center)]
        
        vel_arr[step], accel_arr[step], stress_arr[step] = v_A, v_A - prev_vel_A, np.abs(v_A) * 0.5
        bottom_accel[step] = v_B - prev_vel_B
        prev_vel_A, prev_vel_B = v_A, v_B

        mix_top = 1.0 if is_cymbal else (0.75 if drum_type == "snare" else 0.85)
        mix_bot = 0.0 if is_cymbal else (0.25 if drum_type == "snare" else 0.15)
        output_signal[step] = p_curr_A * mix_top + p_curr_B * mix_bot

    if gui is not None: gui.close()

    output_signal, vel_arr, accel_arr, stress_arr, bottom_accel = output_signal[:actual_steps], vel_arr[:actual_steps], accel_arr[:actual_steps], stress_arr[:actual_steps], bottom_accel[:actual_steps]

    fade_fdtd = min(int(fs * 0.01), len(output_signal))
    if fade_fdtd > 0: output_signal[-fade_fdtd:] *= np.linspace(1.0, 0.0, fade_fdtd) ** 2

    pad_samples = int(fs * np.clip(0.025 / max(0.015, shell_mat_for_processing.get("loss_factor", 0.02)), 1.8 if is_cymbal else 1.0 if drum_type == "kick" else 0.6 if drum_type == "snare" else 0.8, 4.0 if is_cymbal else 1.8 if drum_type == "kick" else 1.2 if drum_type == "snare" else 1.6))
    
    padded_signal = np.pad(output_signal, (0, pad_samples))
    velocity_arr, acceleration_arr, stress_arr = np.pad(vel_arr, (0, pad_samples)), np.pad(accel_arr, (0, pad_samples)), np.pad(stress_arr, (0, pad_samples))

    shell_freq = freq_A if is_cymbal else freq_A * 1.35
    shell_signal = apply_acoustic_shell(padded_signal, fs, shell_mat_for_processing, shell_freq, drum_type, strike_force, autotune_shell=autotune_shell, ring_mod=ring_mod)

    shell_delay = int(0.00008 * fs)
    delayed_shell = np.zeros_like(shell_signal)
    if len(shell_signal) > shell_delay: delayed_shell[shell_delay:] = shell_signal[:-shell_delay]
    else: delayed_shell = shell_signal

    delayed_shell *= 0.25 + 0.75 * (strike_force ** 0.85)
    mixed_signal = padded_signal + delayed_shell
    t_arr = np.arange(len(mixed_signal)) / fs

    tactile_noise = generate_tactile_profile(mat_raw, t_arr, mixed_signal, velocity_arr, acceleration_arr, stress_arr, fs, fs / 2.0, is_space=False, fatness=mat_boost, strike_force=strike_force)

    shell_vel = np.append(np.diff(delayed_shell), 0).astype(np.float32)
    shell_tactile_noise = generate_tactile_profile(shell_mat_for_processing, t_arr, delayed_shell, shell_vel, np.append(np.diff(shell_vel), 0).astype(np.float32), (shell_vel * 0.5).astype(np.float32), fs, fs / 2.0, is_space=False, fatness=mat_boost, strike_force=strike_force)

    tact_decay = 0.24 if drum_type == "snare" else 0.36 if is_cymbal else 0.32 if drum_type == "kick" else 0.20
    tactile_noise *= np.exp(-t_arr / tact_decay)
    
    tactile_mix = (0.28 * (strike_force ** 1.2) if drum_type == "snare" else 0.18 * (strike_force ** 1.3) if is_cymbal else 0.10 * (strike_force ** 2.2) if drum_type == "kick" else 0.14 * (strike_force ** 2.2)) * (1.0 + mat_boost * 1.0) * membrane_tactile
    
    final_output = mixed_signal * 0.65 + tactile_noise * tactile_mix + shell_tactile_noise * (0.12 * (strike_force ** 2.0) * (1.0 + mat_boost * 1.0))
    final_output = apply_meat_and_fat(final_output, fs, drum_type, strike_force, saturation=saturation, skin_mat=mat_raw, shell_mat=shell_mat_for_processing, shell_attack=shell_attack, shell_sustain=shell_sustain, membrane_snap=membrane_snap)
    final_output, _ = declick_ar_model(final_output, fs)

    if drum_type == "snare":
        wires = apply_snare_wires(bottom_accel, fs, tension=snare_tension, mix=1.0, strike_force=strike_force)
        final_output += np.pad(wires, (0, max(0, len(final_output) - len(wires))))[:len(final_output)]

    if use_bells and len(acceleration_arr) > 0:
        final_output = apply_internal_bells(final_output, acceleration_arr, fs, material_name=bell_material, mix=bell_mix * (strike_force ** 0.5), rr_index=rr_index, strike_force=strike_force)

    if body_polish_mix > 0.0 and not is_cymbal:
        mat_hash = (round(shell_mat_for_processing.get("E_long", 10.0), 3), round(shell_mat_for_processing.get("density", 0.5), 3), round(shell_mat_for_processing.get("loss_factor", 0.02), 4))
        cache_key = (mat_hash, round(shell_freq, 1), fs, drum_type)
        if cache_key not in _BODY_IR_CACHE: _BODY_IR_CACHE[cache_key] = generate_body_ir(shell_mat_for_processing, shell_freq, fs, drum_type=drum_type)
        final_output = apply_body_convolution(final_output, _BODY_IR_CACHE[cache_key], fs, mix=body_polish_mix)

    max_val = np.max(np.abs(final_output))
    if max_val > 0: final_output *= (10.0 ** (-8.0 / 20.0) + (1.0 - 10.0 ** (-8.0 / 20.0)) * ((np.clip(strike_force, 16.0 / 127.0, 1.0) - 16.0 / 127.0) / (1.0 - 16.0 / 127.0))) * 0.85 / max_val

    env = np.abs(final_output)
    active_indices = np.where(env > 1e-4)[0]
    if len(active_indices) > 0: final_output = final_output[: active_indices[-1] + int(fs * 0.05)]

    try: room_stereo = apply_3d_studio_room(final_output, fs)
    except Exception: room_stereo = np.column_stack((final_output, final_output))

    stereo_output = (np.column_stack((final_output, final_output)) * (0.55 if is_cymbal else 0.85 if drum_type == "kick" else 0.75)) + (room_stereo * (0.45 if is_cymbal else 0.15 if drum_type == "kick" else 0.25))
    
    max_val = np.max(np.abs(stereo_output))
    if max_val > 0: stereo_output *= (10.0 ** (-8.0 / 20.0) + (1.0 - 10.0 ** (-8.0 / 20.0)) * ((np.clip(strike_force, 16.0 / 127.0, 1.0) - 16.0 / 127.0) / (1.0 - 16.0 / 127.0))) * 0.92 / max_val

    if yield_cb: yield_cb(max_steps, max_steps)
    return stereo_output