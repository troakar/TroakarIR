# --- START OF FILE ui/tab_acoustic.py ---
import logging
import os
import numpy as np
from scipy.io import wavfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading

logger = logging.getLogger(__name__)

from config.materials import MATERIAL_PHYSICS, MATERIAL_CATEGORIES
from config.instruments import RESONATOR_TEMPLATES, INSTRUMENT_PRESETS, INSTRUMENT_CATEGORIES
from engine.core_dsp import generate_physical_ir
from ui.utils import build_category_dict

class AcousticTab(ttk.Frame):
    def __init__(self, parent, status_var):
        super().__init__(parent, padding="15")
        self.status_var = status_var
        self.columnconfigure(1, weight=1)
        self.build_ui()

    def build_ui(self):
        ttk.Label(self, text="Форма корпуса / Зал:", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.inst_var = tk.StringVar()
        self.inst_combo = ttk.Combobox(self, textvariable=self.inst_var, state="readonly")
        self.inst_categories = build_category_dict(INSTRUMENT_PRESETS, INSTRUMENT_CATEGORIES)
        self.inst_combo['values'] = [f"{k} ({name})" for cat, items in self.inst_categories.items() for k, name in items]
        self.inst_combo.current(0)
        self.inst_combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        self.inst_desc_label = ttk.Label(self, text="", wraplength=450, foreground="gray", font=("Arial", 9, "italic"))
        self.inst_desc_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 15))
        
        ttk.Label(self, text="Материал деки / Стен:", font=("Arial", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.mat_var = tk.StringVar()
        self.mat_combo = ttk.Combobox(self, textvariable=self.mat_var, state="readonly")
        self.mat_categories = build_category_dict(MATERIAL_PHYSICS, MATERIAL_CATEGORIES)
        self.mat_combo['values'] = [f"{k} ({name})" for cat, items in self.mat_categories.items() for k, name in items]
        self.mat_combo.current(0)
        self.mat_combo.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        self.mat_desc_label = ttk.Label(self, text="", wraplength=450, foreground="gray", font=("Arial", 9, "italic"))
        self.mat_desc_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 15))
        
        # --- ПОЛЗУНОК МАСШТАБА ---
        self.scale_var = tk.DoubleVar(value=1.0)
        ttk.Label(self, text="Геометрия / Размер:").grid(row=6, column=0, sticky="w")
        ttk.Scale(self, from_=0.3, to=3.0, variable=self.scale_var, orient="horizontal", command=self.update_labels).grid(row=6, column=1, sticky="ew", pady=5)
        self.scale_val_lbl = ttk.Label(self, text="1.00x", font=("Arial", 9, "bold"), foreground="darkcyan")
        self.scale_val_lbl.grid(row=7, column=1, sticky="e")
        
        # --- ПОЛЗУНОК СУСТЕЙНА ---
        self.dur_var = tk.DoubleVar(value=1.5)
        ttk.Label(self, text="Сустейн (Макс. хвост):").grid(row=8, column=0, sticky="w")
        ttk.Scale(self, from_=0.1, to=5.0, variable=self.dur_var, orient="horizontal", command=self.update_labels).grid(row=8, column=1, sticky="ew", pady=5)
        self.dur_val_lbl = ttk.Label(self, text="1.50 сек", font=("Arial", 9, "bold"))
        self.dur_val_lbl.grid(row=9, column=1, sticky="e")
        
        # --- ПОЛЗУНОК МИКРОФОНА ---
        self.mic_var = tk.DoubleVar(value=10.0)
        ttk.Label(self, text="Дистанция микрофона:").grid(row=10, column=0, sticky="w")
        ttk.Scale(self, from_=0.0, to=40.0, variable=self.mic_var, orient="horizontal", command=self.update_labels).grid(row=10, column=1, sticky="ew", pady=5)
        self.mic_val_lbl = ttk.Label(self, text="10.0 м", font=("Arial", 9, "bold"))
        self.mic_val_lbl.grid(row=11, column=1, sticky="e")
        
        # --- ЧЕКБОКС АВТО-ОБРЕЗКИ ---
        self.autocrop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="✂️ Auto-Crop (Отсекать мертвый хвост тишины)", variable=self.autocrop_var).grid(row=12, column=0, columnspan=2, sticky="w", pady=(10, 5))
        
        ttk.Button(self, text="Генерировать (Акустика)", command=self.generate).grid(row=13, column=0, columnspan=2, sticky="ew", ipady=8, pady=20)
        
        self.inst_combo.bind("<<ComboboxSelected>>", lambda e: self.update_all())
        self.mat_combo.bind("<<ComboboxSelected>>", lambda e: self.update_all())
        self.update_all()

    def update_all(self):
        self.update_desc()
        self.update_labels()

    def update_desc(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        mat_key = self.mat_var.get().split(" ")[0].strip()
        self.inst_desc_label.config(text=INSTRUMENT_PRESETS[inst_key].get("description", ""))
        self.mat_desc_label.config(text=MATERIAL_PHYSICS[mat_key].get("description", ""))

    def update_labels(self, *args):
        # 1. Считаем физический размер
        inst_key = self.inst_var.get().split(" ")[0].strip()
        inst = INSTRUMENT_PRESETS[inst_key]
        template = RESONATOR_TEMPLATES[inst["resonator_template"]]
        scale = self.scale_var.get()
        
        if template.get("is_space", False):
            base_m = template.get("base_size", 10.0)
            size_m = base_m * scale
            self.scale_val_lbl.config(text=f"{scale:.2f}x (Объем: ~{size_m:.1f} метров)")
        else:
            # Акустическая оценка размера (Длина полуволны базовой частоты в воздухе)
            base_f = inst.get("A0", inst.get("low_cut", 150.0))
            base_m = (343.0 / base_f) / 2.0  # Формула L = C / (2*F)
            size_m = base_m * scale
            
            if size_m < 0.05:
                self.scale_val_lbl.config(text=f"{scale:.2f}x (Габарит: ~{size_m * 1000:.0f} мм)")
            elif size_m < 1.0:
                self.scale_val_lbl.config(text=f"{scale:.2f}x (Габарит: ~{size_m * 100:.1f} см)")
            else:
                self.scale_val_lbl.config(text=f"{scale:.2f}x (Габарит: ~{size_m:.2f} м)")

        # 2. Сустейн
        self.dur_val_lbl.config(text=f"Макс. предел: {self.dur_var.get():.2f} сек")
        
        # 3. Микрофон
        mic = self.mic_var.get()
        if mic < 0.1:
            mic_str = "Контактный (Пьезо)"
        elif mic < 5.0:
            mic_str = f"{mic:.1f} м (Ближнее поле)"
        else:
            mic_str = f"{mic:.1f} м (Дальнее поле)"
        self.mic_val_lbl.config(text=mic_str)


    def generate(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        mat_key = self.mat_var.get().split(" ")[0].strip()
        scale = self.scale_var.get()
        duration = self.dur_var.get()
        mic_dist = float(self.mic_var.get())
        auto_crop = self.autocrop_var.get()
        
        file_path = filedialog.asksaveasfilename(defaultextension=".wav", initialfile=f"{inst_key}_{mat_key}.wav")
        if not file_path: 
            logger.warning("User cancelled file save dialog")
            return
            
        logger.info("Starting acoustic IR generation")
        logger.info(f"  inst_key={inst_key}, mat_key={mat_key}, scale={scale}, duration={duration}s, mic_dist={mic_dist}m")
            
        self.status_var.set("Расчет 3D уравнений акустики...")
        self.update_idletasks()
        
        inst = INSTRUMENT_PRESETS[inst_key]
        mat = MATERIAL_PHYSICS[mat_key]
        def_mat = MATERIAL_PHYSICS[RESONATOR_TEMPLATES[inst["resonator_template"]]["default_material"]]
        
        def task():
            try:
                ir_data = generate_physical_ir(inst_dict=inst, mat_dict=mat, def_mat_dict=def_mat, user_scale=scale, duration=duration, sample_rate=44100, mic_distance_m=mic_dist)
                
                # === МАГИЯ АВТО-ОБРЕЗКИ (AUTO-CROP) ===
                if auto_crop:
                    # Вычисляем огибающую энергии (сумма модулей стерео-каналов)
                    env = np.abs(ir_data[:, 0]) + np.abs(ir_data[:, 1]) if ir_data.ndim > 1 else np.abs(ir_data)
                    max_amp = np.max(env)
                    
                    if max_amp > 0:
                        # Ищем момент, где сигнал падает ниже -60 дБ (0.1% от пика громкости)
                        threshold = max_amp * 0.001
                        active_indices = np.where(env > threshold)[0]
                        
                        if len(active_indices) > 0:
                            last_active_idx = active_indices[-1]
                            # Добавляем 50 миллисекунд паддинга (тишины) чтобы не рубануть жестко
                            pad_samples = int(44100 * 0.05)
                            crop_idx = min(len(ir_data), last_active_idx + pad_samples)
                            
                            # Делаем мягкий 10-миллисекундный Fade-out на самом конце среза
                            fade_samples = min(int(44100 * 0.01), crop_idx)
                            fade_curve = np.linspace(1.0, 0.0, fade_samples) ** 2
                            
                            ir_data = ir_data[:crop_idx]
                            
                            if ir_data.ndim > 1:
                                ir_data[-fade_samples:, 0] *= fade_curve
                                ir_data[-fade_samples:, 1] *= fade_curve
                            else:
                                ir_data[-fade_samples:] *= fade_curve
                                
                            logger.info(f"Auto-Crop: Убрано {(len(env) - crop_idx) / 44100:.2f} сек тишины.")
                
                wavfile.write(file_path, 44100, ir_data.astype(np.float32))
                self.after(0, lambda: self.status_var.set(f"Успех: {os.path.basename(file_path)}"))
                messagebox.showinfo("Готово", "Импульс сгенерирован и обрезан!")
            except Exception as e:
                logger.error(f"Generation failed: {type(e).__name__}: {e}", exc_info=True)
                self.after(0, lambda: self.status_var.set("Ошибка генерации"))
                messagebox.showerror("Сбой", str(e))

        threading.Thread(target=task, daemon=True).start()
# --- END OF FILE ui/tab_acoustic.py ---