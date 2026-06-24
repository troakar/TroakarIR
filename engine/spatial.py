import numpy as np
from scipy.signal import butter, lfilter
from typing import Dict, Union

def apply_true_physical_distance(stereo_ir: np.ndarray, sample_rate: int, distance_m: float) -> np.ndarray:
    """
    Применяет физическую модель отдаления микрофона.
    Включает сужение стереобазы, поглощение ВЧ воздухом и добавление диффузного поля.
    """
    if distance_m <= 0.1:
        return stereo_ir  # Контактный микрофон (Dry)
        
    nyquist = sample_rate / 2.0
    processed_ir = stereo_ir.copy()
    
    # 1. Потеря Proximity Effect (мягкий High-Pass)
    if distance_m > 1.0:
        hp_freq = np.clip(30.0 * np.log10(distance_m), 10.0, 150.0)
        b_hp, a_hp = butter(1, hp_freq / nyquist, btype='high')
        processed_ir[:, 0] = lfilter(b_hp, a_hp, processed_ir[:, 0])
        processed_ir[:, 1] = lfilter(b_hp, a_hp, processed_ir[:, 1])
        
    # 2. Поглощение высоких частот воздухом (Air Absorption)
    hf_cutoff = np.clip(20000.0 - (distance_m * 400.0), 3000.0, 20000.0)
    b_air, a_air = butter(1, hf_cutoff / nyquist, btype='low')
    
    processed_ir[:, 0] = lfilter(b_air, a_air, processed_ir[:, 0])
    processed_ir[:, 1] = lfilter(b_air, a_air, processed_ir[:, 1])
        
    # 3. Сужение стереобазы (Геометрический параллакс)
    width = 1.0 / max(1.0, distance_m * 0.3)
    mid = (processed_ir[:, 0] + processed_ir[:, 1]) / 2.0
    side = (processed_ir[:, 0] - processed_ir[:, 1]) / 2.0
    processed_ir[:, 0] = mid + side * width
    processed_ir[:, 1] = mid - side * width
    
    # 4. Соотношение прямого звука и диффузного поля
    direct_level = 1.0 / max(distance_m, 1.0)
    room_level = 0.15 + np.clip(distance_m * 0.015, 0.0, 0.6)
    
    # Комната (ранние отражения)
    early_delay_samples = int((10.0 + distance_m * 2.0) * sample_rate / 1000.0)
    room_signal = np.zeros_like(processed_ir)
    
    if early_delay_samples < len(stereo_ir):
        b_room, a_room = butter(1, 4500.0 / nyquist, btype='low')
        room_l = lfilter(b_room, a_room, stereo_ir[:, 0])
        room_r = lfilter(b_room, a_room, stereo_ir[:, 1])
        
        room_signal[early_delay_samples:, 0] = room_l[:-early_delay_samples]
        room_signal[early_delay_samples:, 1] = room_r[:-early_delay_samples]
        
# Финальный микс
    final_ir = (processed_ir * direct_level) + (room_signal * room_level)
    
    max_val = np.max(np.abs(final_ir))
    if max_val > 0:
        # ИСПРАВЛЕНИЕ: Подняли громкость экспорта до комфортного уровня
        final_ir = (final_ir / max_val) * 0.45
        
    return final_ir