# dlc/dhol/dhol_gui.py
import os
import tkinter as tk
from tkinter import ttk, messagebox
import scipy.io.wavfile as wav
import numpy as np
import logging

from dhol_engine import synthesize_dhol_strike, note_to_frequency
from config.materials import MATERIAL_PHYSICS
from dlc.dhol.dhol_packer_gui import DholPackerFrame

logger = logging.getLogger("TheHall.GUI")

class DholDLCFrame(ttk.Notebook):
    def __init__(self, parent, main_app_ref):
        super().__init__(parent)
        self.main_app = main_app_ref
        self.is_rendering = False

        tab_engine = ttk.Frame(self, padding="0")
        self.packer_tab = DholPackerFrame(self, main_app_ref)

        self.add(tab_engine, text="Dhol Engine")
        self.add(self.packer_tab, text="Packer / Multisamples")

        self.setup_ui(tab_engine)

    def setup_ui(self, container):
        # Заголовок
        header = ttk.Label(container, text="THE DHOL — Кавказский Дхол (Coupled FDTD Engine)", font=("Helvetica", 12, "bold"), foreground="#00ff96")
        header.pack(anchor=tk.W, pady=(0, 6))

        # Сетка для разделения на две основные колонки
        main_grid = ttk.Frame(container)
        main_grid.pack(fill=tk.BOTH, expand=True)
        main_grid.columnconfigure(0, weight=1, uniform="group1")
        main_grid.columnconfigure(1, weight=1, uniform="group1")
        main_grid.rowconfigure(0, weight=1)

        # === ЛЕВАЯ КОЛОНКА (Настройки физики и параметров звука) ===
        left_col = ttk.Frame(main_grid)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        # Инициализируем Notebook (Вкладки) для левой колонки
        left_notebook = ttk.Notebook(left_col)
        left_notebook.pack(fill=tk.BOTH, expand=True)

        tab_core = ttk.Frame(left_notebook, padding="6")
        tab_physics = ttk.Frame(left_notebook, padding="6")
        tab_accessories = ttk.Frame(left_notebook, padding="6")

        left_notebook.add(tab_core, text="🎹 База и Акустика")
        left_notebook.add(tab_physics, text="🪵 Физика и Синтез")
        left_notebook.add(tab_accessories, text="🔔 Аксессуары")

        # --- ВКЛАДКА 1: БАЗА И АКУСТИКА (tab_core) ---
        
        # Секция настройки строя (Tuning)
        tuning_group = ttk.LabelFrame(tab_core, text=" Настройки строя мембран (Tuning) ", padding="6")
        tuning_group.pack(fill=tk.X, pady=2)

        ttk.Label(tuning_group, text="Басовая мембрана (Дум):").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.note_A_var = tk.StringVar(value="D2")
        self.combo_A = ttk.Combobox(tuning_group, textvariable=self.note_A_var, values=["C2", "C#2", "D2", "D#2", "E2", "F2", "F#2", "G2", "G#2", "A2", "A#2", "B2", "C3", "C#3", "D3", "D#3", "E3", "F3", "F#3", "G3", "G#3", "A3", "A#3", "B3", "C4"], width=6, state="readonly")
        self.combo_A.grid(row=0, column=1, padx=4, pady=2)
        self.combo_A.bind("<<ComboboxSelected>>", self.update_frequency_labels)
        self.freq_A_lbl = ttk.Label(tuning_group, text="Частота: 73.42 Гц", foreground="#888")
        self.freq_A_lbl.grid(row=0, column=2, padx=8, pady=2, sticky=tk.W)

        ttk.Label(tuning_group, text="Звонкая мембрана (Тэк):").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        self.note_B_var = tk.StringVar(value="A2")
        self.combo_B = ttk.Combobox(tuning_group, textvariable=self.note_B_var, values=["E2", "F2", "F#2", "G2", "G#2", "A2", "A#2", "B2", "C3", "C#3", "D3", "D#3", "E3", "F3", "F#3", "G3", "G#3", "A3", "A#3", "B3", "C4"], width=6, state="readonly")
        self.combo_B.grid(row=1, column=1, padx=4, pady=2)
        self.combo_B.bind("<<ComboboxSelected>>", self.update_frequency_labels)
        self.freq_B_lbl = ttk.Label(tuning_group, text="Частота: 110.00 Гц", foreground="#888")
        self.freq_B_lbl.grid(row=1, column=2, padx=8, pady=2, sticky=tk.W)

        # Секция материалов
        material_group = ttk.LabelFrame(tab_core, text=" Физика материалов (Troakar Integration) ", padding="6")
        material_group.pack(fill=tk.X, pady=2)

        self.mat_list = sorted(list(MATERIAL_PHYSICS.keys()))

        ttk.Label(material_group, text="Материал мембран (Кожа):").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.skin_mat_var = tk.StringVar(value="animal_skin")
        self.skin_selector = ttk.Combobox(material_group, textvariable=self.skin_mat_var, values=self.mat_list, state="readonly", width=18)
        self.skin_selector.grid(row=0, column=1, padx=4, pady=2, sticky=tk.W)
        self.skin_selector.bind("<<ComboboxSelected>>", self.update_material_descriptions)

        ttk.Label(material_group, text="Материал кадушки (Корпус):").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        self.shell_mat_var = tk.StringVar(value="walnut")
        self.shell_selector = ttk.Combobox(material_group, textvariable=self.shell_mat_var, values=self.mat_list, state="readonly", width=18)
        self.shell_selector.grid(row=1, column=1, padx=4, pady=2, sticky=tk.W)
        self.shell_selector.bind("<<ComboboxSelected>>", self.update_material_descriptions)

        self.mat_desc_lbl = ttk.Label(material_group, text="Кожа: Натуральная кожа. Кадушка: Кавказский орех.", font=("Helvetica", 8, "italic"), foreground="#aaa", wraplength=280)
        self.mat_desc_lbl.grid(row=2, column=0, columnspan=2, padx=4, pady=3, sticky=tk.W)

        # Экспресс-анализатор
        self.analysis_group = ttk.LabelFrame(tab_core, text=" Экспресс-анализатор акустики (Pre-render CAD) ", padding="6")
        self.analysis_group.pack(fill=tk.BOTH, expand=True, pady=2)

        self.preview_lbl = ttk.Label(
            self.analysis_group,
            text="Инициализация анализатора...",
            font=("Consolas", 8),
            foreground="#00ff96",
            background="#121212",
            padding="4",
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.preview_lbl.pack(fill=tk.BOTH, expand=True)


        # --- ВКЛАДКА 2: ФИЗИКА И СИНТЕЗ (tab_physics) ---
        
        # Группа характера, насыщения и тактильности
        character_group = ttk.LabelFrame(tab_physics, text=" Физическое насыщение и тактильность мембраны ", padding="6")
        character_group.pack(fill=tk.X, pady=2)

        # Компактный грид для слайдеров
        char_grid = ttk.Frame(character_group)
        char_grid.pack(fill=tk.X, expand=True)
        char_grid.columnconfigure(1, weight=1)

        # 1. Сатурация
        self.saturation_var = tk.DoubleVar(value=0.15)
        ttk.Label(char_grid, text="Tube Saturation:", font=("Helvetica", 8, "bold")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.saturation_scale = ttk.Scale(char_grid, from_=0.0, to=2.0, variable=self.saturation_var, orient="horizontal", command=lambda v: self.update_slider_label("saturation"))
        self.saturation_scale.grid(row=0, column=1, sticky=tk.EW, padx=4, pady=2)
        self.saturation_val_lbl = ttk.Label(char_grid, text="0.15x", width=6, anchor=tk.E)
        self.saturation_val_lbl.grid(row=0, column=2, sticky=tk.E, padx=4, pady=2)

        # 2. Насыщение деталями
        self.mat_boost_var = tk.DoubleVar(value=0.5)
        ttk.Label(char_grid, text="Detail Boost:", font=("Helvetica", 8, "bold")).grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        self.mat_boost_scale = ttk.Scale(char_grid, from_=0.0, to=2.0, variable=self.mat_boost_var, orient="horizontal", command=lambda v: self.update_slider_label("mat_boost"))
        self.mat_boost_scale.grid(row=1, column=1, sticky=tk.EW, padx=4, pady=2)
        self.mat_boost_val_lbl = ttk.Label(char_grid, text="0.50x", width=6, anchor=tk.E)
        self.mat_boost_val_lbl.grid(row=1, column=2, sticky=tk.E, padx=4, pady=2)

        # 3. Тактильность Мембраны
        self.membrane_tactile_var = tk.DoubleVar(value=1.0)
        ttk.Label(char_grid, text="Membrane Tactility:", font=("Helvetica", 8, "bold")).grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        self.membrane_tactile_scale = ttk.Scale(char_grid, from_=0.0, to=2.0, variable=self.membrane_tactile_var, orient="horizontal", command=lambda v: self.update_slider_label("tactility"))
        self.membrane_tactile_scale.grid(row=2, column=1, sticky=tk.EW, padx=4, pady=2)
        self.membrane_tactile_val_lbl = ttk.Label(char_grid, text="1.00x", width=6, anchor=tk.E)
        self.membrane_tactile_val_lbl.grid(row=2, column=2, sticky=tk.E, padx=4, pady=2)

        # 4. Яркость/Щелчок Мембраны
        self.membrane_snap_var = tk.DoubleVar(value=1.0)
        ttk.Label(char_grid, text="Membrane Click:", font=("Helvetica", 8, "bold")).grid(row=3, column=0, sticky=tk.W, padx=4, pady=2)
        self.membrane_snap_scale = ttk.Scale(char_grid, from_=0.0, to=2.0, variable=self.membrane_snap_var, orient="horizontal", command=lambda v: self.update_slider_label("snap"))
        self.membrane_snap_scale.grid(row=3, column=1, sticky=tk.EW, padx=4, pady=2)
        self.membrane_snap_val_lbl = ttk.Label(char_grid, text="1.00x", width=6, anchor=tk.E)
        self.membrane_snap_val_lbl.grid(row=3, column=2, sticky=tk.E, padx=4, pady=2)

        # Секция Shell Engine (Резонанс кадушки)
        shell_group = ttk.LabelFrame(tab_physics, text=" Shell Engine (Резонанс кадушки) ", padding="6")
        shell_group.pack(fill=tk.X, pady=2)

        shell_grid = ttk.Frame(shell_group)
        shell_grid.pack(fill=tk.X, expand=True)
        shell_grid.columnconfigure(1, weight=1)

        # Shell Attack
        self.shell_attack_var = tk.DoubleVar(value=0.0)
        ttk.Label(shell_grid, text="Shell Attack:", font=("Helvetica", 8, "bold")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.shell_attack_scale = ttk.Scale(shell_grid, from_=0.0, to=2.0, variable=self.shell_attack_var, orient="horizontal", command=lambda v: self.update_slider_label("shell_attack"))
        self.shell_attack_scale.grid(row=0, column=1, sticky=tk.EW, padx=4, pady=2)
        self.shell_attack_val_lbl = ttk.Label(shell_grid, text="0.00x", width=6, anchor=tk.E)
        self.shell_attack_val_lbl.grid(row=0, column=2, sticky=tk.E, padx=4, pady=2)

        # Shell Sustain
        self.shell_sustain_var = tk.DoubleVar(value=1.2)
        ttk.Label(shell_grid, text="Shell Sustain:", font=("Helvetica", 8, "bold")).grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        self.shell_sustain_scale = ttk.Scale(shell_grid, from_=0.0, to=2.0, variable=self.shell_sustain_var, orient="horizontal", command=lambda v: self.update_slider_label("shell_sustain"))
        self.shell_sustain_scale.grid(row=1, column=1, sticky=tk.EW, padx=4, pady=2)
        self.shell_sustain_val_lbl = ttk.Label(shell_grid, text="1.20x", width=6, anchor=tk.E)
        self.shell_sustain_val_lbl.grid(row=1, column=2, sticky=tk.E, padx=4, pady=2)

        # Luthier Ring
        self.ring_mod_var = tk.DoubleVar(value=0.0)
        ttk.Label(shell_grid, text="Luthier Ring:", font=("Helvetica", 8, "bold")).grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        self.ring_mod_scale = ttk.Scale(shell_grid, from_=0.0, to=1.0, variable=self.ring_mod_var, orient="horizontal", command=lambda v: self.update_slider_label("ring_mod"))
        self.ring_mod_scale.grid(row=2, column=1, sticky=tk.EW, padx=4, pady=2)
        self.ring_mod_val_lbl = ttk.Label(shell_grid, text="0.00x", width=6, anchor=tk.E)
        self.ring_mod_val_lbl.grid(row=2, column=2, sticky=tk.E, padx=4, pady=2)

        # Чекбокс автотюна
        self.autotune_shell_var = tk.BooleanVar(value=False)
        self.autotune_shell_cb = ttk.Checkbutton(
            shell_group, 
            text="Подстроить резонанс корпуса для чистоты интервала (Luthier Autotune)", 
            variable=self.autotune_shell_var,
            command=self.update_acoustic_preview
        )
        self.autotune_shell_cb.pack(fill=tk.X, anchor=tk.W, pady=(4, 0))


        # --- ВКЛАДКА 3: АКСЕССУАРЫ (tab_accessories) ---
        
        acc_group = ttk.LabelFrame(tab_accessories, text=" Внутренние колокольчики (Shkhshkhan) ", padding="8")
        acc_group.pack(fill=tk.X, pady=4)

        self.use_bells_var = tk.BooleanVar(value=False)
        self.use_bells_cb = ttk.Checkbutton(
            acc_group, 
            text="Активировать внутренние колокольчики", 
            variable=self.use_bells_var,
            command=self.toggle_bells_ui
        )
        self.use_bells_cb.pack(fill=tk.X, anchor=tk.W, pady=(0, 4))

        self.bells_params_frame = ttk.Frame(acc_group)
        self.bells_params_frame.pack(fill=tk.X, pady=(4, 0))
        self.bells_params_frame.columnconfigure(1, weight=1)

        # Выбор сплава
        ttk.Label(self.bells_params_frame, text="Сплав металла:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=3)
        metal_materials = [k for k, v in MATERIAL_PHYSICS.items() if v.get("category") == "metal"]
        if not metal_materials:
            metal_materials = self.mat_list
            
        self.bell_mat_var = tk.StringVar(value="steel")
        self.bell_selector = ttk.Combobox(self.bells_params_frame, textvariable=self.bell_mat_var, values=metal_materials, state="readonly", width=15)
        self.bell_selector.grid(row=0, column=1, sticky=tk.W, padx=4, pady=3)

        # Mix колокольчиков
        ttk.Label(self.bells_params_frame, text="Громкость (Mix):").grid(row=1, column=0, sticky=tk.W, padx=4, pady=3)
        self.bell_mix_var = tk.DoubleVar(value=0.15)
        self.bell_mix_scale = ttk.Scale(self.bells_params_frame, from_=0.0, to=1.0, variable=self.bell_mix_var, orient="horizontal", command=lambda v: self.update_slider_label("bell_mix"))
        self.bell_mix_scale.grid(row=1, column=1, sticky=tk.EW, padx=4, pady=3)
        
        self.bell_mix_val_lbl = ttk.Label(self.bells_params_frame, text="0.15x", width=6, anchor=tk.E)
        self.bell_mix_val_lbl.grid(row=1, column=2, sticky=tk.E, padx=4, pady=3)
        
        self.toggle_bells_ui()


        # === ПРАВАЯ КОЛОНКА (Настройки экспорта и Консоль логов) ===
        right_col = ttk.Frame(main_grid)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # Создаем Notebook для правой колонки (Разгружаем интерфейс)
        right_notebook = ttk.Notebook(right_col)
        right_notebook.pack(fill=tk.BOTH, expand=True)

        tab_export = ttk.Frame(right_notebook, padding="6")
        tab_console = ttk.Frame(right_notebook, padding="6")

        right_notebook.add(tab_export, text="📦 Настройки Экспорта")
        right_notebook.add(tab_console, text="💻 Консоль логов")

        # --- ВКЛАДКА ЭКСПОРТА (tab_export) ---
        export_group = ttk.Frame(tab_export)
        export_group.pack(fill=tk.BOTH, expand=True)

        self.batch_render_var = tk.BooleanVar(value=True)
        self.dyn_layers_var = tk.IntVar(value=8)

        # Рендеринг слоев
        ttk.Checkbutton(export_group, text="Рендерить слои динамики (Velocity 16–127)", variable=self.batch_render_var).pack(anchor=tk.W, padx=4, pady=2)

        # Компактное отображение количества слоев
        layers_frame = ttk.Frame(export_group)
        layers_frame.pack(fill=tk.X, pady=2)
        
        self.dyn_layers_lbl = ttk.Label(layers_frame, text="Слоев динамики (1–12): 8")
        self.dyn_layers_lbl.pack(side=tk.LEFT, padx=4)
        
        self.dyn_layers_scale = ttk.Scale(layers_frame, from_=1.0, to=12.0, variable=self.dyn_layers_var, orient="horizontal", command=self.update_dyn_layers_lbl)
        self.dyn_layers_scale.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=4)

        # Round Robin
        settings_subframe = ttk.Frame(export_group)
        settings_subframe.pack(fill=tk.X, anchor=tk.W, pady=3)
        
        ttk.Label(settings_subframe, text="Количество слоев Round Robin (RR):").pack(side=tk.LEFT, padx=4)
        self.rr_var = tk.IntVar(value=3)
        self.combo_rr = ttk.Combobox(settings_subframe, textvariable=self.rr_var, values=[1, 2, 3, 4, 5], width=4, state="readonly")
        self.combo_rr.pack(side=tk.LEFT, padx=4)

        # Трехколоночная компактная сетка артикуляций
        art_select_group = ttk.LabelFrame(export_group, text=" Артикуляции для экспорта ", padding="6")
        art_select_group.pack(fill=tk.BOTH, expand=True, pady=4)

        self.art_open_bass_var = tk.BooleanVar(value=True)
        self.art_duum_var = tk.BooleanVar(value=True)
        self.art_tek_B_var = tk.BooleanVar(value=True)
        self.art_tek_A_var = tk.BooleanVar(value=True)
        self.art_clap_tek_var = tk.BooleanVar(value=True)
        self.art_mute_var = tk.BooleanVar(value=True)
        self.art_chapa_var = tk.BooleanVar(value=False)
        self.art_kopal_var = tk.BooleanVar(value=False)
        self.art_tchipot_var = tk.BooleanVar(value=False)
        self.art_slide_var = tk.BooleanVar(value=False)
        self.art_click_var = tk.BooleanVar(value=False)

        art_grid = ttk.Frame(art_select_group)
        art_grid.pack(fill=tk.X, padx=2, pady=2)
        art_grid.columnconfigure(0, weight=1)
        art_grid.columnconfigure(1, weight=1)
        art_grid.columnconfigure(2, weight=1)
        
        # Строка 0
        ttk.Checkbutton(art_grid, text="OPEN BASS (Бас)", variable=self.art_open_bass_var).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Checkbutton(art_grid, text="CHAPA (Слап)", variable=self.art_chapa_var).grid(row=0, column=1, sticky=tk.W, padx=4, pady=2)
        ttk.Checkbutton(art_grid, text="TCHIPOT (Прутик)", variable=self.art_tchipot_var).grid(row=0, column=2, sticky=tk.W, padx=4, pady=2)
        
        # Строка 1
        ttk.Checkbutton(art_grid, text="DUUM (Шлепок)", variable=self.art_duum_var).grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Checkbutton(art_grid, text="KOPAL (Колотушка)", variable=self.art_kopal_var).grid(row=1, column=1, sticky=tk.W, padx=4, pady=2)
        ttk.Checkbutton(art_grid, text="B.SLIDE (Слайд)", variable=self.art_slide_var).grid(row=1, column=2, sticky=tk.W, padx=4, pady=2)
        
        # Строка 2
        ttk.Checkbutton(art_grid, text="TEK_B (Тэк звон.)", variable=self.art_tek_B_var).grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Checkbutton(art_grid, text="CLAP TEK (Клэп)", variable=self.art_clap_tek_var).grid(row=2, column=1, sticky=tk.W, padx=4, pady=2)
        ttk.Checkbutton(art_grid, text="W.CLICK (Корпус)", variable=self.art_click_var).grid(row=2, column=2, sticky=tk.W, padx=4, pady=2)
        
        # Строка 3
        ttk.Checkbutton(art_grid, text="TEK_A (Тэк бас.)", variable=self.art_tek_A_var).grid(row=3, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Checkbutton(art_grid, text="MUTE (Глухой)", variable=self.art_mute_var).grid(row=3, column=1, sticky=tk.W, padx=4, pady=2)


        # --- ВКЛАДКА КОНСОЛИ (tab_console) ---
        log_frame = ttk.Frame(tab_console)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, bg="#000000", fg="#00ff66", insertbackground="#00ff66", font=("Courier", 8), height=10)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)


        # === ФИКСИРОВАННЫЙ НИЗ ПРАВОЙ КОЛОНКИ (Всегда виден) ===
        bottom_right_frame = ttk.Frame(right_col, padding=(0, 6, 0, 0))
        bottom_right_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(bottom_right_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 2))

        self.status_lbl = ttk.Label(bottom_right_frame, text="Готов к рендерингу.", font=("Helvetica", 8, "bold"))
        self.status_lbl.pack(anchor=tk.W, pady=1)

        self.btn_gen = ttk.Button(bottom_right_frame, text="🚀 ЗАПУСТИТЬ СИНТЕЗ 'THE HALL'", command=self.start_generation)
        self.btn_gen.pack(fill=tk.X, pady=(2, 0))

        # Обновляем текстовые значения для слайдеров
        self.update_slider_label("all")

    def update_slider_label(self, name):
        """Обновляет текстовые метки текущих значений слайдеров."""
        if name in ["all", "saturation"]:
            self.saturation_val_lbl.config(text=f"{self.saturation_var.get():.2f}x")
        if name in ["all", "mat_boost"]:
            self.mat_boost_val_lbl.config(text=f"{self.mat_boost_var.get():.2f}x")
        if name in ["all", "tactility"]:
            self.membrane_tactile_val_lbl.config(text=f"{self.membrane_tactile_var.get():.2f}x")
        if name in ["all", "snap"]:
            self.membrane_snap_val_lbl.config(text=f"{self.membrane_snap_var.get():.2f}x")
        if name in ["all", "shell_attack"]:
            self.shell_attack_val_lbl.config(text=f"{self.shell_attack_var.get():.2f}x")
        if name in ["all", "shell_sustain"]:
            self.shell_sustain_val_lbl.config(text=f"{self.shell_sustain_var.get():.2f}x")
        if name in ["all", "ring_mod"]:
            self.ring_mod_val_lbl.config(text=f"{self.ring_mod_var.get():.2f}x")
        if name in ["all", "bell_mix"]:
            self.bell_mix_val_lbl.config(text=f"{self.bell_mix_var.get():.2f}x")

    def update_dyn_layers_lbl(self, *args):
        self.dyn_layers_lbl.config(text=f"Слоев динамики (1–12): {int(self.dyn_layers_var.get())}")

    def log(self, message):
        self.log_text.insert(tk.END, f">> {message}\n")
        self.log_text.see(tk.END)
        logger.info(message)
        self.update()

    def update_frequency_labels(self, event=None):
        fA = note_to_frequency(self.note_A_var.get())
        fB = note_to_frequency(self.note_B_var.get())
        self.freq_A_lbl.config(text=f"Частота: {fA:.2f} Гц")
        self.freq_B_lbl.config(text=f"Частота: {fB:.2f} Гц")

    def _resolve_material_key(self, selected_value):
        if selected_value in MATERIAL_PHYSICS:
            return selected_value
        return selected_value.split(" ")[0].strip()

    def update_material_descriptions(self, event=None):
        skin_key = self._resolve_material_key(self.skin_mat_var.get())
        shell_key = self._resolve_material_key(self.shell_mat_var.get())
        skin = MATERIAL_PHYSICS.get(skin_key, {})
        shell = MATERIAL_PHYSICS.get(shell_key, {})
        desc = f"Мембрана: {skin.get('name', 'Custom')}. Кадушка: {shell.get('name', 'Custom')}."
        self.mat_desc_lbl.config(text=desc)
        
        self.update_acoustic_preview()

    def freq_to_note_approx(self, f: float) -> str:
        if f <= 0: return "N/A"
        h = 12 * np.log2(f / 440.0) + 69
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = int((h + 0.5) // 12) - 1
        note_idx = int(round(h)) % 12
        return f"{note_names[note_idx]}{octave}"

    def update_acoustic_preview(self, event=None):
        try:
            freq_A = note_to_frequency(self.note_A_var.get())
            freq_B = note_to_frequency(self.note_B_var.get())

            skin_key = "animal_skin"
            shell_key = "walnut"
            
            if hasattr(self, "skin_mat_var"):
                skin_key = self._resolve_material_key(self.skin_mat_var.get())
            if hasattr(self, "shell_mat_var"):
                shell_key = self._resolve_material_key(self.shell_mat_var.get())
                
            skin_mat = MATERIAL_PHYSICS.get(skin_key, {})
            shell_mat = MATERIAL_PHYSICS.get(shell_key, {})

            E_shell = shell_mat.get("E_long", 10.0)
            den_shell = shell_mat.get("density", 0.5)
            loss_shell = shell_mat.get("loss_factor", 0.02)
            
            v_sound = np.sqrt((E_shell * 1e9) / (den_shell * 1000.0)) if den_shell > 0 else 0
            base_shell = np.clip(v_sound * 0.06, 150.0, 4500.0)
            
            autotune_msg = ""
            autotune_active = self.autotune_shell_var.get() if hasattr(self, "autotune_shell_var") else False
            
            if autotune_active and freq_A > 0:
                ratio = base_shell / freq_A
                consonant_multipliers = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
                best_mult = min(consonant_multipliers, key=lambda x: abs(x - ratio))
                base_shell = freq_A * best_mult
                
                mult_names = {
                    1.5: "Чистая квинта (1.5x)",
                    2.0: "Октава (2.0x)",
                    2.5: "Децима / Терция через октаву (2.5x)",
                    3.0: "Дуодецима / Квинта через октаву (3.0x)",
                    4.0: "Двойная октава (4.0x)",
                    5.0: "Двойная октава + терция (5.0x)",
                    6.0: "Двойная октава + квинта (6.0x)",
                    8.0: "Тройная октава (8.0x)"
                }
                autotune_msg = f"• Luthier Autotune: корпус подстроен в {mult_names.get(best_mult, f'{best_mult}x')}\n"
            
            shell_modes = [
                base_shell,
                base_shell * 1.61,
                base_shell * 2.3,
                base_shell * 3.5
            ]

            bessel_ratios = [1.0, 1.59, 2.14, 2.30, 2.65, 3.0, 4.0, 5.0, 6.0]
            membrane_A_modes = [freq_A * r for r in bessel_ratios]

            clashes = []
            
            intervals_db = [
                (0.0, "Унисон (Unison)", "Абсолютный консонанс. Сверх-сфокусированный тон, но может звучать сухо.", "Нормально"),
                (1.0, "Малая секунда (Minor 2nd)", "Сильные биения («зуд», грязь в СЧ). Опасная зона критической полосы.", "Критично!"),
                (2.0, "Большая секунда (Major 2nd)", "Резкий диссонанс. Агрессивный звенящий характер, как у малых барабанов.", "Приемлемо"),
                (3.0, "Малая терция (Minor 3rd)", "Мягкий консонанс. Меланхоличный, темный, этнический характер.", "Отлично"),
                (4.0, "Большая терция (Major 3rd)", "Яркий консонанс. Открытое, мажорное, поющее звучание кадушки.", "Отлично"),
                (5.0, "Чистая кварта (Perfect 4th)", "Сильный консонанс. Объемный, «пустотелый» деревянный тон (как литавры).", "Отлично"),
                (6.0, "Тритон (Tritone)", "Нестабильный диссонанс. Напряженный металлический или колокольный звон.", "Экспериментально"),
                (7.0, "Чистая квинта (Perfect 5th)", "Золотой стандарт консонанса. Сбалансированный богатый сустейн корпуса.", "Идеально!"),
                (8.0, "Малая секста (Minor 6th)", "Мягкий диссонанс. Загадочный, теплый, но слегка натянутый тембр.", "Нормально"),
                (9.0, "Большая секста (Major 6th)", "Сладкий консонанс. Широкое, открытое дыхание деревянного резонатора.", "Отлично"),
                (10.0, "Малая септима (Minor 7th)", "Джазовый диссонанс. Сложный, слегка дерзкий, но интересный сустейн.", "Нормально"),
                (11.0, "Большая септима (Major 7th)", "Сильный диссонанс. Напряженные фазовые трения. Возможна грязь.", "Warning"),
                (12.0, "Октава (Octave)", "Идеальное слияние. Корпус полностью резонирует с мембраной без каши.", "Идеально!")
            ]

            for s_idx, s_freq in enumerate(shell_modes):
                if autotune_active and s_idx == 0:
                    continue

                for m_idx, m_freq in enumerate(membrane_A_modes):
                    ratio = s_freq / m_freq if m_freq > 0 else 1.0
                    
                    memb_mult = bessel_ratios[m_idx]
                    allowed_window = 1.090 if memb_mult <= 4.0 else 1.030 
                    allowed_low = 1.0 / allowed_window
                    
                    if allowed_low <= ratio <= allowed_window:
                        semitones_diff = abs(12 * np.log2(ratio))
                        
                        reduced_semi = semitones_diff % 12
                        if reduced_semi > 6.0:
                            reduced_semi = 12.0 - reduced_semi
                            
                        best_interval = min(intervals_db, key=lambda x: abs(x[0] - reduced_semi))
                        
                        rating = best_interval[3]
                        if memb_mult > 4.0 and rating == "Критично!":
                            rating = "Допустимо (Верха)"
                        
                        clashes.append({
                            "shell_mode": f"Корпус #{s_idx+1} ({s_freq:.1f} Гц)",
                            "memb_mode": f"Мембрана {memb_mult}x ({m_freq:.1f} Гц)",
                            "memb_mult": memb_mult,
                            "diff": semitones_diff,
                            "interval_name": best_interval[1],
                            "desc": best_interval[2],
                            "rating": rating
                        })

            has_critical_seconds = any(c['diff'] < 1.8 and c['memb_mult'] <= 4.0 for c in clashes)
            
            material_category = shell_mat.get("category", "wood")
            category_names = {"wood": "Дерево", "mineral": "Минерал", "metal": "Металл"}
            mat_type_name = category_names.get(material_category, "Материал")

            if loss_shell < 0.008:
                if has_critical_seconds:
                    timbre_type = f"[{mat_type_name} / Агрессивный / Биения]"
                    timbre_desc = f"Корпус ({shell_mat.get('name', shell_key)}) звенит как колокол и конфликтует в нижнем регистре. Ожидаются биения и фазовая грязь в основе звука."
                else:
                    timbre_type = f"[{mat_type_name} / Кристальный / Чистый]"
                    timbre_desc = f"Яркий колокольный отзвук. Плотный {mat_type_name.lower()} даст чистые высокие обертона с долгим красивым затуханием."
            else:
                if has_critical_seconds:
                    timbre_type = f"[{mat_type_name} / Глуховатый / Биения]"
                    timbre_desc = f"Пористая структура, которую имеет этот {mat_type_name.lower()}, отлично гасит звон, но низкочастотные биения приведут к фазовым вычитаниям в теле барабана."
                else:
                    if autotune_active:
                        timbre_type = f"[{mat_type_name} / Гармоничный / Чистый]"
                        timbre_desc = f"Luthier Autotune подстроил резонансы. {mat_type_name} теперь звучит в идеальном консонансе с мембраной."
                    else:
                        timbre_type = f"[{mat_type_name} / Органический / Сбалансированный]"
                        timbre_desc = f"Сбалансированное звучание. Вязкий {mat_type_name.lower()} мягко резонирует в гармонии с мембраной, давая упругую, плотную середину."

            preview_text = f"ФИЗИКА КОРПУСА ({shell_mat.get('name', shell_key)}):\n"
            preview_text += f"• Скорость звука: {v_sound:.0f} м/с | Базовый тон кадушки: {base_shell:.1f} Гц (~{self.freq_to_note_approx(base_shell)})\n"
            if autotune_msg:
                preview_text += autotune_msg
            preview_text += f"• Резонансы: " + ", ".join([f"{f:.1f}Гц" for f in shell_modes[:3]]) + "\n"
            preview_text += f"\nПРОГНОЗ ТЕМБРА: {timbre_type}\n{timbre_desc}\n"

            if clashes:
                clashes_sorted = sorted(clashes, key=lambda x: 0 if x['rating'] == "Критично!" else 1)
                preview_text += f"\n⚠️ АНАЛИЗ СОЗВУЧИЙ (Близость моды корпуса и мембраны):\n"
                for c in clashes_sorted[:2]:
                    preview_text += f" * {c['shell_mode']} + {c['memb_mode']}:\n"
                    preview_text += f"   Интервал: {c['interval_name']} (Разница: {c['diff']:.2f} п.т.)\n"
                    preview_text += f"   Оценка для барабана: {c['rating']}\n"
                    preview_text += f"   Характер: {c['desc']}\n"
            else:
                preview_text += "\n✅ КОНФЛИКТОВ НЕ ОБНАРУЖЕНО\n"
                preview_text += " Корпус и мембрана идеально гармонируют. Спектр чистый, без грязи."

            self.preview_lbl.config(text=preview_text)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.preview_lbl.config(text=f"⚠️ Ошибка анализатора:\n{str(e)}")

    def toggle_bells_ui(self, event=None):
        state = tk.NORMAL if self.use_bells_var.get() else tk.DISABLED
        self.bell_selector.config(state="readonly" if state == tk.NORMAL else tk.DISABLED)
        self.bell_mix_scale.config(state=state)

    def start_generation(self):
        if self.is_rendering:
            return
        
        self.is_rendering = True
        self.btn_gen.config(state=tk.DISABLED)
        self.progress_var.set(0.0)
        self.log_text.delete("1.0", tk.END)
        
        self.run_generation()

    def run_generation(self):
        note_A = self.note_A_var.get()
        note_B = self.note_B_var.get()
        freq_A = note_to_frequency(note_A)
        freq_B = note_to_frequency(note_B)
        
        skin_name = self._resolve_material_key(self.skin_mat_var.get())
        shell_name = self._resolve_material_key(self.shell_mat_var.get())

        grid_res = "default"
        try:
            if hasattr(self, 'main_app') and self.main_app is not None:
                for attr_name, attr_val in self.main_app.__dict__.items():
                    if 'grid' in attr_name.lower() or 'resolution' in attr_name.lower():
                        try:
                            val = attr_val.get()
                            if val:
                                grid_res = str(val)
                                break
                        except Exception:
                            pass
        except Exception:
            pass
        output_dir = f"@Dhol_Samples_{skin_name}_{shell_name}_{grid_res}"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        articulations = []
        if self.art_open_bass_var.get(): articulations.append("open_bass")
        if self.art_duum_var.get(): articulations.append("duum")
        if self.art_tek_B_var.get(): articulations.append("tek_B")
        if self.art_tek_A_var.get(): articulations.append("tek_A")
        if self.art_clap_tek_var.get(): articulations.append("clap_tek")
        if self.art_mute_var.get(): articulations.append("mute")
        if self.art_chapa_var.get(): articulations.append("chapa")
        if self.art_kopal_var.get(): articulations.append("kopal")
        if self.art_tchipot_var.get(): articulations.append("tchipot")
        if self.art_slide_var.get(): articulations.append("bass_slide")
        if self.art_click_var.get(): articulations.append("wood_click")

        if not articulations:
            self.log("ОШИБКА: Не выбрана ни одна артикуляция!")
            messagebox.showwarning("Внимание", "Пожалуйста, выберите хотя бы одну артикуляцию для экспорта!")
            self.is_rendering = False
            self.btn_gen.config(state=tk.NORMAL)
            return

        self.log("Инициализация физического движка 'The Dhol' (Main Thread)...")
        self.log(f"Настройка Дум (Бас) -> {note_A} | Тэк -> {note_B}...")

        try:
            if self.batch_render_var.get():
                layer_count = int(self.dyn_layers_var.get())
                if layer_count == 1:
                    velocities = [127]
                elif layer_count == 2:
                    velocities = [64, 127]
                else:
                    raw = [16 + (127 - 16) * ((i / (layer_count - 1)) ** 1.5) for i in range(layer_count)]
                    velocities = sorted(set(int(round(v)) for v in raw))
                    velocities[-1] = 127
                num_rr = self.rr_var.get()
                total_files = len(velocities) * len(articulations) * num_rr
                current_file_idx = 0

                for art in articulations:
                    for vel in velocities:
                        for rr in range(1, num_rr + 1):
                            self.status_lbl.config(text=f"Синтез: {art.upper()} | Vel: {vel} | RR: {rr}...")
                            self.log(f"[{current_file_idx+1}/{total_files}] Рендеринг {art.upper()} (vel: {vel}, rr: {rr})...")
                            
                            force = vel / 127.0
                            
                            def step_cb(step, num_steps):
                                base_pct = (current_file_idx / total_files) * 100
                                file_pct = (step / num_steps) * (100 / total_files)
                                self.progress_var.set(base_pct + file_pct)
                                self.update()

                            audio = synthesize_dhol_strike(
                                freq_A, freq_B, articulation=art, strike_force=force, 
                                skin_mat_name=skin_name, shell_mat_name=shell_name,
                                yield_cb=step_cb,
                                saturation=self.saturation_var.get(),
                                mat_boost=self.mat_boost_var.get(),
                                membrane_tactile=self.membrane_tactile_var.get(),
                                membrane_snap=self.membrane_snap_var.get(),
                                shell_attack=self.shell_attack_var.get(),
                                shell_sustain=self.shell_sustain_var.get(),
                                autotune_shell=self.autotune_shell_var.get(),
                                ring_mod=self.ring_mod_var.get(),
                                rr_index=rr,
                                show_gui=True,
                                use_bells=self.use_bells_var.get(),
                                bell_material=self._resolve_material_key(self.bell_mat_var.get()),
                                bell_mix=self.bell_mix_var.get()
                            )
                            
                            assigned_note = note_A if art in ["open_bass", "duum", "chapa", "mute", "bass_slide", "tek_A"] else note_B
                            out_path = os.path.join(output_dir, f"Dhol_{art.capitalize()}_{assigned_note}_v{vel:03d}_rr{rr}.wav")
                            wav.write(out_path, 44100, audio.astype(np.float32))
                            current_file_idx += 1

                self.status_lbl.config(text="Рендеринг завершен!")
                self.log("ПАК УСПЕШНО СГЕНЕРИРОВАН!")
                messagebox.showinfo("Успех", f"Пак сэмплов сохранен в папку '{output_dir}'!")
            else:
                test_art = articulations[0]
                self.status_lbl.config(text=f"Синтез одиночного удара {test_art.upper()}...")
                self.log(f"Рендеринг тестового удара {test_art.upper()} (100% Velocity)...")
                
                def step_cb_single(step, num_steps):
                    self.progress_var.set((step / num_steps) * 100)
                    self.update()

                audio = synthesize_dhol_strike(
                    freq_A, freq_B, articulation=test_art, strike_force=1.0, 
                    skin_mat_name=skin_name, shell_mat_name=shell_name,
                    yield_cb=step_cb_single,
                    saturation=self.saturation_var.get(),
                    mat_boost=self.mat_boost_var.get(),
                    membrane_tactile=self.membrane_tactile_var.get(),
                    membrane_snap=self.membrane_snap_var.get(),
                    shell_attack=self.shell_attack_var.get(),
                    shell_sustain=self.shell_sustain_var.get(),
                    autotune_shell=self.autotune_shell_var.get(),
                    ring_mod=self.ring_mod_var.get(),
                    rr_index=1,
                    show_gui=True,
                    use_bells=self.use_bells_var.get(),
                    bell_material=self._resolve_material_key(self.bell_mat_var.get()),
                    bell_mix=self.bell_mix_var.get()
                )
                
                assigned_note = note_A if test_art in ["open_bass", "duum", "chapa", "mute", "bass_slide", "tek_A"] else note_B
                out_path = os.path.join(output_dir, f"Dhol_{test_art.capitalize()}_{assigned_note}_Test.wav")
                wav.write(out_path, 44100, audio.astype(np.float32))
                
                self.status_lbl.config(text="Готово!")
                self.log(f"Тестовый файл сохранен: {out_path}")
                messagebox.showinfo("Успех", f"Тестовый файл сохранен в '{out_path}'")

        except Exception as e:
            self.log(f"КРИТИЧЕСКАЯ ОШИБКА ДВИЖКА: {e}")
            messagebox.showerror("Ошибка рендеринга", f"Произошел сбой симуляции: {e}")
        finally:
            self.is_rendering = False
            self.btn_gen.config(state=tk.NORMAL)