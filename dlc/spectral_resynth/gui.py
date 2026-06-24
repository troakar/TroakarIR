import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog
from tkinterdnd2 import DND_FILES
from config.materials import MATERIAL_PHYSICS

from .engine import process_hybrid_material, play_preview, stop_preview, batch_process

class SpectralResynthTab(ttk.Frame):
    def __init__(self, parent_widget, main_app_ref):
        super().__init__(parent_widget)
        self.main_app = main_app_ref
        self.files = []
        self.current_processed = None
        self.current_sr = None
        self.init_ui()

    def init_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)

        # === ЛЕВАЯ ПАНЕЛЬ: СПИСОК ФАЙЛОВ И ДРАГ-ЭНД-ДРОП ===
        left_frame = ttk.Frame(self, padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew")
        left_frame.rowconfigure(2, weight=1)
        left_frame.columnconfigure(0, weight=1)

        btn_load = ttk.Button(left_frame, text="📁 Загрузить сэмплы", command=self.load_files)
        btn_load.grid(row=0, column=0, pady=5, sticky="ew")

        # Надпись-подсказка про драг-энд-дроп
        self.lbl_dnd = ttk.Label(left_frame, text="✨ Перетащи файлы сюда (Drag & Drop) ✨", anchor="center", foreground="#888888")
        self.lbl_dnd.grid(row=1, column=0, pady=2)

        self.file_list = tk.Listbox(left_frame, selectmode=tk.SINGLE, background="#1e1e1e", foreground="white", highlightthickness=0)
        self.file_list.grid(row=2, column=0, pady=5, sticky="nsew")
        self.file_list.bind("<<ListboxSelect>>", self.on_file_select)

        # Скроллбар
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.file_list.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.file_list.configure(yscrollcommand=scrollbar.set)

        btn_process_all = ttk.Button(left_frame, text="⚡ Рендер Batch", command=self.render_batch)
        btn_process_all.grid(row=3, column=0, pady=5, sticky="ew")

        # --- Дrag & Drop через tkinterdnd2 ---
        self.file_list.drop_target_register(DND_FILES)
        self.file_list.dnd_bind('<<Drop>>', self.on_files_dropped)
        self.lbl_dnd.config(text="✨ Перетащи файлы прямо в список! ✨", foreground="#00ff66")

        # === ПРАВАЯ ПАНЕЛЬ: ФИЗИЧЕСКАЯ АЛХИМИЯ ===
        right_frame = ttk.Frame(self, padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)

        # --- БЛОК 1: МАТЕРИАЛЫ ---
        mat_group = ttk.LabelFrame(right_frame, text=" Акустический Сплав ", padding=10)
        mat_group.grid(row=0, column=0, pady=5, sticky="ew")
        mat_group.columnconfigure(0, weight=1)

        ttk.Label(mat_group, text="Материал А (База):").grid(row=0, column=0, sticky="w")
        self.cb_mat_a = ttk.Combobox(mat_group, values=list(MATERIAL_PHYSICS.keys()), state="readonly")
        self.cb_mat_a.grid(row=1, column=0, pady=2, sticky="ew")
        self.cb_mat_a.set("pomor_bog_pine")

        ttk.Label(mat_group, text="Материал Б (Примесь):").grid(row=2, column=0, sticky="w")
        self.cb_mat_b = ttk.Combobox(mat_group, values=list(MATERIAL_PHYSICS.keys()), state="readonly")
        self.cb_mat_b.grid(row=3, column=0, pady=2, sticky="ew")
        self.cb_mat_b.set("meteoric_iron")

        ttk.Label(mat_group, text="Blend Ratio (A <-> B):").grid(row=4, column=0, sticky="w")
        self.sl_blend = tk.Scale(mat_group, from_=0, to=100, orient=tk.HORIZONTAL, resolution=1, showvalue=True, highlightthickness=0)
        self.sl_blend.grid(row=5, column=0, pady=2, sticky="ew")
        self.sl_blend.set(0)

        # --- БЛОК 2: РЕЖИМ РАБОТЫ ---
        mode_group = ttk.LabelFrame(right_frame, text=" Режим Интеграции ", padding=10)
        mode_group.grid(row=1, column=0, pady=5, sticky="ew")

        self.mode_var = tk.StringVar(value="Symbiosis")
        r1 = ttk.Radiobutton(mode_group, text="Symbiosis (HPSS Вскрытие + Тактильность)", variable=self.mode_var, value="Symbiosis")
        r2 = ttk.Radiobutton(mode_group, text="Exciter (Сэмпл как молоточек)", variable=self.mode_var, value="Exciter")
        r1.grid(row=0, column=0, sticky="w", pady=2)
        r2.grid(row=1, column=0, sticky="w", pady=2)

        # --- БЛОК 3: ТАКТИЛЬНЫЕ ПАРАМЕТРЫ И MIX ---
        tact_group = ttk.LabelFrame(right_frame, text=" Динамика & Микшер ", padding=10)
        tact_group.grid(row=2, column=0, pady=5, sticky="ew")
        tact_group.columnconfigure(0, weight=1)

        ttk.Label(tact_group, text="Strike Force (Сила удара):").grid(row=0, column=0, sticky="w")
        self.sl_force = tk.Scale(tact_group, from_=1, to=200, orient=tk.HORIZONTAL, resolution=1, highlightthickness=0)
        self.sl_force.grid(row=1, column=0, pady=2, sticky="ew")
        self.sl_force.set(100)

        ttk.Label(tact_group, text="Fatness (Ламповое уплотнение):").grid(row=2, column=0, sticky="w")
        self.sl_fatness = tk.Scale(tact_group, from_=0, to=100, orient=tk.HORIZONTAL, resolution=1, highlightthickness=0)
        self.sl_fatness.grid(row=3, column=0, pady=2, sticky="ew")
        self.sl_fatness.set(20)

        # НАШ НОВЫЙ FLAT MIXЕР!
        ttk.Label(tact_group, text="Dry/Wet (Flat Mix):").grid(row=4, column=0, sticky="w")
        self.sl_mix = tk.Scale(tact_group, from_=0, to=100, orient=tk.HORIZONTAL, resolution=1, highlightthickness=0)
        self.sl_mix.grid(row=5, column=0, pady=2, sticky="ew")
        self.sl_mix.set(100) # По дефолту 100% мокрый (материал)

        # --- БЛОК 4: ПРЕВЬЮ И УПРАВЛЕНИЕ ---
        prev_frame = ttk.Frame(right_frame, padding=10)
        prev_frame.grid(row=3, column=0, pady=10, sticky="ew")
        prev_frame.columnconfigure((0, 1, 2), weight=1)

        btn_apply = ttk.Button(prev_frame, text="🧪 Применить", command=self.process_current_preview)
        btn_play = ttk.Button(prev_frame, text="▶️ Слушать", command=self.play_mutated)
        btn_stop = ttk.Button(prev_frame, text="⏹ Стоп", command=stop_preview)

        btn_apply.grid(row=0, column=0, padx=2, sticky="ew")
        btn_play.grid(row=0, column=1, padx=2, sticky="ew")
        btn_stop.grid(row=0, column=2, padx=2, sticky="ew")

    def load_files(self):
        files = filedialog.askopenfilenames(title="Выбрать сэмплы", filetypes=[("Audio Files", "*.wav *.aiff")])
        if files:
            self.add_files_to_list(files)

    def on_files_dropped(self, event):
        files = self.tk.splitlist(event.data)
        valid_files = [f for f in files if f.lower().endswith(('.wav', '.aiff', '.flac'))]
        if valid_files:
            self.add_files_to_list(valid_files)

    def add_files_to_list(self, new_files):
        for f in new_files:
            if f not in self.files:
                self.files.append(f)
                self.file_list.insert(tk.END, os.path.basename(f))

    def on_file_select(self, event):
        self.process_current_preview()

    def process_current_preview(self):
        selection = self.file_list.curselection()
        if not selection: return
        row = selection[0]
        
        mat_a = self.cb_mat_a.get()
        mat_b = self.cb_mat_b.get()
        blend = self.sl_blend.get() / 100.0
        mode = self.mode_var.get()
        force = self.sl_force.get() / 100.0
        fat = self.sl_fatness.get() / 100.0
        mix = self.sl_mix.get() / 100.0
        
        print(f"🔥 Рендер превью: {mat_a} + {mat_b} ({blend*100}%), Режим: {mode}, Mix: {mix*100}%")
        self.current_processed, self.current_sr = process_hybrid_material(
            self.files[row], mat_a, mat_b, blend, mode, force, fat, mix
        )
        self.play_mutated()

    def play_mutated(self):
        if self.current_processed is not None:
            play_preview(self.current_processed, self.current_sr)

    def render_batch(self):
        if not self.files: return
        out_dir = filedialog.askdirectory(title="Куда сохранить артефакты?")
        if not out_dir: return
        
        mat_a = self.cb_mat_a.get()
        mat_b = self.cb_mat_b.get()
        blend = self.sl_blend.get() / 100.0
        mode = self.mode_var.get()
        force = self.sl_force.get() / 100.0
        fat = self.sl_fatness.get() / 100.0
        mix = self.sl_mix.get() / 100.0
        
        batch_process(self.files, out_dir, mat_a, mat_b, blend, mode, force, fat, mix)
        print("✅ Массовая трансмутация завершена!")