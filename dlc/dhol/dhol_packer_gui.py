# dlc/dhol/dhol_packer_gui.py
import os
import re
import glob
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import scipy.io.wavfile as wav
import logging

logger = logging.getLogger("TheHall.Packer")

class DholPackerFrame(ttk.Frame):
    def __init__(self, parent, main_app_ref=None):
        super().__init__(parent)
        self.main_app = main_app_ref
        self.setup_ui()

    def setup_ui(self):
        container = ttk.Frame(self, padding="15")
        container.pack(fill=tk.BOTH, expand=True)

        # Заголовок
        header = ttk.Label(container, text="📦 УПАКОВЩИК СЭМПЛОВ (Bitwig .multisample)", font=("Helvetica", 12, "bold"), foreground="#00ff96")
        header.pack(anchor=tk.W, pady=(0, 15))

        # --- БЛОК НАСТРОЕК ДИРЕКТОРИЙ ---
        dirs_frame = ttk.LabelFrame(container, text=" Директории ", padding="10")
        dirs_frame.pack(fill=tk.X, pady=5)

        # Входная папка
        ttk.Label(dirs_frame, text="Папка с WAV файлами:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.input_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "Dhol_Samples"))
        self.entry_input = ttk.Entry(dirs_frame, textvariable=self.input_dir_var, width=50)
        self.entry_input.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(dirs_frame, text="Обзор...", command=self.browse_input).grid(row=0, column=2, pady=5)

        # Выходная папка
        ttk.Label(dirs_frame, text="Папка для .multisample:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "Troakar_Multisamples"))
        self.entry_output = ttk.Entry(dirs_frame, textvariable=self.output_dir_var, width=50)
        self.entry_output.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Button(dirs_frame, text="Обзор...", command=self.browse_output).grid(row=1, column=2, pady=5)

        dirs_frame.columnconfigure(1, weight=1)

        # --- БЛОК ДОП. НАСТРОЕК ---
        opts_frame = ttk.LabelFrame(container, text=" Настройки сборки ", padding="10")
        opts_frame.pack(fill=tk.X, pady=5)

        ttk.Label(opts_frame, text="Суффикс инструмента (опционально):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.custom_name_var = tk.StringVar(value="")
        self.entry_custom_name = ttk.Entry(opts_frame, textvariable=self.custom_name_var, width=30)
        self.entry_custom_name.grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)
        ttk.Label(opts_frame, text="Например: Dry Studio, Console Saturation", foreground="#888").grid(row=0, column=2, sticky=tk.W)

        # --- КНОПКА ЗАПУСКА ---
        self.btn_pack = ttk.Button(container, text="🚀 СФОРМИРОВАТЬ ИНСТРУМЕНТЫ (.multisample)", command=self.start_packing)
        self.btn_pack.pack(fill=tk.X, pady=15, ipady=5)

        # --- ЛОГИ ---
        log_frame = ttk.LabelFrame(container, text=" Консоль сборки ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=12, bg="#000000", fg="#00ff66", insertbackground="#00ff66", font=("Consolas", 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        logger.info(message)
        self.update()

    def browse_input(self):
        dir_path = filedialog.askdirectory(initialdir=os.getcwd(), title="Выберите папку с отрендеренными WAV")
        if dir_path:
            self.input_dir_var.set(dir_path)

    def browse_output(self):
        dir_path = filedialog.askdirectory(initialdir=os.getcwd(), title="Выберите папку для сохранения Multisamples")
        if dir_path:
            self.output_dir_var.set(dir_path)

    # --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ПАРСИНГА И ГЕНЕРАЦИИ ---
    def get_wav_frames(self, path):
        try:
            samplerate, data = wav.read(path)
            return data.shape[0] if data.ndim > 1 else len(data)
        except Exception as e:
            self.log(f" [!] Ошибка чтения {os.path.basename(path)}: {e}")
            return 0

    def note_to_midi(self, note_name: str) -> int:
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        try:
            res = re.match(r"(?P<name>[A-G]#?)(?P<octave>\d)", note_name)
            name = res.group("name")
            octave = int(res.group("octave"))
            return notes.index(name) + (octave + 1) * 12
        except Exception:
            return 60

    def parse_wav_metadata(self, filename: str):
        # Поддерживаем полные имена из dhol_gui.py: Dhol_{art}_{note}_{skin}_{shell}_v{vel}_rr{rr}.wav
        pattern_full = r"Dhol_(?P<art>.+?)_(?P<note>[A-G]#?\d)_(?P<skin>.+?)_(?P<shell>.+?)_v(?P<vel>\d+)_rr(?P<rr>\d+)\.wav"
        match = re.match(pattern_full, filename)
        if match:
            return match.groupdict()

        # Резервный короткий формат
        pattern_short = r"Dhol_(?P<art>.+?)_(?P<note>[A-G]#?\d)_v(?P<vel>\d+)_rr(?P<rr>\d+)\.wav"
        match_short = re.match(pattern_short, filename)
        if match_short:
            d = match_short.groupdict()
            d['skin'] = None
            d['shell'] = None
            return d
        return None

    def generate_multisample_xml(self, instrument_display_name, files_data):
        unique_vels = sorted(list(set(int(f["vel"]) for f in files_data)))
        n_layers = len(unique_vels)

        vel_ranges = {}
        if n_layers == 1:
            vel_ranges[unique_vels[0]] = (1, 127)
        else:
            for i, v in enumerate(unique_vels):
                low = int(round(i * 127 / n_layers)) + 1 if i > 0 else 1
                high = int(round((i + 1) * 127 / n_layers)) if i < n_layers - 1 else 127
                vel_ranges[v] = (low, high)

        samples_nodes = []
        for f in files_data:
            midi_note = self.note_to_midi(f["note"])
            v_low, v_high = vel_ranges[int(f["vel"])]
            frames = float(f["frames"])
            rr = int(f["rr"])

            has_rr = any(int(other["vel"]) == int(f["vel"]) and int(other["rr"]) != rr for other in files_data)
            z_logic = "round-robin" if has_rr else "always-play"
            rr_attr = f' round-robin="{rr}"' if z_logic == "round-robin" else ""

            node = f'   <sample file="{f["filename"]}" gain="0.00" parameter-1="0.0000" parameter-2="0.0000" parameter-3="0.0000" reverse="false" sample-start="0.000" sample-stop="{frames:.3f}" zone-logic="{z_logic}"{rr_attr}>\n'
            node += f'      <key high="127" low="0" root="{midi_note}" track="0.0000" tune="0.00"/>\n'
            node += f'      <velocity high="{v_high}" low="{v_low}"/>\n'
            node += f'      <select/>\n'
            node += f'      <loop fade="0.0000" mode="off" start="0.000" stop="{frames:.3f}"/>\n'
            node += f'   </sample>'
            samples_nodes.append(node)

        xml_body = "\n".join(samples_nodes)
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<multisample name="{instrument_display_name}">
   <generator>Troakar FDTD Engine</generator>
   <category>Percussion</category>
   <creator>Troakar</creator>
   <description/>
{xml_body}
</multisample>
"""

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
        wav_paths = glob.glob(os.path.join(src_dir, "*.wav"))
        
        if not wav_paths:
            wav_paths = glob.glob(os.path.join(src_dir, "**", "*.wav"), recursive=True)

        self.log(f"🔍 Найдено WAV файлов для анализа: {len(wav_paths)}")

        arts_db = {}
        for path in wav_paths:
            meta = self.parse_wav_metadata(os.path.basename(path))
            if meta:
                meta['fullpath'] = path
                meta['filename'] = os.path.basename(path)
                meta['frames'] = self.get_wav_frames(path)

                art_key = meta['art']
                if meta.get('skin') and meta.get('shell'):
                    art_key += f"_{meta['skin']}_{meta['shell']}"

                if art_key not in arts_db:
                    arts_db[art_key] = []
                arts_db[art_key].append(meta)

        if not arts_db:
            self.log("❌ Файлы не распознаны. Проверьте правильность имен (Dhol_Art_Note...).")
            self.btn_pack.config(state=tk.NORMAL)
            return

        self.log(f"📦 Сформировано уникальных мультисэмплов (Инструментов): {len(arts_db)}")
        self.log("-" * 50)

        for key, files in arts_db.items():
            meta = files[0]
            art_name = meta['art']

            if meta.get('skin') and meta.get('shell'):
                skin, shell = meta['skin'], meta['shell']
                suffix = f" {custom_name}" if custom_name else ""
                display_name = f"Dhol {art_name.replace('_',' ').title()} ({skin} + {shell}){suffix}"
                file_name_base = f"Dhol_{art_name.capitalize()}_{skin}_{shell}"
            else:
                display_name = f"Dhol {art_name.replace('_',' ').title()} ({custom_name or 'Custom'})"
                file_name_base = f"Dhol_{art_name.capitalize()}_{custom_name.replace(' ', '_') or 'Custom'}"

            multisample_path = os.path.join(dst_dir, f"{file_name_base}.multisample")
            self.log(f" • Сборка: {display_name} -> {os.path.basename(multisample_path)}")

            xml_content = self.generate_multisample_xml(display_name, files)

            with zipfile.ZipFile(multisample_path, 'w', zipfile.ZIP_STORED) as z:
                z.writestr("multisample.xml", xml_content)
                for f in files:
                    z.write(f['fullpath'], f['filename'])
            self.update()

        self.log("-" * 50)
        self.log(f"✅ ВСЕ ИНСТРУМЕНТЫ УПАКОВАНЫ!")
        self.log(f"Сохранено в: {dst_dir}")
        messagebox.showinfo("Готово", f"Сборка завершена!\nСохранено в: {dst_dir}")
        self.btn_pack.config(state=tk.NORMAL)
