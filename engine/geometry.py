# --- START OF FILE engine/geometry.py ---
import os
import glob
import numpy as np
from PIL import Image
from typing import Dict, Tuple

def get_shape_type(template_name: str) -> str:
    if template_name == "bowed_coupled": return "violin"
    elif template_name == "flat_braced": return "guitar"
    elif template_name in ["drum_shell", "stretched_membrane", "cymbal_plate"]: return "circle"
    elif template_name in ["tuned_bar", "metal_bar"]: return "bar"
    elif template_name == "woodwind_bell": return "horn"
    elif "space" in template_name: return "hall"
    else: return "square"

def generate_instrument_mask(inst_dict: Dict, N: int = 128) -> np.ndarray:
    mask_filename = inst_dict.get("mask_image", "")
    m = np.zeros((N, N), dtype=np.float32)
    loaded_from_image = False
    
    # Супер-диагностика в консоль
    print(f"🔍 [Geometry] Анализ инструмента: '{inst_dict.get('name', 'Unknown')}'")
    print(f"🔍 [Geometry] Искомый файл картинки: '{mask_filename}'")
    
    if mask_filename:
        # Получаем абсолютный путь до папки проекта
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        masks_dir = os.path.join(base_dir, "masks")
        
        name_without_ext = os.path.splitext(mask_filename)[0]
        search_pattern = os.path.join(masks_dir, f"{name_without_ext}.*")
        found_files = glob.glob(search_pattern)
        
        if found_files:
            mask_path = found_files[0]
            try:
                img = Image.open(mask_path)
                
                # Обработка прозрачности
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
                    bg.paste(img, mask=img.split()[-1])
                    img = bg
                    
                img = img.convert("L")
                img = img.resize((N, N), Image.NEAREST)
                img_np = np.array(img, dtype=np.float32)
                
                for x in range(N):
                    for y in range(N):
                        img_y = (N - 1) - y 
                        img_x = x
                        if img_np[img_y, img_x] > 127.0:
                            m[x, y] = 1.0
                            
                print(f"✅ [Geometry] ЗАГРУЖЕНА МАСКА: {mask_path}")
                loaded_from_image = True
            except Exception as e:
                print(f"❌ [Geometry] ОШИБКА ЧТЕНИЯ '{mask_path}': {e}")
        else:
            print(f"⚠️ [Geometry] ФАЙЛ НЕ НАЙДЕН! Папка: '{masks_dir}', Искали: '{name_without_ext}.*'")
    else:
        print(f"❌ [Geometry] В пресете '{inst_dict.get('name')}' нет ключа 'mask_image'! Проверь файл instruments.py")

    # 2. FALLBACK: ПРОЦЕДУРНАЯ ГЕНЕРАЦИЯ
    if not loaded_from_image:
        template_name = inst_dict.get("resonator_template", "isotropic_plate")
        shape = get_shape_type(template_name)
        print(f"⚠️ [Geometry] Включаю базовую форму (Fallback): {shape}\n")

        for i in range(N):
            for j in range(N):
                x = (i - N/2) / (N/2)
                y = (j - N/2) / (N/2)
                
                if shape == "circle" and x*x + y*y < 0.9**2: m[i, j] = 1.0
                elif shape == "violin" and x**2 < (0.6 - y**2) * (0.3 + y**2) * 2.8: m[i, j] = 1.0
                elif shape == "guitar":
                    waist = 0.6 + 0.3 * np.cos(y * np.pi)
                    if x**2 < (0.8 - y**2) * waist: m[i, j] = 1.0
                elif shape == "bar" and abs(x) < 0.12 and abs(y) < 0.95: m[i, j] = 1.0
                elif shape == "horn" and y > -0.9 and y < 0.9 and abs(x) < (0.15 + 0.7 * (y + 0.9)/1.8): m[i, j] = 1.0
                elif shape == "hall" and abs(x) < 0.95 and abs(y) < 0.95:
                    if (i % 32 > 6) or (j % 32 > 6): m[i, j] = 1.0
                elif shape == "square" and abs(x) < 0.95 and abs(y) < 0.95: m[i, j] = 1.0
                    
    return m

def get_strike_point(inst_dict: Dict, N: int = 128) -> Tuple[int, int]:
    template_name = inst_dict.get("resonator_template", "isotropic_plate")
    if template_name in ["flat_braced", "bowed_coupled"]: return N // 2, N // 2 + int(N * 0.25) 
    elif template_name == "woodwind_bell": return N // 2, int(N * 0.1) 
    elif template_name in ["tuned_bar", "metal_bar"]: return N // 2, int(N * 0.2)
    else: return N // 2 + int(N * 0.06), N // 2 - int(N * 0.06)

def get_pickup_point(inst_dict: Dict, N: int = 128) -> Tuple[int, int]:
    template_name = inst_dict.get("resonator_template", "isotropic_plate")
    if template_name in ["flat_braced", "bowed_coupled"]: return N // 2, int(N * 0.15) 
    elif template_name == "woodwind_bell": return N // 2, int(N * 0.85)
    else: return N // 2, N // 2

def get_pickup_points_stereo(inst_dict: Dict, N: int = 128) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Апгрейд 2: Стерео-съем (Phase-Accurate Binaural)
    Возвращает две точки съема для честного 3D стерео с естественной разницей фаз.
    """
    template_name = inst_dict.get("resonator_template", "isotropic_plate")
    
    # Разносим левый и правый микрофоны по маске
    if template_name in ["flat_braced", "bowed_coupled"]: 
        return (N // 2 - int(N * 0.15), int(N * 0.15)), (N // 2 + int(N * 0.15), int(N * 0.15))
    elif template_name == "woodwind_bell": 
        return (N // 2 - int(N * 0.1), int(N * 0.85)), (N // 2 + int(N * 0.1), int(N * 0.85))
    elif template_name in ["tuned_bar", "metal_bar"]:
        return (N // 2 - int(N * 0.05), N // 2 + int(N * 0.2)), (N // 2 + int(N * 0.05), N // 2 - int(N * 0.2))
    else: 
        # Универсальный Phase-Accurate разнос (по диагонали от центра)
        return (N // 2 - int(N * 0.12), N // 2 - int(N * 0.12)), (N // 2 + int(N * 0.12), N // 2 + int(N * 0.12))
# --- END OF FILE engine/geometry.py ---