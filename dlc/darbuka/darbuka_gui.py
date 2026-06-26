# dlc/darbuka/darbuka_gui.py
import os
import re
import glob
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import scipy.io.wavfile as wav
import numpy as np
import logging

from dlc.darbuka.darbuka_engine import synthesize_darbuka_strike, note_to_frequency
from config.materials import MATERIAL_PHYSICS
from ui.utils import format_material_display, format_material_list, extract_key_from_display

logger = logging.getLogger("TheHall.GUI")

# =====================================================================
#  УПАКОВЩИК СЭМПЛОВ ДАРБУКИ (Встроенный)
# =====================================================================
class DarbukaPackerFrame(ttk.Frame):
    def __init__(self, parent, main_app_ref=None):
        super().__init__(parent)
        self.main_app = main_app_ref
        self.setup_ui()

    def setup_ui(self):
        container = ttk.Frame(self, padding="15")
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(container, text="📦 УПАКОВЩИК СЭМПЛОВ ДАРБУКИ (.multisample)", font=("Helvetica", 12, "bold"), foreground="#ff9933")
        header.pack(anchor=tk.W, pady=(0, 15))

        dirs_frame = ttk.LabelFrame(container, text=" Директории ", padding="10")
        dirs_frame.pack(fill=tk.X, pady=5)

        ttk.Label(dirs_frame, text="Папка с WAV файлами:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.input_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "Darbuka_Samples"))
        self.entry_input = ttk.Entry(dirs_frame, textvariable=self.input_dir_var, width=50)
        self.entry_input.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(dirs_frame, text="Обзор...", command=self.browse_input).grid(row=0, column=2, pady=5)

        ttk.Label(dirs_frame, text="Папка для .multisample:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "Troakar_Multisamples"))
        self.entry_output = ttk.Entry(dirs_frame, textvariable=self.output_dir_var, width=50)
        self.entry_output.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(dirs_frame, text="Обзор...", command=self.browse_output).grid(row=1, column=2, pady=5)

        dirs_frame.columnconfigure(1, weight=1)

        opts_frame = ttk.LabelFrame(container, text=" Настройки сборки ", padding="10")
        opts_frame.pack(fill=tk.X, pady=5)

        ttk.Label(opts_frame, text="Суффикс инструмента (опционально):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.custom_name_var = tk.StringVar(value="")
        self.entry_custom_name = ttk.Entry(opts_frame, textvariable=self.custom_name_var, width=30)
        self.entry_custom_name.grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)

        self.btn_pack = ttk.Button(container, text="🚀 СФОРМИРОВАТЬ ИНСТРУМЕНТЫ (.multisample)", command=self.start_packing)
        self.btn_pack.pack(fill=tk.X, pady=15, ipady=5)

        log_frame = ttk.LabelFrame(container, text=" Консоль сборки ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=12, bg="#000000", fg="#ffcc66", insertbackground="#ffcc66", font=("Consolas", 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.update()

    def browse_input(self):
        d = filedialog.askdirectory(initialdir=os.getcwd(), title="Выберите папку с отрендеренными WAV")
        if d: self.input_dir_var.set(d)

    def browse_output(self):
        d = filedialog.askdirectory(initialdir=os.getcwd(), title="Выберите папку для Multisamples")
        if d: self.output_dir_var.set(d)

    def start_packing(self):
        self.btn_pack.config(state=tk.DISABLED)
        self.log_text.delete("1.0", tk.END)

        src_dir = self.input_dir_var.get()
        dst_dir = self.output_dir_var.get()
        custom_name = self.custom_name_var.get().strip()

        if not os.path.exists(src_dir):
            self.log(f"❌ ОШИБКА: Папка '{src_dir}' не найдена!")
            self.btn_pack.config(state=tk.NORMAL)
            return

        os.makedirs(dst_dir, exist_ok=True)
        wav_paths = glob.glob(os.path.join(src_dir, "**", "*.wav"), recursive=True)
        
        self.log(f"🔍 Найдено WAV файлов: {len(wav_paths)}")
        arts_db = {}
        
        pattern = r"Darbuka_(?P<art>.+?)_(?P<note>[A-G]#?\d)_(?P<skin>.+?)_(?P<shell>.+?)_v(?P<vel>\d+)_rr(?P<rr>\d+)\.wav"
        
        for path in wav_paths:
            match = re.match(pattern, os.path.basename(path))
            if match:
                meta = match.groupdict()
                meta['fullpath'] = path
                meta['filename'] = os.path.basename(path)
                try:
                    meta['frames'] = wav.read(path)[1].shape[0] if wav.read(path)[1].ndim > 1 else len(wav.read(path)[1])
                except Exception:
                    continue
                    
                art_key = f"{meta['art']}_{meta['skin']}_{meta['shell']}"
                if art_key not in arts_db: arts_db[art_key] = []
                arts_db[art_key].append(meta)

        if not arts_db:
            self.log("❌ Файлы не распознаны. Проверьте правильность имен (Darbuka_Art_Note...).")
            self.btn_pack.config(state=tk.NORMAL)
            return

        for key, files in arts_db.items():
            meta = files[0]
            suffix = f" {custom_name}" if custom_name else ""
            display_name = f"Darbuka {meta['art'].title()} ({meta['skin']} + {meta['shell']}){suffix}"
            file_name_base = f"Darbuka_{meta['art'].capitalize()}_{meta['skin']}_{meta['shell']}"
            
            out_path = os.path.join(dst_dir, f"{file_name_base}.multisample")
            self.log(f" • Сборка: {display_name} -> {os.path.basename(out_path)}")
            
            # Генерация XML
            xml_nodes = []
            for f in files:
                note_idx = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'].index(f["note"][:-1].replace('b','')) + (int(f["note"][-1]) + 1)*12
                v = int(f["vel"])
                low_v = max(1, v - 10) # Упрощенное распределение велосити
                high_v = min(127, v + 10)
                
                xml = f'   <sample file="{f["filename"]}" gain="0.00" reverse="false" sample-start="0.000" sample-stop="{float(f["frames"]):.3f}" zone-logic="round-robin" round-robin="{f["rr"]}">\n'
                xml += f'      <key high="127" low="0" root="{note_idx}" track="0.0000" tune="0.00"/>\n'
                xml += f'      <velocity high="{high_v}" low="{low_v}"/>\n   </sample>'
                xml_nodes.append(xml)
                
            xml_content = f'<?xml version="1.0" encoding="UTF-8"?>\n<multisample name="{display_name}">\n' + "\n".join(xml_nodes) + "\n</multisample>"

            with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_STORED) as z:
                z.writestr("multisample.xml", xml_content)
                for f in files: z.write(f['fullpath'], f['filename'])
                
            self.update()

        self.log("✅ ВСЕ ИНСТРУМЕНТЫ УПАКОВАНЫ!")
        self.btn_pack.config(state=tk.NORMAL)

# =====================================================================
#  ГЛАВНЫЙ ИНТЕРФЕЙС DARBUKA
# =====================================================================
class DarbukaDLCFrame(ttk.Notebook):
    def __init__(self, parent, main_app_ref):
        super().__init__(parent)
        self.main_app = main_app_ref
        self.is_rendering = False

        tab_engine = ttk.Frame(self, padding="0")
        self.packer_tab = DarbukaPackerFrame(self, main_app_ref)

        self.add(tab_engine, text="Darbuka Engine")
        self.add(self.packer_tab, text="Packer / Multisamples")

        self.setup_ui(tab_engine)

    def setup_ui(self, container):
        header = ttk.Label(container, text="THE DARBUKA — FDTD Моделирование Кубка", font=("Helvetica", 12, "bold"), foreground="#ff9933")
        header.pack(anchor=tk.W, pady=(0, 6))

        main_grid = ttk.Frame(container)
        main_grid.pack(fill=tk.BOTH, expand=True)
        main_grid.columnconfigure(0, weight=1, uniform="group1")
        main_grid.columnconfigure(1, weight=1, uniform="group1")
        main_grid.rowconfigure(0, weight=1)

        # === ЛЕВАЯ КОЛОНКА ===
        left_col = ttk.Frame(main_grid)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        
        left_notebook = ttk.Notebook(left_col)
        left_notebook.pack(fill=tk.BOTH, expand=True)
        
        tab_core = ttk.Frame(left_notebook, padding="6")
        tab_physics = ttk.Frame(left_notebook, padding="6")
        
        left_notebook.add(tab_core, text="🎹 Настройка и Акустика")
        left_notebook.add(tab_physics, text="🪵 Физика")

        # --- ВКЛАДКА 1: БАЗА ---
        tuning_group = ttk.LabelFrame(tab_core, text=" Натяжение мембраны (Tuning) ", padding="6")
        tuning_group.pack(fill=tk.X, pady=2)

        ttk.Label(tuning_group, text="Основной тон (Doum):").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.note_var = tk.StringVar(value="D3")
        notes_list = ["G2", "G#2", "A2", "A#2", "B2", "C3", "C#3", "D3", "D#3", "E3", "F3", "F#3", "G3", "G#3", "A3"]
        self.combo_note = ttk.Combobox(tuning_group, textvariable=self.note_var, values=notes_list, width=6, state="readonly")
        self.combo_note.grid(row=0, column=1, padx=4, pady=2)
        self.combo_note.bind("<<ComboboxSelected>>", self.update_frequency_labels)
        self.freq_lbl = ttk.Label(tuning_group, text="Частота: 146.83 Гц", foreground="#888")
        self.freq_lbl.grid(row=0, column=2, padx=8, pady=2, sticky=tk.W)

        material_group = ttk.LabelFrame(tab_core, text=" Физика материалов ", padding="6")
        material_group.pack(fill=tk.X, pady=2)

        self.mat_list = format_material_list(MATERIAL_PHYSICS)

        ttk.Label(material_group, text="Пластик/Кожа (Мембрана):").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.skin_mat_var = tk.StringVar(value=format_material_display("mylar_standard", MATERIAL_PHYSICS))
        self.skin_selector = ttk.Combobox(material_group, textvariable=self.skin_mat_var, values=self.mat_list, state="readonly", width=28)
        self.skin_selector.grid(row=0, column=1, padx=4, pady=2, sticky=tk.W)

        ttk.Label(material_group, text="Металл/Керамика (Кубок):").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        self.shell_mat_var = tk.StringVar(value=format_material_display("aluminum", MATERIAL_PHYSICS))
        self.shell_selector = ttk.Combobox(material_group, textvariable=self.shell_mat_var, values=self.mat_list, state="readonly", width=28)
        self.shell_selector.grid(row=1, column=1, padx=4, pady=2, sticky=tk.W)

        # --- ВКЛАДКА 2: ФИЗИКА ---
        character_group = ttk.LabelFrame(tab_physics, text=" Окрас и Тактильность ", padding="6")
        character_group.pack(fill=tk.X, pady=2)

        char_grid = ttk.Frame(character_group)
        char_grid.pack(fill=tk.X, expand=True)
        char_grid.columnconfigure(1, weight=1)

        self.saturation_var = tk.DoubleVar(value=0.25)
        ttk.Label(char_grid, text="Tape Saturation:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Scale(char_grid, from_=0.0, to=2.0, variable=self.saturation_var, orient="horizontal").grid(row=0, column=1, sticky=tk.EW, padx=4)

        self.mat_boost_var = tk.DoubleVar(value=0.5)
        ttk.Label(char_grid, text="Tactile Sand/Grit:").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Scale(char_grid, from_=0.0, to=2.0, variable=self.mat_boost_var, orient="horizontal").grid(row=1, column=1, sticky=tk.EW, padx=4)

        # === ПРАВАЯ КОЛОНКА ===
        right_col = ttk.Frame(main_grid)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        right_notebook = ttk.Notebook(right_col)
        right_notebook.pack(fill=tk.BOTH, expand=True)

        tab_export = ttk.Frame(right_notebook, padding="6")
        tab_console = ttk.Frame(right_notebook, padding="6")

        right_notebook.add(tab_export, text="📦 Экспорт и Артикуляции")
        right_notebook.add(tab_console, text="💻 Консоль")

        # --- ЭКСПОРТ ---
        export_group = ttk.Frame(tab_export)
        export_group.pack(fill=tk.BOTH, expand=True)

        self.batch_render_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(export_group, text="Пакетный рендер (Velocity 16–127)", variable=self.batch_render_var).pack(anchor=tk.W, pady=2)

        settings_subframe = ttk.Frame(export_group)
        settings_subframe.pack(fill=tk.X, anchor=tk.W, pady=3)
        
        ttk.Label(settings_subframe, text="Слоев Velocity:").grid(row=0, column=0, padx=4)
        self.dyn_layers_var = tk.IntVar(value=6)
        ttk.Combobox(settings_subframe, textvariable=self.dyn_layers_var, values=[1, 2, 4, 6, 8, 12], width=3, state="readonly").grid(row=0, column=1, padx=4)
        
        ttk.Label(settings_subframe, text="Round Robin:").grid(row=0, column=2, padx=4)
        self.rr_var = tk.IntVar(value=3)
        ttk.Combobox(settings_subframe, textvariable=self.rr_var, values=[1, 2, 3, 4, 5], width=3, state="readonly").grid(row=0, column=3, padx=4)

        art_select_group = ttk.LabelFrame(export_group, text=" Артикуляции ", padding="6")
        art_select_group.pack(fill=tk.BOTH, expand=True, pady=4)

        self.art_doum_var = tk.BooleanVar(value=True)
        self.art_tek_var = tk.BooleanVar(value=True)
        self.art_ka_var = tk.BooleanVar(value=True)
        self.art_slap_var = tk.BooleanVar(value=True)
        self.art_roll_var = tk.BooleanVar(value=False)
        self.art_mute_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(art_select_group, text="DOUM (Глубокий бас в центр)", variable=self.art_doum_var).grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Checkbutton(art_select_group, text="TEK (Высокий звон в край)", variable=self.art_tek_var).grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Checkbutton(art_select_group, text="KA (Тэк левой рукой)", variable=self.art_ka_var).grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Checkbutton(art_select_group, text="SLAP (Резкий глухой шлепок)", variable=self.art_slap_var).grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Checkbutton(art_select_group, text="ROLL (Микро-пальцевая дробь)", variable=self.art_roll_var).grid(row=4, column=0, sticky=tk.W, pady=2)
        ttk.Checkbutton(art_select_group, text="MUTE (Приглушенный)", variable=self.art_mute_var).grid(row=5, column=0, sticky=tk.W, pady=2)

        # --- КОНСОЛЬ ---
        self.log_text = tk.Text(tab_console, bg="#000000", fg="#ff9933", insertbackground="#ff9933", font=("Courier", 8))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- НИЖНЯЯ ПАНЕЛЬ ---
        bottom_right_frame = ttk.Frame(right_col, padding=(0, 6, 0, 0))
        bottom_right_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(bottom_right_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 2))

        self.status_lbl = ttk.Label(bottom_right_frame, text="Готов к рендерингу.", font=("Helvetica", 8, "bold"))
        self.status_lbl.pack(anchor=tk.W, pady=1)

        self.btn_gen = ttk.Button(bottom_right_frame, text="🚀 ЗАПУСТИТЬ СИНТЕЗ 'DARBUKA'", command=self.start_generation)
        self.btn_gen.pack(fill=tk.X, pady=(2, 0))

        self.update_frequency_labels()

    def update_frequency_labels(self, event=None):
        f = note_to_frequency(self.note_var.get())
        self.freq_lbl.config(text=f"Частота: {f:.2f} Гц")

    def log(self, message):
        self.log_text.insert(tk.END, f">> {message}\n")
        self.log_text.see(tk.END)
        self.update()

    def _resolve_material_key(self, selected_value):
        if selected_value in MATERIAL_PHYSICS: return selected_value
        return extract_key_from_display(selected_value)

    def start_generation(self):
        if self.is_rendering: return
        self.is_rendering = True
        self.btn_gen.config(state=tk.DISABLED)
        self.progress_var.set(0.0)
        self.log_text.delete("1.0", tk.END)
        self.run_generation()

    def run_generation(self):
        note = self.note_var.get()
        freq = note_to_frequency(note)
        skin_name = self._resolve_material_key(self.skin_mat_var.get())
        shell_name = self._resolve_material_key(self.shell_mat_var.get())

        grid_res = 256
        output_dir = f"@Darbuka_Samples_{skin_name}_{shell_name}"
        os.makedirs(output_dir, exist_ok=True)

        articulations = []
        if self.art_doum_var.get(): articulations.append("doum")
        if self.art_tek_var.get(): articulations.append("tek")
        if self.art_ka_var.get(): articulations.append("ka")
        if self.art_slap_var.get(): articulations.append("slap")
        if self.art_roll_var.get(): articulations.append("roll")
        if self.art_mute_var.get(): articulations.append("mute")

        if not articulations:
            self.log("ОШИБКА: Не выбрана ни одна артикуляция!")
            self.is_rendering = False
            self.btn_gen.config(state=tk.NORMAL)
            return

        self.log("Инициализация физического движка 'The Darbuka'...")

        try:
            if self.batch_render_var.get():
                layer_count = int(self.dyn_layers_var.get())
                if layer_count == 1: velocities = [127]
                elif layer_count == 2: velocities = [64, 127]
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
                            
                            def step_cb(step, num_steps):
                                base_pct = (current_file_idx / total_files) * 100
                                file_pct = (step / num_steps) * (100 / total_files)
                                self.progress_var.set(base_pct + file_pct)
                                self.update()

                            audio = synthesize_darbuka_strike(
                                target_freq=freq, articulation=art, strike_force=vel/127.0, 
                                skin_mat_name=skin_name, shell_mat_name=shell_name,
                                yield_cb=step_cb,
                                saturation=self.saturation_var.get(),
                                mat_boost=self.mat_boost_var.get(),
                                show_gui=True, N_grid=grid_res, rr_index=rr
                            )
                            
                            out_path = os.path.join(output_dir, f"Darbuka_{art.capitalize()}_{note}_{skin_name}_{shell_name}_v{vel:03d}_rr{rr}.wav")
                            wav.write(out_path, 44100, audio.astype(np.float32))
                            current_file_idx += 1

                self.status_lbl.config(text="Рендеринг завершен!")
                self.log("ПАК УСПЕШНО СГЕНЕРИРОВАН!")
                messagebox.showinfo("Успех", f"Пак сэмплов сохранен в папку '{output_dir}'!")
            else:
                test_art = articulations[0]
                self.status_lbl.config(text=f"Синтез одиночного удара {test_art.upper()}...")
                
                def step_cb_single(step, num_steps):
                    self.progress_var.set((step / num_steps) * 100)
                    self.update()

                audio = synthesize_darbuka_strike(
                    target_freq=freq, articulation=test_art, strike_force=1.0, 
                    skin_mat_name=skin_name, shell_mat_name=shell_name,
                    yield_cb=step_cb_single,
                    saturation=self.saturation_var.get(),
                    mat_boost=self.mat_boost_var.get(),
                    show_gui=True, N_grid=grid_res, rr_index=1
                )
                
                out_path = os.path.join(output_dir, f"Darbuka_{test_art.capitalize()}_{note}_Test.wav")
                wav.write(out_path, 44100, audio.astype(np.float32))
                self.status_lbl.config(text="Готово!")
                self.log(f"Тестовый файл сохранен: {out_path}")

        except Exception as e:
            self.log(f"КРИТИЧЕСКАЯ ОШИБКА ДВИЖКА: {e}")
            messagebox.showerror("Ошибка", f"Сбой симуляции: {e}")
        finally:
            self.is_rendering = False
            self.btn_gen.config(state=tk.NORMAL)