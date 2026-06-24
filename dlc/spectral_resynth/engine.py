import os
import json
import numpy as np
import librosa
import soundfile as sf
import sounddevice as sd
from scipy.signal import fftconvolve
import importlib
import logging

logging.getLogger('numba').setLevel(logging.WARNING)

# ======================================================================
#  САМОЗАЛЕЧИВАЮЩИЙСЯ ИМПОРТ ДВИЖКОВ И МАТЕРИАЛОВ (БЕЗЛИМИТНЫЙ ПОИСК)
# ======================================================================

_generate_msae_texture_cached = None
generate_tactile_profile = None
MATERIAL_PHYSICS = None
blend_materials = None

# 1. Ищем материалы (в корне или внутри dlc)
materials_attempts = [
    "config.materials",
    "dhol.config.materials",
    "dlc.dhol.config.materials"
]
for mod_name in materials_attempts:
    try:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "MATERIAL_PHYSICS") and hasattr(mod, "blend_materials"):
            MATERIAL_PHYSICS = getattr(mod, "MATERIAL_PHYSICS")
            blend_materials = getattr(mod, "blend_materials")
            # print(f"DEBUG: Материалы успешно импортированы из {mod_name}")
            break
    except ImportError:
        continue

# 2. Ищем физический и тактильный движки по всем возможным явным путям
engine_attempts = [
    ("engine.shell_texture", ["_generate_msae_texture_cached", "generate_tactile_profile"]),
    ("dhol.engine.shell_texture", ["_generate_msae_texture_cached", "generate_tactile_profile"]),
    ("dlc.dhol.engine.shell_texture", ["_generate_msae_texture_cached", "generate_tactile_profile"]),
    ("engine.tactile", ["generate_tactile_profile"]),
    ("engine.tactile_engine", ["generate_tactile_profile"]),
]

for mod_name, func_names in engine_attempts:
    try:
        mod = importlib.import_module(mod_name)
        for func_name in func_names:
            if hasattr(mod, func_name) and globals()[func_name] is None:
                globals()[func_name] = getattr(mod, func_name)
                # print(f"DEBUG: Функция {func_name} успешно импортирована из {mod_name}")
    except ImportError:
        continue

# Проверка критических импортов перед запуском
missing = []
if _generate_msae_texture_cached is None: missing.append("_generate_msae_texture_cached")
if generate_tactile_profile is None: missing.append("generate_tactile_profile")
if MATERIAL_PHYSICS is None: missing.append("MATERIAL_PHYSICS")

if missing:
    raise ImportError(
        f"🚨 Критическая ошибка импорта! Не найдены модули: {missing}\n"
        f"Убедись, что файлы config/materials.py и shell_texture.py лежат в "
        f"корневых папках проекта или внутри dlc/dhol/!"
    )

# ======================================================================
#  ОСНОВНОЙ АЛХИМИЧЕСКИЙ ДВИЖОК
# ======================================================================

def process_hybrid_material(file_path, mat_a_key, mat_b_key, blend_ratio, mode, strike_force, fatness, dry_wet=1.0):
    """
    Алхимический котел с ручкой Dry/Wet (Flat Mix).
    """
    y, sr = librosa.load(file_path, sr=None)
    
    # Если Dry/Wet в ноль, мгновенно отдаем оригинал
    if dry_wet <= 0.01:
        max_val = np.max(np.abs(y))
        if max_val > 0:
            y = (y / max_val) * 0.95
        return y, sr
        
    # 1. Берем материалы и варим сплав
    mat_a = MATERIAL_PHYSICS.get(mat_a_key)
    mat_b = MATERIAL_PHYSICS.get(mat_b_key)
    mat = blend_materials(mat_a, mat_b, blend_ratio)
    
    # 2. Рендерим акустический слепок
    mat_json = json.dumps(mat, sort_keys=True)
    ir_raw = _generate_msae_texture_cached(mat_json, sr)
    
    t = np.arange(len(y)) / sr
    nyquist = sr / 2.0
    
    if mode == "Symbiosis":
        y_harm, y_perc = librosa.effects.hpss(y, margin=(1.2, 1.2))
        body_reson = fftconvolve(y_harm, ir_raw)[:len(y)]
        
        vel = np.gradient(y_perc)
        acc = np.gradient(vel)
        stress = np.abs(vel) * mat.get("E_long", 10.0) * 0.1
        
        tactile_noise = generate_tactile_profile(
            mat, t, y_perc, vel, acc, stress, 
            sample_rate=sr, nyquist=nyquist, is_space=False, 
            fatness=fatness, strike_force=strike_force
        )
        y_wet = body_reson + tactile_noise
    else:
        body_reson = fftconvolve(y, ir_raw)[:len(y)]
        
        vel = np.gradient(y)
        acc = np.gradient(vel)
        stress = np.abs(vel) * mat.get("E_long", 10.0) * 0.1
        
        tactile_noise = generate_tactile_profile(
            mat, t, body_reson, vel, acc, stress, 
            sample_rate=sr, nyquist=nyquist, is_space=False, 
            fatness=fatness, strike_force=strike_force
        )
        y_wet = body_reson + tactile_noise

    min_len = min(len(y), len(y_wet))
    y_dry = y[:min_len]
    y_wet = y_wet[:min_len]
    
    y_final = (y_dry * (1.0 - dry_wet)) + (y_wet * dry_wet)

    max_val = np.max(np.abs(y_final))
    if max_val > 0:
        y_final = (y_final / max_val) * 0.95
        
    return y_final, sr

def play_preview(audio_data, sr):
    sd.stop()
    sd.play(audio_data, sr)

def stop_preview():
    sd.stop()

def batch_process(file_paths, out_dir, mat_a_key, mat_b_key, blend_ratio, mode, strike_force, fatness, dry_wet):
    os.makedirs(out_dir, exist_ok=True)
    for path in file_paths:
        try:
            y_out, sr = process_hybrid_material(path, mat_a_key, mat_b_key, blend_ratio, mode, strike_force, fatness, dry_wet)
            filename = os.path.basename(path)
            name, ext = os.path.splitext(filename)
            out_path = os.path.join(out_dir, f"{name}_{mat_a_key}_{mode[:3]}_processed{ext}")
            sf.write(out_path, y_out, sr)
        except Exception as e:
            print(f"Ошибка с файлом {path}: {e}")