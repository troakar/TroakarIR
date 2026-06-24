# --- START OF FILE ui/tab_taichi.py ---
import os
import re
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from scipy.io import wavfile

from config.materials import MATERIAL_PHYSICS, MATERIAL_CATEGORIES, blend_materials
from config.instruments import INSTRUMENT_PRESETS, PERCUSSION_PRESETS, INSTRUMENT_CATEGORIES, PERCUSSION_CATEGORIES
from engine.core_taichi import generate_fdtd_ir, get_resonance_info, note_name_to_hz
from engine.geometry import generate_instrument_mask, get_strike_point, get_pickup_point, get_pickup_points_stereo
from engine.grid_builder import build_heterogeneous_grids, get_heterogeneous_material_description

try:
    from ui.utils import build_category_dict
except ImportError:
    def build_category_dict(presets, categories):
        result = {cat_id: [] for cat_id in categories}
        for key, preset in presets.items():
            cat = preset.get("category")
            if cat in result:
                result[cat].append((key, preset.get("name", key)))
            else:
                if "other" not in result:
                    result["other"] = []
                result["other"].append((key, preset.get("name", key)))
        return {k: v for k, v in result.items() if v}

ALL_PRESETS = {**INSTRUMENT_PRESETS, **PERCUSSION_PRESETS}
ALL_CATEGORIES = {**INSTRUMENT_CATEGORIES, **PERCUSSION_CATEGORIES}

class TaichiTab(ttk.Frame):
    def __init__(self, parent, status_var):
        super().__init__(parent, padding="15")
        self.status_var = status_var
        
        # Раздельное хранение кастомных координат для полноценного Stereo-съема
        self.custom_strike = None
        self.custom_pickup_L = None
        self.custom_pickup_R = None
        
        self.is_stereo_var = tk.BooleanVar(value=False)
        self.use_alloy_var = tk.BooleanVar(value=False)
        self.use_degradation_var = tk.BooleanVar(value=False)
        self.force_var = tk.DoubleVar(value=1.0) # Сила удара / Давление смычка
        
        self._last_inst = None
        self._last_scale = None
        
        # Переменная выбора активного датчика для перетаскивания (strike, pickup_L, pickup_R)
        self.edit_mode = tk.StringVar(value="strike")
        
        # Трассировка изменений опций
        self.is_stereo_var.trace_add("write", lambda *args: (self.rebuild_point_frame_widgets(), self.update_all()))
        self.use_alloy_var.trace_add("write", lambda *args: self.update_widget_states())
        self.use_degradation_var.trace_add("write", lambda *args: self.update_widget_states())
        
        # Конфигурируем главную сетку вкладки (2 колонки)
        self.columnconfigure(0, weight=1, minsize=380) # Левая панель
        self.columnconfigure(1, weight=2)               # Правая панель
        self.rowconfigure(0, weight=1)
        
        self.build_ui()
        
    def build_ui(self):
        # Создаем изолированные контейнеры-панели
        left_panel = ttk.Frame(self, padding=(0, 0, 15, 0))
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.columnconfigure(0, weight=1)
        left_panel.columnconfigure(1, weight=1)
        
        right_panel = ttk.Frame(self)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.columnconfigure(1, weight=0) # Не растягиваем среднюю панель
        right_panel.columnconfigure(2, weight=1)
        
        # ==========================================
        #      ЛЕВАЯ ПАНЕЛЬ (НАСТРОЙКИ И СЛАЙДЕРЫ)
        # ==========================================
        
        # 1. Выбор Инструмента
        ttk.Label(left_panel, text="Инструмент / Пресет:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(5, 2))
        self.inst_var = tk.StringVar()
        self.inst_combo = ttk.Combobox(left_panel, textvariable=self.inst_var, state="readonly")
        preset_dict = build_category_dict(ALL_PRESETS, ALL_CATEGORIES)
        self.inst_combo['values'] = [f"{k} ({name})" for cat, items in preset_dict.items() for k, name in items]
        self.inst_combo.current(0)
        self.inst_combo.grid(row=0, column=1, sticky="ew", pady=(5, 2))
        self.inst_combo.bind("<<ComboboxSelected>>", self.on_preset_change)
        
        # 2. Выбор основного материала (Материал А)
        ttk.Label(left_panel, text="Материал Матрицы А:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(5, 2))
        self.mat_var = tk.StringVar()
        self.mat_combo = ttk.Combobox(left_panel, textvariable=self.mat_var, state="readonly")
        all_mats = [f"{k} ({name})" for cat, items in build_category_dict(MATERIAL_PHYSICS, MATERIAL_CATEGORIES).items() for k, name in items]
        self.mat_combo['values'] = all_mats
        self.mat_combo.current(0)
        self.mat_combo.grid(row=1, column=1, sticky="ew", pady=(5, 2))
        self.mat_combo.bind("<<ComboboxSelected>>", self.update_all) # Исправлено: теперь обновляет всё
        
        # Описание материала с вкраплениями
        self.mat_desc_label = ttk.Label(left_panel, text="", wraplength=350, foreground="#555", font=("Arial", 9))
        self.mat_desc_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 8))
        
        # 2.5 Выбор второго материала для сплава (Материал Б)
        self.mat2_label = ttk.Label(left_panel, text="Материал Б (Сплав):", font=("Arial", 10, "bold"))
        self.mat2_label.grid(row=3, column=0, sticky="w", pady=(5, 2))
        self.mat2_var = tk.StringVar()
        self.mat2_combo = ttk.Combobox(left_panel, textvariable=self.mat2_var, state="disabled")
        self.mat2_combo['values'] = all_mats
        self.mat2_combo.current(1 if len(all_mats) > 1 else 0)
        self.mat2_combo.grid(row=3, column=1, sticky="ew", pady=(5, 2))
        self.mat2_combo.bind("<<ComboboxSelected>>", self.update_all) # Исправлено: теперь обновляет всё
        
        # 5. Ползунок геометрии
        self.scale_var = tk.DoubleVar(value=1.0)
        ttk.Label(left_panel, text="Геометрия / Размер:", font=("Arial", 9, "bold")).grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.scale_val_lbl = ttk.Label(left_panel, text="1.00x", font=("Arial", 9, "bold"), foreground="purple")
        self.scale_val_lbl.grid(row=4, column=1, sticky="e", pady=(8, 0))
        
        scale_slider = ttk.Scale(left_panel, from_=0.3, to=3.0, variable=self.scale_var, orient="horizontal", command=self.update_labels)
        scale_slider.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        
        # 6. Длина
        self.dur_var = tk.DoubleVar(value=1.5)
        ttk.Label(left_panel, text="Длина рендера (сек):", font=("Arial", 9, "bold")).grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.dur_val_lbl = ttk.Label(left_panel, text="1.50 сек", font=("Arial", 9, "bold"))
        self.dur_val_lbl.grid(row=6, column=1, sticky="e", pady=(6, 0))
        
        dur_slider = ttk.Scale(left_panel, from_=0.1, to=10.0, variable=self.dur_var, orient="horizontal", command=self.update_labels)
        dur_slider.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        
        # 7. Насыщение деталей (Fatness)
        self.mat_boost_var = tk.DoubleVar(value=0.5)
        ttk.Label(left_panel, text="Material Detail Boost (Общая детализация):", font=("Arial", 9, "bold")).grid(row=8, column=0, sticky="w", pady=(6, 0))
        self.fat_val_lbl = ttk.Label(left_panel, text="0.50x", font=("Arial", 9, "bold"), foreground="darkcyan")
        self.fat_val_lbl.grid(row=8, column=1, sticky="e", pady=(6, 0))
        
        mat_boost_slider = ttk.Scale(left_panel, from_=0.0, to=2.0, variable=self.mat_boost_var, orient="horizontal", command=self.update_labels)
        mat_boost_slider.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        
        # 7.5 Нелинейность материала (Nonlinearity)
        self.nonlin_var = tk.DoubleVar(value=0.0)
        ttk.Label(left_panel, text="Нелинейность материала (Nonlinearity):", font=("Arial", 9, "bold")).grid(row=10, column=0, sticky="w", pady=(6, 0))
        self.nonlin_val_lbl = ttk.Label(left_panel, text="0.00 (Linear)", font=("Arial", 9, "bold"), foreground="orangered")
        self.nonlin_val_lbl.grid(row=10, column=1, sticky="e", pady=(6, 0))
        
        nonlin_slider = ttk.Scale(left_panel, from_=0.0, to=1.0, variable=self.nonlin_var, orient="horizontal", command=self.update_labels)
        nonlin_slider.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        
        # 8. Подавление резонансов (De-Mud)
        self.demud_var = tk.DoubleVar(value=3.0)
        ttk.Label(left_panel, text="Подавление резонансов (De-Mud):", font=("Arial", 9, "bold")).grid(row=12, column=0, sticky="w", pady=(6, 0))
        self.demud_val_lbl = ttk.Label(left_panel, text="3.0 dB", font=("Arial", 9, "bold"), foreground="gold")
        self.demud_val_lbl.grid(row=12, column=1, sticky="e", pady=(6, 0))
        
        demud_slider = ttk.Scale(left_panel, from_=0.0, to=10.0, variable=self.demud_var, orient="horizontal", command=self.update_demud_label)
        demud_slider.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        
        # 9. Сила удара / Давление смычка
        ttk.Label(left_panel, text="Сила удара / Смычка:", font=("Arial", 9, "bold")).grid(row=14, column=0, sticky="w", pady=(6, 0))
        self.force_val_lbl = ttk.Label(left_panel, text="1.00x", font=("Arial", 9, "bold"), foreground="blue")
        self.force_val_lbl.grid(row=14, column=1, sticky="e", pady=(6, 0))
        
        force_slider = ttk.Scale(left_panel, from_=0.1, to=5.0, variable=self.force_var, orient="horizontal", command=self.update_labels)
        force_slider.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Фиолетовая кнопка рендера удара (внизу левой панели)
        style = ttk.Style()
        style.configure("Taichi.TButton", font=("Arial", 11, "bold"), foreground="purple")
        self.purple_btn = ttk.Button(left_panel, text="🔮 ГЕНЕРИРОВАТЬ УДАР В ФОРМЕ (FDTD)", style="Taichi.TButton", command=self.generate)
        self.purple_btn.grid(row=16, column=0, columnspan=2, sticky="ew", ipady=12, pady=(15, 5))
        
        self.resonance_frame = ttk.LabelFrame(left_panel, text="Резонансы корпуса", padding="8")
        self.resonance_frame.grid(row=17, column=0, columnspan=2, sticky="ew", pady=(6, 5))
        
        self.lowest_label = ttk.Label(self.resonance_frame, text="Нижняя струна: --")
        self.lowest_label.grid(row=0, column=0, sticky="w", pady=2)
        self.target_low_var = tk.DoubleVar(value=0.0)
        self.target_low_entry = ttk.Entry(self.resonance_frame, textvariable=self.target_low_var, width=10)
        self.target_low_entry.grid(row=0, column=1, sticky="w", padx=5)
        self.target_low_note_var = tk.StringVar()
        self.target_low_note_entry = ttk.Entry(self.resonance_frame, textvariable=self.target_low_note_var, width=6)
        self.target_low_note_entry.grid(row=0, column=2, sticky="w", padx=2)
        self.target_low_note_entry.bind("<Return>", self.on_target_note_changed)
        self.target_low_entry.bind("<Return>", self.on_target_note_changed)
        
        self.helmholtz_label = ttk.Label(self.resonance_frame, text="Гельгонц (A0): --")
        self.helmholtz_label.grid(row=1, column=0, sticky="w", pady=2)
        self.target_helm_var = tk.DoubleVar(value=0.0)
        self.target_helm_entry = ttk.Entry(self.resonance_frame, textvariable=self.target_helm_var, width=10)
        self.target_helm_entry.grid(row=1, column=1, sticky="w", padx=5)
        self.target_helm_note_var = tk.StringVar()
        self.target_helm_note_entry = ttk.Entry(self.resonance_frame, textvariable=self.target_helm_note_var, width=6)
        self.target_helm_note_entry.grid(row=1, column=2, sticky="w", padx=2)
        self.target_helm_note_entry.bind("<Return>", self.on_target_note_changed)
        self.target_helm_entry.bind("<Return>", self.on_target_note_changed)
        
        self.sympathy_label = ttk.Label(self.resonance_frame, text="Симпатические: --")
        self.sympathy_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=2)
        
        # ==========================================
        #      ПРАВАЯ ПАНЕЛЬ (ХОЛСТЫ И ОПЦИИ)
        # ==========================================
        
        # Заголовки холстов
        ttk.Label(right_panel, text="Чертежный холст:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="s", pady=(0, 5))
        ttk.Label(right_panel, text="Оптическая маска:", font=("Arial", 9, "bold")).grid(row=0, column=2, sticky="s", pady=(0, 5))
        
        # Левый интерактивный холст
        self.canvas = tk.Canvas(right_panel, width=256, height=256, bg="#111", highlightthickness=2, highlightbackground="#444", cursor="crosshair")
        self.canvas.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.canvas.bind("<B1-Motion>", self.on_canvas_click)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
        # Панель управления точками (в центре)
        self.point_frame = ttk.LabelFrame(right_panel, text="Расположение датчиков", padding=10)
        self.point_frame.grid(row=1, column=1, sticky="n", padx=10, pady=5)
        self.rebuild_point_frame_widgets()
        
        # Правый пассивный холст оптической маски
        self.mask_canvas = tk.Canvas(right_panel, width=256, height=256, bg="#111", highlightthickness=2, highlightbackground="#444")
        self.mask_canvas.grid(row=1, column=2, padx=10, pady=5, sticky="nsew")
        
        # Опции экспериментов (Многоколоночная сетка)
        self.opt_frame = ttk.LabelFrame(right_panel, text="Опции эксперимента", padding="10")
        self.opt_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=15, sticky="ew")
        
        self.opt_frame.columnconfigure(0, weight=1)
        self.opt_frame.columnconfigure(1, weight=1)
        self.opt_frame.columnconfigure(2, weight=1)
        
        # Колонка 0: True Stereo
        stereo_container = ttk.Frame(self.opt_frame)
        stereo_container.grid(row=0, column=0, sticky="nw", padx=5)
        ttk.Checkbutton(stereo_container, text="True Stereo (Двухканальный съем)", variable=self.is_stereo_var).pack(anchor="w", pady=5)
        
        # Колонка 1: Деградация
        deg_container = ttk.Frame(self.opt_frame)
        deg_container.grid(row=0, column=1, sticky="nwe", padx=5)
        ttk.Checkbutton(deg_container, text="Градиент вязкости (Деградация)", variable=self.use_degradation_var).pack(anchor="w")
        self.deg_label = ttk.Label(deg_container, text="Глубина градиента:", state="disabled")
        self.deg_label.pack(anchor="w", pady=(5, 0), padx=15)
        self.degradation_amt_var = tk.DoubleVar(value=0.5)
        self.deg_scale = ttk.Scale(deg_container, from_=0.0, to=1.0, variable=self.degradation_amt_var, orient="horizontal", state="disabled")
        self.deg_scale.pack(anchor="w", fill="x", padx=15, pady=(0, 5))
        
        # Колонка 2: Сплавы
        alloy_container = ttk.Frame(self.opt_frame)
        alloy_container.grid(row=0, column=2, sticky="nwe", padx=5)
        ttk.Checkbutton(alloy_container, text="Сплайнинг материалов (Alloy)", variable=self.use_alloy_var).pack(anchor="w")
        self.alloy_label = ttk.Label(alloy_container, text="Соотношение сплава (А / Б):", state="disabled")
        self.alloy_label.pack(anchor="w", pady=(5, 0), padx=15)
        self.alloy_ratio_var = tk.DoubleVar(value=0.5)
        self.alloy_scale = ttk.Scale(alloy_container, from_=0.0, to=1.0, variable=self.alloy_ratio_var, orient="horizontal", state="disabled")
        self.alloy_scale.pack(anchor="w", fill="x", padx=15, pady=(0, 5))
        
        self.alloy_ratio_var.trace_add("write", self.update_all)
        
        # Зеленая кнопка генерации текстуры смычка (внизу правой панели)
        style.configure("Texture.TButton", font=("Arial", 11, "bold"), foreground="darkcyan")
        self.green_btn = ttk.Button(right_panel, text="🎻 СИНТЕЗИРОВАТЬ ТЕКСТУРУ ТРЕНИЯ (FDTD смычок)", style="Texture.TButton", command=self.generate_texture)
        self.green_btn.grid(row=3, column=0, columnspan=3, sticky="ew", ipady=12, pady=(10, 5), padx=10)
        
        # Первоначальный апдейт
        self.update_all()
        self.update_widget_states()
        
    def rebuild_point_frame_widgets(self):
        """Динамическое перестроение кнопок выбора датчиков на основе режима (Моно/Стерео)"""
        for widget in self.point_frame.winfo_children():
            widget.destroy()
            
        ttk.Radiobutton(self.point_frame, text="Точка смычка (Красная)", variable=self.edit_mode, value="strike").pack(anchor="w", pady=2)
        
        if self.is_stereo_var.get():
            if self.edit_mode.get() == "pickup_L":
                self.edit_mode.set("pickup_L")
            
            ttk.Radiobutton(self.point_frame, text="Левый датчик (Желтая)", variable=self.edit_mode, value="pickup_L").pack(anchor="w", pady=2)
            ttk.Radiobutton(self.point_frame, text="Правый датчик (Оранжевая)", variable=self.edit_mode, value="pickup_R").pack(anchor="w", pady=2)
        else:
            if self.edit_mode.get() == "pickup_R":
                self.edit_mode.set("strike")
                
            ttk.Radiobutton(self.point_frame, text="Пьезодатчик (Желтая)", variable=self.edit_mode, value="pickup_L").pack(anchor="w", pady=2)
            
        ttk.Button(self.point_frame, text="Сбросить в центр", command=self.reset_points).pack(fill="x", pady=(10, 0))

    def update_widget_states(self):
        """Интерактивное включение/выключение слайдеров и комбобоксов в зависимости от галочек"""
        if self.use_alloy_var.get():
            self.mat2_label.configure(state="normal")
            self.mat2_combo.configure(state="readonly")
            self.alloy_label.configure(state="normal")
            self.alloy_scale.configure(state="normal")
        else:
            self.mat2_label.configure(state="disabled")
            self.mat2_combo.configure(state="disabled")
            self.alloy_label.configure(state="disabled")
            self.alloy_scale.configure(state="disabled")
            
        if self.use_degradation_var.get():
            self.deg_label.configure(state="normal")
            self.deg_scale.configure(state="normal")
        else:
            self.deg_label.configure(state="disabled")
            self.deg_scale.configure(state="disabled")
            
        self.update_all() # Исправлено: теперь обновляет и маску

    def on_preset_change(self, event):
        self.reset_points()
        self.update_resonance_display()
        
    def reset_points(self):
        self.custom_strike = None
        self.custom_pickup_L = None
        self.custom_pickup_R = None
        self.update_all()

    def on_canvas_click(self, event):
        tx = int(np.clip(event.x / 2.0, 0, 127))
        ty = int(np.clip((256 - event.y) / 2.0, 0, 127))
        
        if self.edit_mode.get() == "strike":
            self.custom_strike = (tx, ty)
        elif self.edit_mode.get() == "pickup_L":
            self.custom_pickup_L = (tx, ty)
        elif self.edit_mode.get() == "pickup_R":
            self.custom_pickup_R = (tx, ty)
            
        self.update_preview()

    def update_all(self, *args):
        self.update_preview()
        self.update_labels()

    def update_preview(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        inst = ALL_PRESETS[inst_key]
        
        mask_np = generate_instrument_mask(inst, 128)
        img_data = np.zeros((128, 128, 3), dtype=np.uint8)
        img_data[mask_np > 0.5] = [0, 255, 150] 
        
        strike = self.custom_strike or get_strike_point(inst, 128)
        
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                sx, sy = np.clip(strike[0]+dx, 0, 127), np.clip(strike[1]+dy, 0, 127)
                img_data[sx, sy] = [255, 50, 50]

        if self.is_stereo_var.get():
            default_L, default_R = get_pickup_points_stereo(inst, 128)
            pickup_L = self.custom_pickup_L or default_L
            pickup_R = self.custom_pickup_R or default_R
            
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    lx, ly = np.clip(pickup_L[0]+dx, 0, 127), np.clip(pickup_L[1]+dy, 0, 127)
                    img_data[lx, ly] = [255, 255, 50]
                    rx, ry = np.clip(pickup_R[0]+dx, 0, 127), np.clip(pickup_R[1]+dy, 0, 127)
                    img_data[rx, ry] = [255, 128, 0]
        else:
            pickup = self.custom_pickup_L or get_pickup_point(inst, 128)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    px, py = np.clip(pickup[0]+dx, 0, 127), np.clip(pickup[1]+dy, 0, 127)
                    img_data[px, py] = [255, 255, 50]

        img_transposed = np.transpose(img_data, (1, 0, 2))
        img_flipped = np.flip(img_transposed, axis=0)
        
        img = Image.fromarray(img_flipped).resize((256, 256), Image.NEAREST)
        self.photo = ImageTk.PhotoImage(image=img)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        
        self.update_optical_mask()
    
    def update_optical_mask(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        mat_key = self.mat_var.get().split(" ")[0].strip()
        
        inst = ALL_PRESETS[inst_key]
        mat = MATERIAL_PHYSICS[mat_key]
        
        if self.use_alloy_var.get() and self.mat2_var.get():
            mat2_key = self.mat2_var.get().split(" ")[0].strip()
            mat2 = MATERIAL_PHYSICS.get(mat2_key, mat)
            mat = blend_materials(mat, mat2, self.alloy_ratio_var.get())
            
        mask_np = generate_instrument_mask(inst, 128)
        _, rgb_map = build_heterogeneous_grids(mask_np, mat)
        
        strike = self.custom_strike or get_strike_point(inst, 128)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                sx, sy = np.clip(strike[0]+dx, 0, 127), np.clip(strike[1]+dy, 0, 127)
                rgb_map[sx, sy] = [255, 50, 50]
        
        if self.is_stereo_var.get():
            default_L, default_R = get_pickup_points_stereo(inst, 128)
            pickup_L = self.custom_pickup_L or default_L
            pickup_R = self.custom_pickup_R or default_R
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    lx, ly = np.clip(pickup_L[0]+dx, 0, 127), np.clip(pickup_L[1]+dy, 0, 127)
                    rgb_map[lx, ly] = [255, 255, 50]
                    rx, ry = np.clip(pickup_R[0]+dx, 0, 127), np.clip(pickup_R[1]+dy, 0, 127)
                    rgb_map[rx, ry] = [255, 128, 0]
        else:
            pickup = self.custom_pickup_L or get_pickup_point(inst, 128)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    px, py = np.clip(pickup[0]+dx, 0, 127), np.clip(pickup[1]+dy, 0, 127)
                    rgb_map[px, py] = [255, 255, 50]
        
        rgb_transposed = np.transpose(rgb_map, (1, 0, 2))
        rgb_flipped = np.flip(rgb_transposed, axis=0)
        
        mask_img = Image.fromarray(rgb_flipped).resize((256, 256), Image.NEAREST)
        self.mask_photo = ImageTk.PhotoImage(image=mask_img)
        self.mask_canvas.create_image(0, 0, image=self.mask_photo, anchor="nw")
    
    def update_labels(self, *args):
        mat_key = self.mat_var.get().split(" ")[0].strip()
        mat = MATERIAL_PHYSICS[mat_key]
        
        if self.use_alloy_var.get() and self.mat2_var.get():
            mat2_key = self.mat2_var.get().split(" ")[0].strip()
            mat2 = MATERIAL_PHYSICS.get(mat2_key, mat)
            mat = blend_materials(mat, mat2, self.alloy_ratio_var.get())
            
        base_thickness = mat.get("base_thickness", 0.003)
        
        # Очистка HTML тегов для красивого отображения описания в интерфейсе
        desc_html = get_heterogeneous_material_description(mat)
        desc_text = re.sub(r'<br\s*/?>', '\n', desc_html)
        desc_text = re.sub(r'<li>', '  • ', desc_text)
        desc_text = re.sub(r'<[^>]+>', '', desc_text)
        self.mat_desc_label.config(text=desc_text)
        
        inst_key = self.inst_var.get().split(" ")[0].strip()
        inst = ALL_PRESETS[inst_key]
        base_size_m = inst.get("size_m", 0.4)
        self._last_inst = inst
        
        scale = self.scale_var.get()
        self._last_scale = scale
        width_m = base_size_m * scale
        thickness_mm = base_thickness * scale * 1000.0
        
        self.scale_val_lbl.config(
            text=f"{scale:.2f}x (Габарит: {width_m*100:.1f} см, Толщина деки: {thickness_mm:.2f} мм)"
        )
        self.dur_val_lbl.config(text=f"{self.dur_var.get():.2f} сек")
        
        mat_boost = self.mat_boost_var.get()
        if mat_boost == 0.0:
            self.fat_val_lbl.config(text="0.00 (Off)")
        else:
            self.fat_val_lbl.config(text=f"+{mat_boost:.2f}x (+{mat_boost * 6.0:.1f} dB)")

        nonlin = self.nonlin_var.get()
        if nonlin == 0.0:
            self.nonlin_val_lbl.config(text="0.00 (Linear)")
        else:
            self.nonlin_val_lbl.config(text=f"{nonlin:.2f} (Fracture Reactivity)")
            
        force = self.force_var.get()
        self.force_val_lbl.config(text=f"{force:.2f}x")
        
        self.update_resonance_display()
        
    def update_demud_label(self, value):
        db_val = float(value)
        if db_val == 0.0:
            self.demud_val_lbl.config(text="Откл (0.0 dB)")
        else:
            self.demud_val_lbl.config(text=f"{db_val:.1f} dB")
            
    def hz_to_note_name(self, hz):
        if hz <= 0:
            return ""
        midi = round(69 + 12 * np.log2(hz / 440.0))
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        note = note_names[midi % 12]
        octave = midi // 12 - 1
        return f"{note}{octave}"
            
    def update_resonance_display(self):
        if hasattr(self, '_last_inst') and hasattr(self, '_last_scale'):
            inst = self._last_inst
            scale = self._last_scale
        else:
            inst_key = self.inst_var.get().split(" ")[0].strip()
            inst = ALL_PRESETS[inst_key]
            scale = self.scale_var.get()
            self._last_inst = inst
            self._last_scale = scale
        info = get_resonance_info(inst, scale)
        lowest_hz = info.get("lowest_string_hz")
        helmholtz_hz = info.get("helmholtz_hz")
        sympathy_hz = info.get("sympathetic_hz", [])
        
        if lowest_hz is not None:
            self.lowest_label.config(text=f"Нижняя струна: {lowest_hz:.1f} Гц")
            self.target_low_var.set(round(lowest_hz, 1))
            self.target_low_note_var.set(self.hz_to_note_name(lowest_hz))
        else:
            self.lowest_label.config(text="Нижняя струна: н/д")
            
        if helmholtz_hz is not None:
            self.helmholtz_label.config(text=f"Гельгонц (A0): {helmholtz_hz:.1f} Гц")
            self.target_helm_var.set(round(helmholtz_hz, 1))
            self.target_helm_note_var.set(self.hz_to_note_name(helmholtz_hz))
        else:
            self.helmholtz_label.config(text="Гельгонц (A0): н/д")
            
        if sympathy_hz:
            text = "Симпатические: " + ", ".join(f"{f:.1f}" for f in sympathy_hz) + " Гц"
        else:
            text = "Симпатические: н/д"
        self.sympathy_label.config(text=text)
        
        if not getattr(self, '_resonance_display_pending', False):
            self._resonance_display_pending = True
            self.after(50, self._update_resonance_display_delayed)
            
    def _update_resonance_display_delayed(self):
        self._resonance_display_pending = False
        inst_key = self.inst_var.get().split(" ")[0].strip()
        inst = ALL_PRESETS[inst_key]
        scale = self.scale_var.get()
        self._last_inst = inst
        self._last_scale = scale
        try:
            info = get_resonance_info(inst, scale)
            lowest_hz = info.get("lowest_string_hz")
            helmholtz_hz = info.get("helmholtz_hz")
            sympathy_hz = info.get("sympathetic_hz", [])
            
            if lowest_hz is not None:
                self.lowest_label.config(text=f"Нижняя струна: {lowest_hz:.1f} Гц")
                self.target_low_var.set(round(lowest_hz, 1))
                self.target_low_note_var.set(self.hz_to_note_name(lowest_hz))
            else:
                self.lowest_label.config(text="Нижняя струна: н/д")
            if helmholtz_hz is not None:
                self.helmholtz_label.config(text=f"Гельгонц (A0): {helmholtz_hz:.1f} Гц")
                self.target_helm_var.set(round(helmholtz_hz, 1))
                self.target_helm_note_var.set(self.hz_to_note_name(helmholtz_hz))
            else:
                self.helmholtz_label.config(text="Гельгонц (A0): н/д")
            if sympathy_hz:
                text = "Симпатические: " + ", ".join(f"{f:.1f}" for f in sympathy_hz) + " Гц"
            else:
                text = "Симпатические: н/д"
            self.sympathy_label.config(text=text)
        except Exception:
            pass
            
    def on_target_note_changed(self, event=None):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        inst = ALL_PRESETS[inst_key]
        base_A0 = inst.get("A0", None)
        base_f0 = inst.get("f0", None)
        target_hz = None
        entry = event.widget if event else None
        if entry in (self.target_helm_entry, self.target_helm_note_entry) and base_A0 is not None:
            try:
                if entry is self.target_helm_note_entry:
                    text = self.target_helm_note_var.get().strip()
                    if text:
                        target_hz = note_name_to_hz(text)
                        self.target_helm_var.set(round(target_hz, 1))
                    else:
                        return
                else:
                    target_hz = float(self.target_helm_var.get().strip())
                    if target_hz <= 0:
                        return
            except Exception:
                return
            new_scale = base_A0 / target_hz
        elif entry in (self.target_low_entry, self.target_low_note_entry) and base_f0 is not None:
            try:
                if entry is self.target_low_note_entry:
                    text = self.target_low_note_var.get().strip()
                    if text:
                        target_hz = note_name_to_hz(text)
                        self.target_low_var.set(round(target_hz, 1))
                    else:
                        return
                else:
                    target_hz = float(self.target_low_var.get().strip())
                    if target_hz <= 0:
                        return
            except Exception:
                return
            new_scale = base_f0 / target_hz
        else:
            return
        if new_scale > 0:
            self.scale_var.set(new_scale)
            self._last_scale = new_scale
            self.update_labels()
            self.update_resonance_display()
        
    def generate(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        mat_key = self.mat_var.get().split(" ")[0].strip()
        scale = self.scale_var.get()
        duration = self.dur_var.get()
        mat_boost = self.mat_boost_var.get()
        nonlinearity = self.nonlin_var.get()
        demud_db = self.demud_var.get()

        is_stereo = self.is_stereo_var.get()
        use_degradation = self.use_degradation_var.get()
        use_alloy = self.use_alloy_var.get()
        degradation_amt = self.degradation_amt_var.get()
        
        file_path = filedialog.asksaveasfilename(defaultextension=".wav", initialfile=f"FDTD_STRIKE_{inst_key}_{mat_key}.wav")
        if not file_path: return
        
        self.status_var.set("Запуск Taichi ядра. Открываю окно тепловизора...")
        self.update_idletasks() 
        
        inst = ALL_PRESETS[inst_key]
        mat = MATERIAL_PHYSICS[mat_key]
        
        if use_alloy:
            mat2_key = self.mat2_var.get().split(" ")[0].strip()
            mat2 = MATERIAL_PHYSICS[mat2_key]
            mat = blend_materials(mat, mat2, self.alloy_ratio_var.get())
        
        hetero_grids = None
        if "inclusions" in mat and mat["inclusions"]:
            mask_np = generate_instrument_mask(inst, 128)
            hetero_grids, _ = build_heterogeneous_grids(mask_np, mat)
        
        try:
            ir_data = generate_fdtd_ir(
                inst_dict=inst, 
                mat_dict=mat, 
                user_scale=scale, 
                duration=duration, 
                sample_rate=44100,
                custom_strike=self.custom_strike,
                custom_pickup_L=self.custom_pickup_L,
                custom_pickup_R=self.custom_pickup_R,
                is_friction=False,
                fatness=mat_boost,
                is_stereo=is_stereo,
                use_degradation=use_degradation,
                degradation_amt=degradation_amt,
                nonlinearity=nonlinearity,
                heterogeneous_grids=hetero_grids,
                demud_db=demud_db
            )
            wavfile.write(file_path, 44100, ir_data.astype(np.float32))
            self.status_var.set(f"Успех: {os.path.basename(file_path)}")
            messagebox.showinfo("FDTD Рендер Завершен", "Матрица остыла. Импульс готов!")
        except Exception as e:
            self.status_var.set("Ошибка FDTD ядра")
            messagebox.showerror("Сбой", str(e))

    def generate_texture(self):
        inst_key = self.inst_var.get().split(" ")[0].strip()
        mat_key = self.mat_var.get().split(" ")[0].strip()
        scale = self.scale_var.get()
        duration = self.dur_var.get()
        mat_boost = self.mat_boost_var.get()
        nonlinearity = self.nonlin_var.get()
        demud_db = self.demud_var.get()
        
        is_stereo = self.is_stereo_var.get()
        use_degradation = self.use_degradation_var.get()
        use_alloy = self.use_alloy_var.get()
        degradation_amt = self.degradation_amt_var.get()
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".wav", 
            initialfile=f"FDTD_BOW_{inst_key}_{mat_key}.wav"
        )
        if not file_path: return
        
        self.status_var.set("Запуск FDTD Смычка. Открываю окно тепловизора...")
        self.update_idletasks() 
        
        inst = ALL_PRESETS[inst_key]
        mat = MATERIAL_PHYSICS[mat_key]
        
        if use_alloy:
            mat2_key = self.mat2_var.get().split(" ")[0].strip()
            mat2 = MATERIAL_PHYSICS[mat2_key]
            mat = blend_materials(mat, mat2, self.alloy_ratio_var.get())
        
        hetero_grids = None
        
        if "inclusions" in mat and mat["inclusions"]:
            mask_np = generate_instrument_mask(inst, 128)
            hetero_grids, _ = build_heterogeneous_grids(mask_np, mat)
        
        try:
            ir_data = generate_fdtd_ir(
                inst_dict=inst, 
                mat_dict=mat, 
                user_scale=scale, 
                duration=duration, 
                sample_rate=44100,
                custom_strike=self.custom_strike,
                custom_pickup_L=self.custom_pickup_L,
                custom_pickup_R=self.custom_pickup_R,
                is_friction=True,
                fatness=mat_boost,
                is_stereo=is_stereo,
                use_degradation=use_degradation,
                degradation_amt=degradation_amt,
                nonlinearity=nonlinearity,
                heterogeneous_grids=hetero_grids,
                demud_db=demud_db
            )
            wavfile.write(file_path, 44100, ir_data.astype(np.float32))
            self.status_var.set(f"Успех: {os.path.basename(file_path)}")
            messagebox.showinfo("FDTD Смычок Завершен", "Физическая текстура трения готова!")
        except Exception as e:
            self.status_var.set("Ошибка FDTD ядра")
            messagebox.showerror("Сбой", str(e))
# --- END OF FILE ui/tab_taichi.py ---