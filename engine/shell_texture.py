# dlc/dhol/engine/shell_texture.py
import os
import json
import math
import numpy as np
import scipy.io.wavfile as wav
from scipy.signal import butter, sosfilt, fftconvolve, lfilter
from functools import lru_cache

from engine.core_logging import core_logger

# ----------------------------------------------------------------------
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ТЕКСТУРНЫХ СЛОЁВ
# ----------------------------------------------------------------------

def _envelope_follower(signal: np.ndarray, fs: int, attack_ms: float = 1.0, release_ms: float = 50.0) -> np.ndarray:
    """
    Быстрый детектор огибающей. Оптимизирован через math.
    """
    alpha_attack = 1.0 - math.exp(-1.0 / (attack_ms * 0.001 * fs))
    alpha_release = 1.0 - math.exp(-1.0 / (release_ms * 0.001 * fs))
    env = np.zeros_like(signal)
    
    prev = 0.0
    for i, s in enumerate(np.abs(signal)):
        alpha = alpha_attack if s > prev else alpha_release
        prev = alpha * s + (1.0 - alpha) * prev
        env[i] = prev
    return env

def _generate_granular_layer(body_ir: np.ndarray, fs: int, material: dict, density_ratio: float = 1.0) -> np.ndarray:
    """
    Управляемый синтез сыпучих частиц (Ржавчина, Соль, Песок, Патина).
    """
    gran = material.get("granular", {})
    tactile = material.get("tactile_profile", {})
    
    # Проверка включения (с поддержкой старого tactile_profile)
    is_enabled = gran.get("enabled", tactile.get("granularity", 0.0) > 0.0)
    if not is_enabled:
        return np.zeros_like(body_ir)
    
    # Извлечение параметров Art Direction
    intensity = gran.get("intensity", tactile.get("granularity", 0.0)) * density_ratio
    brittleness = tactile.get("brittleness", 0.0)
    
    if intensity <= 0:
        return np.zeros_like(body_ir)
        
    freq_range = gran.get("freq_range", [2500.0, 12000.0])
    duration_range = gran.get("duration_range", [0.002, 0.012])
    
    # particle_count: плотность гранул
    p_count = gran.get("particle_count", 5000)
    density_mult = gran.get("density", 1.0)
    max_grains_per_sec = p_count * 0.5 * density_mult
    
    # Формирование формы осыпания
    env_power = gran.get("env_power", gran.get("exponential_rise", 1.5))
    
    # Огибающая (хвост длинный, чтобы ржавчина осыпалась после удара)
    envelope = _envelope_follower(body_ir, fs, attack_ms=1.0, release_ms=250.0)
    max_env = np.max(envelope)
    if max_env > 0:
        envelope = envelope / max_env
    else:
        return np.zeros_like(body_ir)
    
    grain_rate = max_grains_per_sec * envelope 
    
    out = np.zeros_like(body_ir)
    rng = np.random.RandomState(hash(str(material.get("name", ""))) & 0xFFFFFFFF)
    
    time_sec = 0.0
    dt = 1.0 / fs
    next_grain_time = 0.0
    n = 0
    len_out = len(out)
    
    while time_sec < len_out * dt and n < p_count * 2:  
        idx = int(time_sec * fs)
        if idx >= len_out:
            break
        
        current_rate = grain_rate[idx]
        current_env_val = envelope[idx] 
        
        if current_rate > 0 and time_sec >= next_grain_time:
            freq = rng.uniform(freq_range[0], freq_range[1])
            dur = rng.uniform(duration_range[0], duration_range[1])
            dur_samples = min(int(dur * fs), len_out - idx)
            
            if dur_samples > 0:
                t_grain = np.arange(dur_samples) / fs
                grain_env = np.exp(-t_grain / (dur * 0.35))
                
                # FM-хруст внутри гранулы (чем ниже частота, тем грязнее — идеально для ржавчины)
                noise_mod = rng.randn(dur_samples) * (0.5 + brittleness * 1.5)
                grain_sig = np.sin(2 * np.pi * freq * t_grain + noise_mod)
                
                # Амплитуда подчиняется кривой env_power (затухает гармонично)
                amp = 0.25 * intensity * density_ratio * (current_env_val ** env_power) * rng.uniform(0.4, 1.2)
                
                out[idx:idx+dur_samples] += grain_sig * grain_env * amp
            
            interval = 1.0 / max(current_rate, 1e-6)
            next_grain_time = time_sec + interval * rng.uniform(0.6, 1.4)
            n += 1
        
        time_sec += dt
    
    max_val = np.max(np.abs(out))
    if max_val > 0:
        out *= (0.4 / max_val) * intensity * density_ratio

    if core_logger is not None:
        core_logger.log_tactile_summary(material, {
            "granular_density": int(n),
            "particle_count": int(p_count),
            "density_ratio": float(density_ratio),
            "granular_peak_rate": float(np.max(grain_rate)),
            "granular_intensity": float(intensity)
        })

    return out

def _generate_fibrous_layer(body_ir: np.ndarray, fs: int, material: dict) -> np.ndarray:
    """Управляемый слой древесных волокон и скрипа."""
    fibr_cfg = material.get("fibrous", {})
    tactile = material.get("tactile_profile", {})
    
    is_enabled = fibr_cfg.get("enabled", tactile.get("fibrousness", 0.0) > 0)
    if not is_enabled:
        return np.zeros_like(body_ir)
        
    intensity = fibr_cfg.get("intensity", tactile.get("fibrousness", 0.0))
    if intensity <= 0:
        return np.zeros_like(body_ir)
        
    tension = fibr_cfg.get("tension", 1.0) # Влияет на высоту скрипа
    
    rng = np.random.RandomState(123)
    brown = np.cumsum(rng.randn(len(body_ir)))
    brown = brown / (np.max(np.abs(brown)) + 1e-6)
    
    # Гребенчатый фильтр
    delay_samples = max(1, int(0.0025 * fs / tension))
    mod_delay = max(1, int(0.0005 * fs / tension))
    
    comb = brown.copy()
    shifted_brown = np.roll(brown, delay_samples)
    shifted_brown[:delay_samples] = 0
    comb += 0.6 * shifted_brown
    
    # Модуляция задержки (разрыв волокон)
    mod_freq = fibr_cfg.get("tear_freq", 17.0)
    mod = 0.5 * (1 + np.sin(2 * np.pi * mod_freq * np.arange(len(body_ir)) / fs))
    shifted_mod = np.roll(comb, mod_delay)
    shifted_mod[:mod_delay] = 0
    comb += 0.3 * shifted_mod * mod
    
    env = _envelope_follower(body_ir, fs, attack_ms=0.5, release_ms=40.0)
    attack_deriv = np.gradient(env)
    attack_deriv = np.maximum(0, attack_deriv)
    
    max_deriv = np.max(attack_deriv)
    if max_deriv > 0:
        attack_deriv /= max_deriv
    
    out = comb * attack_deriv * intensity
    out = np.tanh(out * 2.0) * 0.3 * intensity

    if core_logger is not None:
        core_logger.log_tactile_summary(material, {
            "fibrous_intensity": float(intensity),
            "fibrous_tension": float(tension),
            "fibrous_tear_freq": float(mod_freq),
            "fibrous_event_index": int(np.sum(attack_deriv > 0.01))
        })

    return out

def _generate_fluid_layer(body_ir: np.ndarray, fs: int, material: dict) -> np.ndarray:
    """Управляемый слой жидкостной флуктуации."""
    fluid_cfg = material.get("fluid", {})
    tactile = material.get("tactile_profile", {})
    
    is_enabled = fluid_cfg.get("enabled", tactile.get("fluidity", 0.0) > 0)
    if not is_enabled:
        return np.zeros_like(body_ir)
        
    intensity = fluid_cfg.get("intensity", tactile.get("fluidity", 0.0))
    if intensity <= 0:
        return np.zeros_like(body_ir)
    
    lfo_range = fluid_cfg.get("lfo_freq_range", [5.0, 20.0])
    lfo_freq = lfo_range[0] + intensity * (lfo_range[1] - lfo_range[0])
    
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * lfo_freq * np.arange(len(body_ir)) / fs)
    
    rng = np.random.RandomState(321)
    noise = rng.randn(len(body_ir))
    sos_hp = butter(2, 200.0, 'hp', fs=fs, output='sos')
    noise = sosfilt(sos_hp, noise)
    
    out = (body_ir * lfo * 0.5) + (noise * 0.02)
    out *= intensity * 0.5

    if core_logger is not None:
        core_logger.log_tactile_summary(material, {
            "fluid_intensity": float(intensity),
            "fluid_lfo_freq": float(lfo_freq)
        })

    return out

def _process_inclusions(body_ir: np.ndarray, fs: int, material: dict) -> np.ndarray:
    inclusions = material.get("inclusions", [])
    if not inclusions:
        return np.zeros_like(body_ir)
    
    total = np.zeros_like(body_ir)
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
        pattern = inc.get("pattern", "specks")
        
        # --- СВЕРХГИБКАЯ СБОРКА ВИРТУАЛЬНОГО МАТЕРИАЛА ВКЛЮЧЕНИЯ ---
        virtual_mat = inc_mat.copy() if isinstance(inc_mat, dict) else {}
        
        for key in ["granular", "fibrous", "fluid", "tactile_profile"]:
            if key in inc:
                virtual_mat[key] = {**virtual_mat.get(key, {}), **inc[key]}
        
        virtual_mat["name"] = f"{material.get('name', 'base')}_inc_{virtual_mat.get('name', 'generic')}"
        
        # ИНИЦИАЛИЗАЦИЯ ИСПРАВЛЕНА: rng теперь доступен для любого паттерна (veins и specks)
        rng = np.random.RandomState(hash(str(virtual_mat.get("name", ""))) & 0xFFFFFFFF)
        
        if pattern == "veins":
            env = _envelope_follower(body_ir, fs, attack_ms=5.0, release_ms=250.0)
            noise = rng.randn(len(body_ir))
            
            freq_range = virtual_mat.get("granular", {}).get("freq_range", [500.0, 4000.0])
            sos_bp = butter(2, freq_range, 'bp', fs=fs, output='sos')
            noise = sosfilt(sos_bp, noise)
            
            layer = noise * env * density_ratio * 0.4
        else:
            layer = _generate_granular_layer(body_ir, fs, virtual_mat, density_ratio)

        if core_logger is not None and density_ratio > 0.0:
            collision_time_ms = int(np.clip(rng.uniform(2.0, 80.0), 2.0, 80.0))
            amplitude_db = float(-10.0 - density_ratio * 20.0)
            detail = f"Collision with {virtual_mat.get('name', 'inclusion')} at T+{collision_time_ms}ms, amplitude: {amplitude_db:.1f}dB"
            core_logger.log_inclusion_collision(material, {
                "detail": detail,
                "value": {
                    "time_ms": collision_time_ms,
                    "amplitude_db": amplitude_db,
                    "material": virtual_mat.get("name", "inclusion"),
                    "pattern": pattern
                }
            })
        
        total += layer
    return total

# ----------------------------------------------------------------------
#  ОСНОВНОЙ МОДАЛЬНЫЙ СИНТЕЗ
# ----------------------------------------------------------------------

@lru_cache(maxsize=32)
def _generate_msae_texture_cached(mat_json: str, fs: int) -> np.ndarray:
    mat = json.loads(mat_json)
    mat_name = mat.get("name", "Unknown Material")
    print(f"\n🔬 [MSAE V4 Directable] Рендер текстуры Art-Direction: {mat_name}")
    
    duration = 2.8 
    len_t = int(fs * duration)
    t = np.arange(len_t) / fs
    
    E_long = mat.get("E_long", 10.0)
    E_trans = mat.get("E_trans", E_long)
    density = mat.get("density", 1.0)
    loss = max(0.00005, mat.get("loss_factor", 0.02))
    visco = mat.get("visco_gamma", 1e-5)
    
    fluidity = mat.get("fluid", {}).get("intensity", mat.get("tactile_profile", {}).get("fluidity", 0.0))
    rng = np.random.RandomState(int(E_long * 100 + density * 10))
    
    # --- 1. Модальный резонанс корпуса ---
    modal_IR = np.zeros(len_t, dtype=np.float32)
    modes_count = 0
    max_modes = 2500 if E_long > 40.0 else 1200
    
    for m in range(1, 40):
        for n in range(1, 40):
            if modes_count >= max_modes: break
            
            Lx = 1.0 + rng.uniform(-0.05, 0.05)
            Ly = 1.0 + rng.uniform(-0.05, 0.05)
            k_m = m / Lx
            k_n = n / Ly
            stiffness = (E_long * k_m**4) + (E_trans * k_n**4) + (np.sqrt(E_long * E_trans) * 2 * k_m**2 * k_n**2)
            freq = 40.0 * np.sqrt(stiffness / density)
            freq *= (1.0 + 0.0005 * (m**2 + n**2))
            
            if 20.0 < freq < fs * 0.48:
                amp = 1.0 / ((m * n)**0.65)
                
                visco_damp = min(freq**2 * visco * 5e3, 300.0) 
                damp = (freq * loss * 1.2) + visco_damp
                
                phase = 2.0 * np.pi * freq * t
                env = np.exp(-damp * t)
                
                if fluidity > 0.0 and freq < 800.0:
                    phase += (0.01 * fluidity) * np.sin(2.0 * np.pi * 12.0 * t) * env
                
                modal_IR += amp * np.sin(phase) * env
                modes_count += 1
                
                if E_long > 50.0 and rng.rand() > 0.5:
                    freq_split = freq * rng.uniform(0.995, 1.005)
                    phase_s = 2.0 * np.pi * freq_split * t
                    modal_IR += (amp * 0.7) * np.sin(phase_s) * env
                    modes_count += 1
                    
        if modes_count >= max_modes: break
        
    print(f"   ➤ Модальный банк: {modes_count} гармоник")
    
    # --- 2. Возбудитель и свёртка ---
    exciter = np.zeros(len_t, dtype=np.float32)
    exciter[0] = 1.0
    
    fibr = mat.get("fibrous", {}).get("intensity", mat.get("tactile_profile", {}).get("fibrousness", 0.0))
    if fibr > 0:
        tear_len = int(fs * 0.035)
        tear = rng.randn(tear_len) ** 3
        tear *= np.exp(-np.arange(tear_len) / (fs * 0.008))
        exciter[:tear_len] += tear * fibr * 0.4
        
    cutoff = np.clip(1000.0 * np.sqrt(E_long), 200.0, fs * 0.45)
    sos_lp = butter(2, cutoff, 'lp', fs=fs, output='sos')
    exciter = sosfilt(sos_lp, exciter)
    
    print(f"   ➤ Тензорная конволюция корпуса...")
    body_response = fftconvolve(exciter, modal_IR)[:len_t]
    max_body = np.max(np.abs(body_response))
    if max_body > 0:
        body_response /= max_body
    
    # --- 3. Генерация Art-Direction слоёв ---
    print(f"   ➤ Синтез направленных суб-слоёв...")
    fibrous_layer = _generate_fibrous_layer(body_response, fs, mat)
    fluid_layer = _generate_fluid_layer(body_response, fs, mat)
    self_granular = _generate_granular_layer(body_response, fs, mat, density_ratio=1.0)
    inclusion_layer = _process_inclusions(body_response, fs, mat)
    
    # --- 4. Смешивание и финализация ---
    final_ir = body_response.copy()
    final_ir += fibrous_layer * 0.7
    final_ir += fluid_layer * 0.5
    final_ir += self_granular * 1.2  
    final_ir += inclusion_layer * 1.5 
    
    final_ir = np.tanh(final_ir * 1.2)
    fade_t = t / (0.8 + 2.0 * (1.0 - loss))
    final_ir *= np.exp(-fade_t)

    if core_logger is not None:
        core_logger.log_physics_summary(mat, "Shell texture synthesis summary", {
            "modal_bank": int(modes_count),
            "E_long": float(E_long),
            "E_trans": float(E_trans),
            "density": float(density),
            "loss_factor": float(loss),
            "visco_gamma": float(visco),
            "fluidity": float(fluidity),
            "peak_body_response": float(np.max(np.abs(body_response)))
        })

    # Экспорт
    export_dir = "impulses/msae_textures"
    os.makedirs(export_dir, exist_ok=True)
    safe_name = "".join([c if c.isalnum() else "_" for c in mat_name])
    file_name = f"MSAE_v4_{safe_name}_E{E_long:.1f}.wav"
    file_path = os.path.join(export_dir, file_name)
    
    wav_data = np.clip(final_ir, -1.0, 1.0).astype(np.float32)
    wav.write(file_path, fs, wav_data)
    
    print(f"🔊 [MSAE V4] Текстура готова: {file_path}\n")
    return final_ir

# ----------------------------------------------------------------------
#  ПУБЛИЧНОЕ API
# ----------------------------------------------------------------------
# === ЗАМЕНИ ЭТУ ФУНКЦИЮ В shell_texture.py ===
def apply_dynamic_shell_texture(mat: dict, fs: int, target_len: int,
                                strike_force: float, fatness: float, articulation: str) -> np.ndarray:
    mat_json = json.dumps(mat, sort_keys=True)
    raw_tex = _generate_msae_texture_cached(mat_json, fs)
    
    out = np.zeros(target_len)
    copy_len = min(target_len, len(raw_tex))
    out[:copy_len] = raw_tex[:copy_len]
    
    t = np.arange(target_len) / fs
    decay_time = 0.15 + (strike_force * 0.35) + (fatness * 0.5)
    
    if articulation == "wood_click":
        decay_time *= 0.5
    elif articulation == "mute":
        decay_time *= 0.2
    elif articulation in ["chapa", "clap_tek"]:
        decay_time *= 0.6
        
    env = np.exp(-t / decay_time)
    attack_len = int(0.001 * fs)
    if attack_len > 0 and target_len > attack_len:
        env[:attack_len] *= np.linspace(0.0, 1.0, attack_len) ** 2
        
    # ГРОМКОСТЬ: Масштабируем общую амплитуду текстуры по силе удара
    out *= env * (strike_force ** 1.3)
    
    # ТЕМБР (Dynamic Low-Pass): Срезаем яркий клик на тихих ударах
    # При strike_force = 1.0 (сильный удар) фильтр открыт до Nyquist (не влияет)
    # При strike_force = 0.12 (vel: 16) срез опускается до ~1400 Гц, делая щелчок мягким и глухим
    nyquist = fs / 2.0
    dyn_cutoff = np.clip(nyquist * (strike_force ** 1.1), 200.0, nyquist - 200.0)
    
    if dyn_cutoff < nyquist - 500.0:
        sos_dyn = butter(2, dyn_cutoff, 'lp', fs=fs, output='sos')
        out = sosfilt(sos_dyn, out)
        
    if fatness > 0.0:
        drive = 1.0 + (fatness * 4.0)
        out = np.tanh(out * drive) * 0.7
        
    alpha = 0.40
    out = lfilter([alpha], [1, alpha - 1], out)
        
    return out
