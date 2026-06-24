# --- START OF FILE engine/grid_builder.py ---
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_gradient_magnitude
from typing import Dict, Tuple

def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def build_heterogeneous_grids(mask_2d: np.ndarray, mat_dict: dict, base_db: dict = None) -> Tuple[dict, np.ndarray]:
    from config.materials import MATERIAL_PHYSICS
    if base_db is None:
        base_db = MATERIAL_PHYSICS
    
    h, w = mask_2d.shape
    
    # 1. Заливаем базовыми параметрами матрицы (строго float32 для Taichi)
    grids = {
        "rho": np.full((h, w), mat_dict.get("density", 1.0), dtype=np.float32),
        "E_l": np.full((h, w), mat_dict.get("E_long", 1.0), dtype=np.float32),
        "E_t": np.full((h, w), mat_dict.get("E_trans", mat_dict.get("E_long", 1.0)), dtype=np.float32),
        "loss": np.full((h, w), mat_dict.get("loss_factor", 0.01), dtype=np.float32),
        "visco": np.full((h, w), mat_dict.get("visco_gamma", 1e-5), dtype=np.float32)
    }
    
    rgb_map = np.zeros((h, w, 3), dtype=np.uint8)
    rgb_map[mask_2d > 0] = (0, 255, 0)
    
    inclusions = mat_dict.get("inclusions", [])
    
    # 2. Наслаиваем включения
    for inc in inclusions:
        if isinstance(inc["material"], str):
            inc_phys = base_db.get(inc["material"], {})
        else:
            inc_phys = inc["material"]
        
        ratio = float(inc.get("density_ratio", 0.1))
        pattern = inc.get("pattern", "specks")
        scale = float(inc.get("scale", 1.0))
        inc_color = hex_to_rgb(inc.get("color_hex", "#FFFFFF"))
        
        if pattern == "specks":
            noise = np.random.rand(h, w)
            inc_mask = (noise < ratio) & (mask_2d > 0)
        elif pattern == "veins":
            raw_noise = np.random.rand(h, w)
            smoothed = gaussian_filter(raw_noise, sigma=scale)
            threshold = np.percentile(smoothed[mask_2d > 0], 100 * (1.0 - ratio)) if np.any(mask_2d > 0) else 0.0
            inc_mask = (smoothed > threshold) & (mask_2d > 0)
        else:
            inc_mask = np.zeros((h, w), dtype=bool)

        if inc_phys:
            grids["rho"][inc_mask] = inc_phys.get("density", grids["rho"][inc_mask])
            grids["E_l"][inc_mask] = inc_phys.get("E_long", grids["E_l"][inc_mask])
            grids["E_t"][inc_mask] = inc_phys.get("E_trans", inc_phys.get("E_long", grids["E_t"][inc_mask]))
            grids["loss"][inc_mask] = inc_phys.get("loss_factor", grids["loss"][inc_mask])
            grids["visco"][inc_mask] = inc_phys.get("visco_gamma", grids["visco"][inc_mask])
        
        rgb_map[inc_mask] = inc_color

    # ---> НОВЫЙ БЛОК: Умное сглаживание акустических границ (Анти-резонанс) <---
    
    # A) Вычисляем "горячие точки" (края включений) через градиент упругости
    edges = gaussian_gradient_magnitude(grids["E_l"], sigma=0.5)
    edges_norm = edges / (np.max(edges) + 1e-10)
    
    # B) Инжектируем экстра-вязкость СТРОГО в стыки материалов.
    # ИСПРАВЛЕНИЕ: коэффициент вязкости понижен до 1.5e-6
    grids["visco"] += edges_norm * 1.5e-6 

    # C) Раздельное пространственное сглаживание:
    # 1. Структура (масса и жесткость) остается очень резкой (0.25) для сохранения "песочного/зернистого" хруста.
    grids["rho"] = gaussian_filter(grids["rho"], sigma=0.25)
    grids["E_l"] = gaussian_filter(grids["E_l"], sigma=0.25)
    grids["E_t"] = gaussian_filter(grids["E_t"], sigma=0.25)

    # 2. Поглощение и вязкость размываются сильно (0.8), создавая демпфирующее гало вокруг гранул.
    grids["loss"] = gaussian_filter(grids["loss"], sigma=0.5)
    grids["visco"] = gaussian_filter(grids["visco"], sigma=0.35)

    # Обрезаем все массивы строго по форме инструмента
    for key in grids:
        grids[key] = grids[key] * mask_2d

    return grids, rgb_map

def get_heterogeneous_material_description(mat_dict: dict) -> str:
    desc_text = f"<b>{mat_dict.get('name', 'Unknown')}</b><br>{mat_dict.get('description', '')}"
    if "inclusions" in mat_dict and mat_dict["inclusions"]:
        desc_text += "<br><br><b>Heterogeneous Structure:</b><ul>"
        for inc in mat_dict["inclusions"]:
            ui_desc = inc.get("ui_desc", "Custom inclusion")
            ratio_pct = int(float(inc.get("density_ratio", 0)) * 100)
            desc_text += f"<li><font color='{inc.get('color_hex', '#FFF')}'>■</font> <b>{ratio_pct}%</b>: {ui_desc}</li>"
        desc_text += "</ul>"
    return desc_text
# --- END OF FILE engine/grid_builder.py ---