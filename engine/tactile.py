import numpy as np
from scipy.signal import butter, sosfilt, lfilter
from typing import Dict
import math

# ----------------------------------------------------------------------
#  Вспомогательные утилиты динамической обработки
# ----------------------------------------------------------------------

def _envelope_follower(signal: np.ndarray, fs: int,
                      attack_ms: float = 1.0, release_ms: float = 50.0) -> np.ndarray:
    """Детектор огибающей."""
    alpha_attack = 1.0 - math.exp(-1.0 / (max(0.1, attack_ms) * 0.001 * fs))
    alpha_release = 1.0 - math.exp(-1.0 / (max(0.1, release_ms) * 0.001 * fs))
    env = np.zeros_like(signal)
    prev = 0.0
    for i, s in enumerate(np.abs(signal)):
        alpha = alpha_attack if s > prev else alpha_release
        prev = alpha * s + (1.0 - alpha) * prev
        env[i] = prev
    return env

def _soft_knee_limit_vectorized(signal: np.ndarray, threshold: float = 0.12, ratio: float = 3.5) -> np.ndarray:
    """
    Векторизованный Soft-Knee компрессор-лимитер.
    Плавный излом порога предотвращает перегрузку и цифровой треск при суммировании
    слоев тактильного шума, сохраняя текстуру полностью органичной.
    """
    abs_sig = np.abs(signal)
    mask_comp = abs_sig > threshold
    
    output = signal.copy()
    if np.any(mask_comp):
        val = abs_sig[mask_comp]
        excess = val - threshold
        # Формула мягкого компрессирования избыточной амплитуды
        compressed_val = threshold + excess / (1.0 + (excess / threshold) * (ratio - 1.0))
        output[mask_comp] = np.sign(signal[mask_comp]) * compressed_val
        
    return output

# ----------------------------------------------------------------------
#  MSAE V6: SIGNAL-DEPENDENT TACTILE ENGINE (Физические генераторы)
# ----------------------------------------------------------------------

def _apply_fibrous_waveshaper(ir_signal: np.ndarray, velocity_arr: np.ndarray, fs: int, 
                              material: dict, strike_force: float) -> np.ndarray:
    """
    ФИБРОЗНОСТЬ (Дребезг волокон дерева Pomor Pine). 
    Модулирует хруст по скорости деформации корпуса.
    """
    tactile = material.get("tactile_profile", {})
    intensity = tactile.get("fibrousness", 0.0) * strike_force
    
    if intensity <= 0.01:
        return np.zeros_like(ir_signal)
    
    strain_rate = np.abs(velocity_arr)
    max_sr = np.max(strain_rate) + 1e-9
    env = _envelope_follower(strain_rate / max_sr, fs, attack_ms=0.5, release_ms=15.0)
    
    drive = 1.0 + intensity * 6.0 * env
    dc_offset = intensity * 0.3 * env
    driven_signal = (ir_signal + dc_offset) * drive
    
    folded = np.sin(driven_signal * (np.pi / 2.0))
    crunch = folded - np.sin(dc_offset * (np.pi / 2.0)) - ir_signal
    
    if material.get("category") == "wood" and intensity > 0.05:
        threshold = 0.32 - intensity * 0.12
        buzz = np.where(np.abs(ir_signal) > threshold, np.sin(ir_signal * 14.0) * 0.18 * env, 0.0)
        crunch += buzz
    
    sos_hp = butter(2, 1200.0, btype='highpass', fs=fs, output='sos')
    crunch = sosfilt(sos_hp, crunch)
    
    return crunch * intensity * 0.5

def _apply_fluid_viscoelasticity(ir_signal: np.ndarray, velocity_arr: np.ndarray, fs: int, 
                                 material: dict, strike_force: float) -> np.ndarray:
    """ВЯЗКОСТЬ (Вязкое трение)."""
    tactile = material.get("tactile_profile", {})
    intensity = tactile.get("fluidity", 0.0) * strike_force
    
    if intensity <= 0.01:
        return np.zeros_like(ir_signal)
    
    v_norm = np.abs(velocity_arr)
    max_v = np.max(v_norm) + 1e-9
    v_env = _envelope_follower(v_norm / max_v, fs, attack_ms=1.0, release_ms=40.0)
    
    noise = np.random.normal(0, 1.0, len(ir_signal))
    
    sos_heavy = butter(2, 300.0, btype='low', fs=fs, output='sos')
    sos_light = butter(2, 2500.0, btype='low', fs=fs, output='sos')
    
    heavy_noise = sosfilt(sos_heavy, noise)
    light_noise = sosfilt(sos_light, noise)
    
    dynamic_noise = heavy_noise * v_env + light_noise * (1.0 - v_env)
    
    return dynamic_noise * v_env * intensity * 0.4

def _apply_granular_stutter(ir_signal: np.ndarray, acceleration_arr: np.ndarray, fs: int, 
                            material: dict, strike_force: float) -> np.ndarray:
    """ГРАНУЛЯРНОСТЬ (Осыпание кристаллов морской соли)."""
    tactile = material.get("tactile_profile", {})
    intensity = tactile.get("granularity", 0.0) * strike_force
    
    if intensity <= 0.01:
        return np.zeros_like(ir_signal)
    
    accel_norm = np.abs(acceleration_arr)
    max_accel = np.max(accel_norm) + 1e-9
    a_env = accel_norm / max_accel
    
    probability = a_env * intensity
    
    random_dist = np.random.rand(len(ir_signal))
    gate = (random_dist < (probability * 0.15)).astype(np.float32)
    gate = lfilter([0.3, 0.4, 0.3], [1.0], gate)  # Мягкое размытие гейта убирает "цифровые песчинки"
    
    sos_hp = butter(2, 2000.0, btype='highpass', fs=fs, output='sos')
    highs = sosfilt(sos_hp, ir_signal)
    
    return highs * gate * intensity * 1.5

def _apply_brittle_cracks(ir_signal: np.ndarray, stress_arr: np.ndarray, fs: int, 
                          material: dict, strike_force: float, nyquist: float) -> np.ndarray:
    """ХРУПКОСТЬ (Трещины топлёка Pomor Pine при деформациях)."""
    tactile = material.get("tactile_profile", {})
    brittleness = tactile.get("brittleness", 0.0) * strike_force
    E_long = material.get("E_long", 10.0)
    
    if brittleness <= 0.01:
        return np.zeros_like(ir_signal)
    
    stress_norm = np.abs(stress_arr)
    max_stress = np.max(stress_norm) + 1e-9
    
    threshold = max_stress * (1.0 - brittleness * 0.6 - strike_force * 0.1)
    threshold = max(threshold, max_stress * 0.2)
    
    triggers = (stress_norm > threshold).astype(np.float32)
    sparse_mask = (np.random.rand(len(ir_signal)) > 0.995).astype(np.float32)
    events = triggers * sparse_mask
    
    # Смягчаем атаку импульсов трещин (убирает щелчки)
    events = lfilter([0.15, 0.35, 0.35, 0.15], [1.0], events)
    
    f_res = np.clip(E_long * 500.0, 3000.0, nyquist - 500.0)
    sos_bp = butter(2, [f_res * 0.8, min(f_res * 1.2, nyquist - 100)], btype='bandpass', fs=fs, output='sos')
    cracks = sosfilt(sos_bp, events)
    
    return cracks * brittleness * 2.5

def _process_inclusions_tactile(ir_signal: np.ndarray, velocity_arr: np.ndarray, 
                                acceleration_arr: np.ndarray, stress_arr: np.ndarray,
                                fs: int, material: dict, strike_force: float) -> np.ndarray:
    """ВКЛЮЧЕНИЯ (Кристаллы соли и минералы в сосне)."""
    inclusions = material.get("inclusions", [])
    if not inclusions:
        return np.zeros_like(ir_signal)

    total = np.zeros_like(ir_signal)
    for inc in inclusions:
        inc_mat = inc.get("material", {})
        if isinstance(inc_mat, str):
            try:
                from config.materials import MATERIAL_PHYSICS
                inc_mat = MATERIAL_PHYSICS.get(inc_mat, {})
            except ImportError:
                inc_mat = {}
        if not inc_mat:
            continue

        density_ratio = float(inc.get("density_ratio", 0.1))
        
        virtual_mat = inc_mat.copy() if isinstance(inc_mat, dict) else {}
        for key in ["tactile_profile"]:
            if key in inc:
                virtual_mat[key] = {**virtual_mat.get(key, {}), **inc[key]}
        
        total += _apply_granular_stutter(ir_signal, acceleration_arr, fs, virtual_mat, strike_force) * density_ratio
        total += _apply_fibrous_waveshaper(ir_signal, velocity_arr, fs, virtual_mat, strike_force) * density_ratio

    return total

# ----------------------------------------------------------------------
#  Центральный интерфейсный процессор («Tactile Engine»)
# ----------------------------------------------------------------------

def generate_tactile_profile(mat: Dict, t: np.ndarray, ir_signal: np.ndarray,
                             velocity_arr: np.ndarray, acceleration_arr: np.ndarray, stress_arr: np.ndarray,
                             sample_rate: int, nyquist: float, is_space: bool,
                             fatness: float = 0.0, strike_force: float = 1.0) -> np.ndarray:
    """Сборка всех физических слоев тактильности с защитой от перегрузки."""
    ir_tactile = np.zeros_like(t)

    # 1. Фиброзный слой волокон (не в космосе)
    if not is_space:
        ir_tactile += _apply_fibrous_waveshaper(ir_signal, velocity_arr, sample_rate, mat, strike_force)

    # 2. Флюидная вязкость
    ir_tactile += _apply_fluid_viscoelasticity(ir_signal, velocity_arr, sample_rate, mat, strike_force)
    
    # 3. Гранулярное осыпание
    ir_tactile += _apply_granular_stutter(ir_signal, acceleration_arr, sample_rate, mat, strike_force)
    
    # 4. Микротрещины
    ir_tactile += _apply_brittle_cracks(ir_signal, stress_arr, sample_rate, mat, strike_force, nyquist)
    
    # 5. Кристаллические вкрапления соли
    ir_tactile += _process_inclusions_tactile(ir_signal, velocity_arr, acceleration_arr, stress_arr, sample_rate, mat, strike_force)

    # 6. Ламповое уплотнение (Fatness)
    if fatness > 0.01:
        ir_tactile *= (1.0 + fatness * 1.2)
        ir_tactile = np.tanh(ir_tactile * (1.0 + fatness * 0.4))

    # === ШАГ 7: Защита от перегрузки и цифрового скрежета ===
    # Ограничиваем пиковые соударения мягким компрессором
    ir_tactile = _soft_knee_limit_vectorized(ir_tactile, threshold=0.12, ratio=3.5)

    # Мягкое финальное сглаживание крутизны фронта (Slew filter)
    slew_alpha = 0.35  
    ir_tactile = lfilter([slew_alpha], [1, slew_alpha - 1], ir_tactile)

    return ir_tactile

# ----------------------------------------------------------------------
#  Чистый текстурный шум трения (Material-Aware, стерео)
# ----------------------------------------------------------------------

def generate_pure_material_noise(mat: Dict, duration: float = 2.5,
                                 sample_rate: int = 44100) -> np.ndarray:
    """Шум трения смычка / рук на основе FDTD датчиков."""
    t = np.arange(0, duration, 1.0 / sample_rate)
    dummy_vel = np.random.normal(0, 1.0, len(t))
    dummy_accel = np.append(np.diff(dummy_vel), 0)
    dummy_stress = np.abs(dummy_vel) * 0.5
    dummy_ir = dummy_vel * 0.1
    
    out = _apply_fibrous_waveshaper(dummy_ir, dummy_vel, sample_rate, mat, 1.0)
    out += _apply_granular_stutter(dummy_ir, dummy_accel, sample_rate, mat, 1.0)
    
    stereo_left = out.copy()
    stereo_right = np.roll(out, 20)
    stereo_right[:20] = 0
    return np.vstack((stereo_left, stereo_right)).T