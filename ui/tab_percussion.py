# --- START OF FILE ui/tab_percussion.py ---
import logging
import os
import numpy as np
from scipy.io import wavfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading

logger = logging.getLogger(__name__)

from config.materials import MATERIAL_PHYSICS, MATERIAL_CATEGORIES
from config.instruments import PERCUSSION_PRESETS, PERCUSSION_CATEGORIES
from engine.core_drums import generate_drum_ir
from ui.utils import build_category_dict

class PercussionTab(ttk.Frame):
    def __init__(self, parent, status_var):
        super().__init__(parent, padding="15")
        self.status_var = status_var
        self.columnconfigure(1, weight=1)
        self.build_ui()

    def build_ui(self):
        ttk.Label(self, text="Выберите ударный инструмент:", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.inst_var = tk.StringVar()
        self.inst_combo = ttk.Combobox(self, textvariable=self.inst_var, state="readonly")
        self.inst_categories = build_category_dict(PERCUSSION_PRESETS, PERCUSSION_CATEGORIES)
        self.inst_combo['values'] = [f"{k} ({name})" for cat, items in self.inst_categories.items() for k, name in items]
        self.inst_combo.current(0)
        self.inst_combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        self.inst_desc_label = ttk.Label(self, text="", wraplength=450, foreground="gray", font=("Arial", 9, "italic"))
        self.inst_desc_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 15))
        
        ttk.Label(self, text="Материал оболочки:", font=("Arial", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.shell_var = tk.StringVar()
        self.shell_combo = ttk.Combobox(self, textvariable=self.shell_var, state="readonly")
        self.shell_combo['values'] = [f"{k} ({name})" for cat, items in build_category_dict(MATERIAL_PHYSICS, MATERIAL_CATEGORIES).items() for k, name in items]
        self.shell_combo.current(0)
        self.shell_combo.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        ttk.Label(self, text="Материал мембраны / рамы:", font=("Arial", 10, "bold")).grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.head_var = tk.StringVar()
        self.head_combo = ttk.Combobox(self, textvariable=self.head_var, state="readonly")
        self.head_combo['values'] = [f"{k} ({name})" for cat, items in build_category_dict(MATERIAL_PHYSICS, MATERIAL_CATEGORIES).items() for k, name in items]
        self.head_combo.current(1)
        self.head_combo.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        ttk.Label(self, text="Материал проволоки / тарелки:", font=("Arial", 10, "bold")).grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.wire_var = tk.StringVar()
        self.wire_combo = ttk.Combobox(self, textvariable=self.wire_var, state="readonly")
        self.wire_combo['values'] = [f"{k} ({name})" for cat, items in build_category_dict(MATERIAL_PHYSICS, MATERIAL_CATEGORIES).items() for k, name in items]
        self.wire_combo.current(2)
        self.wire_combo.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 5))

        self.scale_var = tk.DoubleVar(value=1.0)
        ttk.Label(self, text="Размер инструмента:").grid(row=9, column=0, sticky="w")
        ttk.Scale(self, from_=0.3, to=3.0, variable=self.scale_var, orient="horizontal").grid(row=9, column=1, sticky="ew", pady=5)
        
        self.dur_var = tk.DoubleVar(value=0.8)
        ttk.Label(self, text="Время реверберации:").grid(row=10, column=0, sticky="w")
        ttk.Scale(self, from_=0.1, to=5.0, variable=self.dur_var, orient="horizontal").grid(row=10, column=1, sticky="ew", pady=5)
        
        self.snare_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Добавить дребезг проволоки/хвоста", variable=self.snare_var).grid(row=11, column=0, columnspan=2, sticky="w", pady=(5, 15))
        
        self.batch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Пакетный экспорт всех пресетов", variable=self.batch_var).grid(row=12, column=0, columnspan=2, sticky="w", pady=(0, 15))
        
        ttk.Button(self, text="Генерировать (Ударные)", command=self.generate).grid(row=13, column=0, columnspan=2, sticky="ew", ipady=8, pady=10)
        
        self.inst_combo.bind("<<ComboboxSelected>>", lambda e: self.update_desc())
        self.update_desc()

    def update_desc(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        self.inst_desc_label.config(text=PERCUSSION_PRESETS[inst_key].get("description", ""))

    def generate(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        shell_key = self.shell_var.get().split(" ")[0].strip()
        head_key = self.head_var.get().split(" ")[0].strip()
        wire_key = self.wire_var.get().split(" ")[0].strip()
        scale = self.scale_var.get()
        duration = self.dur_var.get()
        add_snare = self.snare_var.get()
        is_batch = self.batch_var.get()

        target_dir = filedialog.askdirectory()
        if not target_dir:
            logger.warning("User cancelled directory selection")
            return

        logger.info("Starting percussion IR generation")
        logger.info(f"  inst_key={inst_key}, shell={shell_key}, head={head_key}, wire={wire_key}, scale={scale}, duration={duration}s, add_snare={add_snare}, batch={is_batch}")
        self.status_var.set("Генерация ударных...")

        def task():
            try:
                if is_batch:
                    logger.info(f"Batch mode: processing {len(PERCUSSION_PRESETS)} presets")
                    for key, preset in PERCUSSION_PRESETS.items():
                        self.generate_single(key, preset, shell_key, head_key, wire_key, scale, duration, add_snare, target_dir)
                else:
                    self.generate_single(inst_key, PERCUSSION_PRESETS[inst_key], shell_key, head_key, wire_key, scale, duration, add_snare, target_dir)
                self.after(0, lambda: self.status_var.set("Экспорт ударных завершен"))
                messagebox.showinfo("Готово", "Перкуссионный импульс был сгенерирован")
            except Exception as e:
                logger.error(f"Percussion generation failed: {type(e).__name__}: {e}", exc_info=True)
                self.after(0, lambda: self.status_var.set("Ошибка генерации ударных"))
                messagebox.showerror("Сбой", str(e))

        threading.Thread(target=task, daemon=True).start()

    def generate_single(self, key, preset, shell_key, head_key, wire_key, scale, duration, add_snare, target_dir):
        logger.info(f"Generating preset: {key}")
        shell = MATERIAL_PHYSICS[shell_key]
        head = MATERIAL_PHYSICS[head_key]
        wire = MATERIAL_PHYSICS[wire_key]
        preset_copy = preset.copy()
        preset_copy["snare_rattle"] = 0.7 if add_snare else 0.0
        logger.info(f"  shell={shell_key}, head={head_key}, wire={wire_key}, snare_rattle={preset_copy['snare_rattle']}")

        logger.info(f"  Calling generate_physical_ir(inst_dict=preset_copy, mat_dict=head, def_mat_dict=shell, wire_mat_dict=wire, ...)")
        ir_data = generate_drum_ir(
            inst_dict=preset_copy,
            mat_dict=head,
            def_mat_dict=shell,
            shell_mat_dict=shell,
            wire_mat_dict=wire,
            user_scale=scale,
            duration=duration,
            sample_rate=44100,
            mic_distance_m=0.5,
            compensate_delay=False,
        )
        logger.info(f"  generate_physical_ir() returned shape={ir_data.shape}, dtype={ir_data.dtype}")
        output_path = os.path.join(target_dir, f"{key}.wav")
        logger.info(f"  Writing WAV: {output_path}")
        wavfile.write(output_path, 44100, ir_data.astype(np.float32))
        logger.info(f"  WAV write successful: {output_path}")
# --- END OF FILE ui/tab_percussion.py ---
