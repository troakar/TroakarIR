import logging
import numpy as np
from scipy.signal import butter, lfilter
from typing import Dict

from engine.tactile import generate_tactile_profile
from engine.spatial import apply_true_physical_distance
from config.instruments import RESONATOR_TEMPLATES

logger = logging.getLogger(__name__)

def calculate_coincidence_frequency(mat_props, h):
    c_air = 343.0
    rho_mat_kg = mat_props["density"] * 1000.0
    E_mat_pa = mat_props["E_long"] * 1e9

    # Достаем коэффициент Пуассона (по умолчанию 0.3, если не указан)
    nu = mat_props.get("poisson", 0.3)

    factor_c = (c_air**2) / (2 * np.pi)

    # Истинная академическая формула изгибной жесткости пластины D = (E * h^3) / (12 * (1 - nu^2))
    stiffness_ratio = np.sqrt((12.0 * rho_mat_kg * (1.0 - nu**2)) / (E_mat_pa * (h**2)))

    return factor_c * stiffness_ratio

def calculate_radiation_efficiency(f, f_c):
    if f < f_c:
        return (f / f_c) ** 1.5
    else:
        return 1.0

def generate_modal_cloud_physics(duration, sample_rate, freq_start, freq_end, num_modes, mat_props, user_scale, is_space=False, space_size=0.0, eq_curve_func=None):
    t = np.arange(0, duration, 1.0 / sample_rate)
    cloud = np.zeros_like(t)
    
    if is_space:
        h = 0.3 * user_scale
    else:
        h = mat_props["base_thickness"] * user_scale
        
    f_c = calculate_coincidence_frequency(mat_props, h)
    
    if is_space and space_size > 0.0:
        base_freqs = freq_start + (freq_end - freq_start) * (np.linspace(0, 1, num_modes) ** (1.0 / 3.0))
    else:
        base_freqs = np.linspace(freq_start, freq_end, num=num_modes)
        
    delta_f = (freq_end - freq_start) / num_modes
    freqs = base_freqs + np.random.uniform(-delta_f * 0.4, delta_f * 0.4, num_modes)
    phases = np.random.uniform(0, 2 * np.pi, num_modes)
    
    drift_speeds = np.random.uniform(1.0, 4.0, num_modes)
    drift_phases = np.random.uniform(0, 2 * np.pi, num_modes)
    drift_depths = freqs * 0.00015 
    
    rho_mat_kg = mat_props["density"] * 1000.0
    Z_air = 415.0
    
    for idx, (f, p) in enumerate(zip(freqs, phases)):
        if f >= sample_rate / 2.0:
            continue
            
        sigma = calculate_radiation_efficiency(f, f_c)
        eta_air = (Z_air * sigma) / (2 * np.pi * max(10.0, f) * rho_mat_kg * h)
        eta_total = mat_props["loss_factor"] + eta_air + (mat_props["visco_gamma"] * f)
        tau = 1.0 / (np.pi * f * eta_total)
        
        if is_space and space_size > 0.0:
            tau *= (space_size * 0.4)
            
        amp = (freq_start / f) * sigma
        if eq_curve_func:
            amp *= eq_curve_func(f)
            
        decay = np.exp(-t / tau)
        
        d_depth = drift_depths[idx]
        d_speed = drift_speeds[idx]
        d_phase = drift_phases[idx]
        
        phase_modulated = 2 * np.pi * f * t - (d_depth / d_speed) * np.cos(2 * np.pi * d_speed * t + d_phase) + p
        cloud += amp * decay * np.sin(phase_modulated)
        
    max_val = np.max(np.abs(cloud))
    if max_val > 0:
        cloud /= max_val
    return cloud

def generate_physical_ir(inst_dict: Dict, mat_dict: Dict, def_mat_dict: Dict, 
                         shell_mat_dict: Dict = None, wire_mat_dict: Dict = None,
                         user_scale: float = 1.0, duration: float = 2.0, 
                         sample_rate: int = 44100, mic_distance_m: float = 0.0, custom_f0: float = None) -> np.ndarray:
    
    try:
        template = RESONATOR_TEMPLATES[inst_dict["resonator_template"]]
    except KeyError as e:
        logger.error(f"Unknown resonator_template: {inst_dict.get('resonator_template')} in inst_dict keys={list(inst_dict.keys())}")
        raise
    mat = mat_dict
    shell_mat = shell_mat_dict if shell_mat_dict else mat_dict
    wire_mat = wire_mat_dict if wire_mat_dict else def_mat_dict
    inst = inst_dict.copy()

    if custom_f0 is not None and "f0" in inst:
        if "A0" in inst:
            inst["A0"] *= (custom_f0 / inst["f0"])
        inst["f0"] = custom_f0
    
    v_def = np.sqrt((def_mat_dict["E_long"] * 1e9) / (def_mat_dict["density"] * 1000.0))
    v_target = np.sqrt((mat["E_long"] * 1e9) / (mat["density"] * 1000.0))
    combined_plate_scale = (v_target / v_def) / user_scale
    
    AR_target = mat["E_long"] / max(0.001, mat["E_trans"])
    k_aniso = 0.5 + 0.5 * np.tanh((AR_target - 1.0) / 10.0)
    
    t = np.arange(0, duration, 1.0 / sample_rate)
    ir_signal = np.zeros_like(t)
    nyquist = 0.5 * sample_rate
    
    is_space = template.get("is_space", False)
    h_target = 0.3 * user_scale if is_space else mat["base_thickness"] * user_scale
    f_c = calculate_coincidence_frequency(mat, h_target)
    
    # Синтез главных дискретных мод
    if not is_space:
        inst_copy = inst.copy()
        if "A0" in inst_copy:
            inst_copy["A0"] = inst["A0"] / user_scale
            
        modes = template["modes_builder"](inst_copy, combined_plate_scale, k_aniso)
        rho_mat_kg = mat["density"] * 1000.0
        Z_air = 415.0
        
        for mode in modes:
            f = np.clip(mode["f"], 10.0, nyquist - 100.0)
            amp = mode["amp"]
            
            effective_density = rho_mat_kg
            if inst["resonator_template"] == "drum_shell" and mode["is_air"]:
                effective_density = shell_mat["density"] * 1000.0
            
            if template["has_helmholtz"] and mode["is_air"]:
                tau = 12.0 / (np.pi * f)
            else:
                sigma = calculate_radiation_efficiency(f, f_c)
                eta_air = (Z_air * sigma) / (2 * np.pi * f * effective_density * h_target)
                eta_total = mat["loss_factor"] + eta_air + (mat["visco_gamma"] * f)
                tau = 1.0 / (np.pi * f * eta_total)
            
            # ИСПРАВЛЕНИЕ: Разрешаем звуку звучать столько, сколько диктует физика.
            tau = min(tau, duration * 1.5)
            decay = np.exp(-t / tau)
            ir_signal += amp * decay * np.sin(2 * np.pi * f * t)
            
    # Синтез ВЧ-хвоста
    bh_center = np.clip(inst["bridge_hill"] * combined_plate_scale, 500.0, 10000.0)
    
    def bridge_hill_eq(f):
        # ИСПРАВЛЕНИЕ: Вернули множитель 2.5 для ярких, кристальных верхов
        # Расширили ширину горба (2000.0) для мягкого воздушного резонанса
        return 1.0 + 2.5 * np.exp(-0.5 * ((f - bh_center) / 2000.0) ** 2)

    if is_space:
        space_size = template["base_size"] * user_scale
        freq_start = max(20.0, 343.0 / (2.0 * space_size))
        
        diffuse_tail = generate_modal_cloud_physics(
            duration=duration, sample_rate=sample_rate, 
            freq_start=freq_start, freq_end=18000.0, num_modes=1200, 
            mat_props=mat, user_scale=user_scale, is_space=True, space_size=space_size, 
            eq_curve_func=bridge_hill_eq
        )
    else:
        diffuse_tail = generate_modal_cloud_physics(
            duration=duration, sample_rate=sample_rate, 
            freq_start=1200.0, freq_end=18000.0, num_modes=800, 
            mat_props=mat, user_scale=user_scale, is_space=False,
            eq_curve_func=bridge_hill_eq
        )
    
    # Транзиент (Инициализирующий щелчок)
    transient_env = np.exp(-t / (0.002 + 0.05 * (1.0 - template["transient_click"])))
    if is_space:
        organic_click = generate_modal_cloud_physics(
            duration=duration, sample_rate=sample_rate, 
            freq_start=80.0, freq_end=12000.0, num_modes=150, 
            mat_props=mat, user_scale=user_scale, is_space=True, space_size=space_size
        ) * transient_env * 0.4
    else:
        organic_click = generate_modal_cloud_physics(
            duration=duration, sample_rate=sample_rate, 
            freq_start=2000.0, freq_end=15000.0, num_modes=200, 
            mat_props=mat, user_scale=user_scale, is_space=False
        ) * transient_env * template["transient_click"] * 0.4
        
    # === ФИЗИКА ПРУЖИН МАЛОГО БАРАБАНА (WIRE RATTLE) ===
    snare_rattle_amt = inst.get("snare_rattle", 0.0)
    if snare_rattle_amt > 0.0:
        wire_E = wire_mat["E_long"]
        wire_loss = wire_mat["loss_factor"]
        
        wire_hp = np.clip(wire_E * 20.0, 800.0, 6000.0)
        wire_lp = np.clip(wire_E * 150.0, 5000.0, 18000.0)
        
        b_sn, a_sn = butter(2, [wire_hp / nyquist, wire_lp / nyquist], btype='band')
        noise = np.random.normal(0, 1, len(t))
        filtered_noise = lfilter(b_sn, a_sn, noise)
        
        decay_time = 0.15 / max(0.001, wire_loss * 50.0)
        decay_time = np.clip(decay_time, 0.05, 0.4) * user_scale
        decay_snare = np.exp(-t / decay_time)
        
        organic_click += filtered_noise * decay_snare * snare_rattle_amt * 0.7

    # Подключение тактильного модуля из отдельного файла
    ir_tactile = generate_tactile_profile(mat, t, ir_signal, sample_rate, nyquist, is_space)
    
    # Симпатический резонанс струн
    sympathetic_ring = np.zeros_like(t)
    tuning_hz = inst.get("sympathetic_strings", [])
    
    if tuning_hz:
        for string_f in tuning_hz:
            sf = string_f / user_scale 
            if sf < nyquist:
                tau_str = min(0.4, duration / 4.0) 
                decay_str = np.exp(-t / tau_str)
                sympathetic_ring += 0.003 * decay_str * np.sin(2 * np.pi * sf * t)
                sympathetic_ring += 0.001 * decay_str * np.sin(2 * np.pi * (sf * 2.01) * t)

    # TRUE STEREO И СБОРКА МИКСА
    if is_space:
        ir_left = diffuse_tail * 0.82 + organic_click * 0.13 + sympathetic_ring * 0.05 + ir_tactile * 0.5
        ir_right = diffuse_tail * 0.82 + organic_click * 0.13 + sympathetic_ring * 0.05 + ir_tactile * 0.5
    else:
        ir_left = ir_signal * 0.75 + diffuse_tail * 0.12 + organic_click * 0.10 + ir_tactile * 0.8 + sympathetic_ring
        ir_right = ir_signal * 0.65 + diffuse_tail * 0.18 + organic_click * 0.20 + ir_tactile * 0.9 + sympathetic_ring
    
    # Фильтрация
    low_cut_hz = np.clip(inst["low_cut"] / user_scale, 15.0, nyquist - 100.0)
    b_low, a_low = butter(3, low_cut_hz / nyquist, btype='high')
    b_high, a_high = butter(2, min(16000.0, nyquist - 200.0) / nyquist, btype='low')
    
    ir_left = lfilter(b_high, a_high, lfilter(b_low, a_low, ir_left))
    ir_right = lfilter(b_high, a_high, lfilter(b_low, a_low, ir_right))
    
    stereo_ir = np.vstack((ir_left, ir_right)).T
    
    # Пространственная обработка
    if not is_space:
        stereo_ir = apply_true_physical_distance(stereo_ir, sample_rate, distance_m=mic_distance_m)

    # Защита от гула (Fade-out)
    fade_samples = int(0.1 * sample_rate)
    if len(stereo_ir) > fade_samples:
        fade_curve = np.linspace(1.0, 0.0, fade_samples) ** 2
        stereo_ir[-fade_samples:, 0] *= fade_curve
        stereo_ir[-fade_samples:, 1] *= fade_curve

    # Микро-атака
    attack_samples = int(0.001 * sample_rate) 
    if len(stereo_ir) > attack_samples:
        attack_curve = np.linspace(0.0, 1.0, attack_samples) ** 2
        stereo_ir[:attack_samples, 0] *= attack_curve
        stereo_ir[:attack_samples, 1] *= attack_curve

    # Нормализация
    max_val = np.max(np.abs(stereo_ir))
    if max_val > 0:
        stereo_ir = (stereo_ir / max_val) * 0.45
        
    return stereo_ir