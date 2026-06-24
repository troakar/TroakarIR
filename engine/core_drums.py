# --- START OF FILE engine/core_drums.py ---
import numpy as np
from scipy.signal import butter, lfilter
from typing import Dict

from engine.tactile import generate_tactile_profile
from engine.spatial import apply_true_physical_distance
from config.instruments import RESONATOR_TEMPLATES

def generate_physical_mallet_strike(mat, f0, duration, sample_rate, is_cymbal=False, mallet_hardness=0.8):
    t = np.arange(0, duration, 1.0 / sample_rate)
    signal = np.zeros_like(t)
    
    v_mat = np.sqrt((mat["E_long"] * 1e9) / (mat["density"] * 1000.0))
    base_f = f0 * np.clip(v_mat / 800.0, 1.0, 15.0)
    
    num_modes = 180 if is_cymbal else 60
    
    stiffness_ratio = mat["E_long"] / max(0.1, mat["density"])
    inharm = 1.0 + np.clip(stiffness_ratio / 20.0, 0.0, 1.5)
    
    contact_time = 0.0005 + 0.005 * (1.0 - mallet_hardness)
    force_env = (t / contact_time) * np.exp(1.0 - (t / contact_time))
    force_env[t > contact_time * 5] = 0.0
    
    deformation = force_env ** (0.5 + mallet_hardness)
    
    # Генератор хаоса для фазового рассеяния
    jitter = np.random.normal(0, 1.0, len(t))
    
    for i in range(1, num_modes + 1):
        f_n = base_f * (i ** (inharm if not is_cymbal else 1.35)) * (1.0 + 0.03 * (i % 7))
        if f_n > sample_rate / 2.2:
            break
            
        visco = mat.get("visco_gamma", 1e-5) if not is_cymbal else (mat.get("visco_gamma", 1e-5) * 0.05)
        eta = mat.get("loss_factor", 0.01) + (visco * f_n)
        tau = 1.0 / (np.pi * f_n * eta)
        
        if is_cymbal:
            tau *= 6.0 
            amp = 1.0 / (i ** 0.85) 
            
            mod_index = 4.0 * np.exp(-t / (tau * 0.3)) * mallet_hardness
            fm_wash = mod_index * np.sin(2 * np.pi * (f_n * 1.61803) * t)
            
            # --- МАГИЯ ЗДЕСЬ: Фазовое разрушение ---
            # Высокие частоты превращаются из синусоид в плотный "шшшш" (полосной шум)
            phase_noise = jitter * (f_n / 12000.0) * mallet_hardness * 2.5
            phase = 2 * np.pi * f_n * t + fm_wash + phase_noise
        else:
            tau *= (0.05 + 0.2 * mallet_hardness)
            amp = 1.0 / (i ** (2.0 - 0.5 * mallet_hardness))
            phase = 2 * np.pi * f_n * t + deformation * 2.0
            
        signal += amp * np.exp(-t / tau) * np.sin(phase)
        
    # --- ИНТЕРМОДУЛЯЦИЯ (Склейка) ---
    # Нелинейное искажение сплавляет синусоиды вместе, заполняя пустоты спектра
    if is_cymbal:
        signal = np.tanh(signal * 3.0) / 3.0
        
    max_val = np.max(np.abs(signal))
    if max_val > 0:
        signal /= max_val
    return signal

def generate_snare_wires(wire_mat, drum_membrane_signal, duration, sample_rate):
    """
    Эмуляция металлических пружин снейра.
    Связанные осцилляторы, модулируемые движением мембраны. Никакого белого шума.
    """
    t = np.arange(0, duration, 1.0 / sample_rate)
    wires = np.zeros_like(t)
    
    wire_E = wire_mat["E_long"]
    # Базовая частота пружины зависит от жесткости металла (Сталь - звонко, Пьютер - глухо)
    base_wire_f = np.clip(wire_E * 25.0, 800.0, 5000.0)
    
    # 40 трущихся друг о друга металлических резонансов
    for w in range(1, 41):
        fw = base_wire_f * (1.0 + 0.07 * w * np.random.uniform(0.9, 1.1))
        if fw > sample_rate / 2.2:
            break
        tau_w = 0.2 / max(0.001, wire_mat["loss_factor"] * 50.0)
        wires += (1.0 / np.sqrt(w)) * np.exp(-t / tau_w) * np.sin(2 * np.pi * fw * t)
        
    # АМПЛИТУДНАЯ МОДУЛЯЦИЯ: Пружины звучат только тогда, когда мембрана бьет по ним
    # Вычисляем огибающую мембраны (выпрямленный сигнал)
    membrane_env = np.abs(drum_membrane_signal)
    
    # Привязываем пружины к удару мембраны
    rattle = wires * np.clip(membrane_env * 5.0, 0.0, 1.0)
    return rattle

def generate_drum_ir(inst_dict: Dict, mat_dict: Dict, def_mat_dict: Dict, 
                     shell_mat_dict: Dict = None, wire_mat_dict: Dict = None,
                     user_scale: float = 1.0, duration: float = 2.0, 
                     sample_rate: int = 44100, mic_distance_m: float = 0.5, 
                     custom_f0: float = None, compensate_delay: bool = True) -> np.ndarray:
    
    template = RESONATOR_TEMPLATES[inst_dict["resonator_template"]]
    mat = mat_dict  
    def_mat = def_mat_dict
    shell_mat = shell_mat_dict if shell_mat_dict else mat_dict 
    wire_mat = wire_mat_dict if wire_mat_dict else def_mat_dict 
    
    inst = inst_dict.copy()
    if custom_f0 is not None and "f0" in inst:
        if "A0" in inst: inst["A0"] *= (custom_f0 / inst["f0"])
        inst["f0"] = custom_f0
        
    t = np.arange(0, duration, 1.0 / sample_rate)
    ir_signal = np.zeros_like(t)
    nyquist = 0.5 * sample_rate
    
    is_drum = (inst_dict["resonator_template"] == "drum_shell")
    is_cymbal = (inst_dict["resonator_template"] == "cymbal_plate")
    
    v_def = np.sqrt((def_mat["E_long"] * 1e9) / (def_mat["density"] * 1000.0))
    v_target = np.sqrt((mat["E_long"] * 1e9) / (mat["density"] * 1000.0))
    scale_factor = (v_target / v_def) / user_scale
    k_aniso = 0.5 + 0.5 * np.tanh(((mat["E_long"] / max(0.001, mat["E_trans"])) - 1.0) / 10.0)

    # === 1. ГЛАВНЫЕ МОДЫ И ВОЗДУХ КАДУШКИ ===
    modes = template["modes_builder"](inst, scale_factor, k_aniso)
    
    # Вычисляем огибающую энергии для динамического натяжения
    eenergy_env = np.exp(-t / 0.15) 
    
    for mode in modes:
        f = np.clip(mode["f"], 10.0, nyquist - 100.0)
        
        if template.get("has_helmholtz", False) and mode.get("is_air", False):
            tau = 12.0 / (np.pi * f)
            decay = np.exp(-t / tau)
            phase = 2 * np.pi * f * t
        elif is_cymbal:
            # ФИЗИКА МЕТАЛЛИЧЕСКИХ ПЛАСТИН
            visco_cymbal = shell_mat.get("visco_gamma", 1e-5) * 0.02 # Игнорируем вязкость дерева
            eta = shell_mat.get("loss_factor", 0.01) + (visco_cymbal * f)
            tau = 1.0 / (np.pi * f * eta) * 5.0 # Глобальный множитель сустейна тарелки
            tau = min(tau, duration * 2.0)
            
            # Эффект "Bloom" (Вскипание): ВЧ появляются с задержкой, а не бьют сразу
            bloom_time = np.clip((f / 5000.0) * 0.15, 0.005, 0.4)
            bloom_env = (1.0 - np.exp(-t / bloom_time))
            decay = np.exp(-t / tau) * bloom_env
            
            # Микро-модуляция фазы для имитации биений изогнутого металла
            phase_drift = 0.5 * np.sin(2 * np.pi * 3.0 * t) * np.exp(-t / 1.0)
            phase = 2 * np.pi * f * t + phase_drift
        else:
            # ФИЗИКА БАРАБАНОВ (Мембрана + Кадушка)
            eta = shell_mat.get("loss_factor", 0.01) + (shell_mat.get("visco_gamma", 1e-5) * f)
            tau = 1.0 / (np.pi * f * eta) * 0.35 
            tau = min(tau, duration * 1.5)
            decay = np.exp(-t / tau)
            
            # True Dynamic Tension (Pitch Drop)
            is_kick = "kick" in inst_dict.get("category", "") or "kick" in inst_dict.get("name", "").lower()
            tension_mod = 1.0 + (1.2 if is_kick else 0.5) * (energy_env ** 2.0)
            integral_tension = t + (1.2 if is_kick else 0.5) * (-0.075) * np.exp(-t / 0.075)
            phase = 2 * np.pi * f * integral_tension
            
        ir_signal += mode["amp"] * decay * np.sin(phase)

    # === 2. МАТЕРИАЛЬНЫЙ ТРАНЗИЕНТ (Без белого шума!) ===
    mallet_hard = 0.9 if is_cymbal else 0.4 # Можно вынести в настройки
    material_transient = generate_physical_mallet_strike(mat, inst["f0"], duration, sample_rate, is_cymbal, mallet_hardness=mallet_hard)
    
    if is_cymbal:
        # Для тарелок звук разгоняется (Swell)
        material_transient *= (1.0 - np.exp(-t / 0.012))
    else:
        # Для барабанов транзиент бьет сразу
        transient_env = np.exp(-t / (0.002 + 0.05 * (1.0 - template["transient_click"])))
        material_transient *= transient_env * template["transient_click"] * 0.5

    # === 3. ПРУЖИНЫ СНЕЙРА ===
    snare_rattle_amt = inst.get("snare_rattle", 0.0)
    snare_signal = np.zeros_like(t)
    if snare_rattle_amt > 0.0:
        snare_signal = generate_snare_wires(wire_mat, ir_signal, duration, sample_rate) * snare_rattle_amt * 0.6

    # === 4. ТАКТИЛЬНОСТЬ ===
    ir_tactile = generate_tactile_profile(mat, t, ir_signal, sample_rate, nyquist, is_space=False)

    # === МИКС СЛОЕВ (Нелинейная склейка) ===
    # Пропускаем модальный сигнал через легкий сатуратор, чтобы убрать цифровую чистоту
    ir_signal_sat = np.tanh(ir_signal * 1.5) / 1.5
    
    ir_left = ir_signal_sat * 0.75 + material_transient * 0.25 + snare_signal + ir_tactile * 0.8
    ir_right = ir_signal_sat * 0.65 + material_transient * 0.35 + snare_signal + ir_tactile * 0.9
    
    # === 5. ПСИХОАКУСТИКА: ДИСТАНЦИЯ ДО МИКРОФОНА И ВОЗДУХ ===
    
    # 1. Поглощение высоких частот кислородом (чем дальше микрофон, тем глуше звук)
    air_cutoff = np.clip(22000.0 - (mic_distance_m * 1800.0), 4000.0, nyquist - 100.0)
    b_air, a_air = butter(2, air_cutoff / nyquist, btype='low')
    
    ir_left = lfilter(b_air, a_air, ir_left)
    ir_right = lfilter(b_air, a_air, ir_right)
    
    # 2. Раннее отражение от пола / стойки (Comb-фильтр)
    # Это размазывает "синтетический" транзиент, давая ощущение реального пространства
    floor_delay_s = 0.0015 * max(0.5, mic_distance_m) # ~1.5 мс на метр дистанции
    delay_samp = int(floor_delay_s * sample_rate)
    
    if delay_samp > 0:
        # Инвертированное отражение (как отскок от твердого пола)
        bounce_L = np.zeros_like(ir_left)
        bounce_R = np.zeros_like(ir_right)
        bounce_L[delay_samp:] = ir_left[:-delay_samp] * (-0.25)
        bounce_R[delay_samp:] = ir_right[:-delay_samp] * (-0.25)
        
        ir_left += bounce_L
        ir_right += bounce_R

    # Базовая фильтрация НЧ/ВЧ инструмента
    low_cut_hz = np.clip(inst["low_cut"] / user_scale, 15.0, nyquist - 100.0)
    b_low, a_low = butter(3, low_cut_hz / nyquist, btype='high')
    
    stereo_ir = np.vstack((lfilter(b_low, a_low, ir_left), lfilter(b_low, a_low, ir_right))).T

    # === AUTO-TRIM (Острый транзиент) ===
    if compensate_delay:
        env = np.abs(stereo_ir[:, 0]) + np.abs(stereo_ir[:, 1])
        max_amp = np.max(env)
        if max_amp > 0:
            onset_idx = np.argmax(env > max_amp * 0.001)
            if onset_idx > 0:
                stereo_ir = np.pad(stereo_ir[onset_idx:], ((0, onset_idx), (0, 0)), mode='constant')

    # Fade-out и Микро-атака
    fade_samples = int(0.1 * sample_rate)
    if len(stereo_ir) > fade_samples:
        stereo_ir[-fade_samples:] *= (np.linspace(1.0, 0.0, fade_samples) ** 2)[:, np.newaxis]
    
    attack_samples = int(0.0005 * sample_rate) 
    if len(stereo_ir) > attack_samples:
        stereo_ir[:attack_samples] *= (np.linspace(0.0, 1.0, attack_samples) ** 2)[:, np.newaxis]

    max_val = np.max(np.abs(stereo_ir))
    if max_val > 0: 
        stereo_ir = (stereo_ir / max_val) * 0.6
        
    return stereo_ir
# --- END OF FILE engine/core_drums.py ---