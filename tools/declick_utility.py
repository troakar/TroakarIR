import os
import sys
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import scipy.io.wavfile as wav
from scipy.signal import butter, lfilter, iirnotch

def peaking_equalizer(sig, fs, f0, Q, gain_db):
    """
    Хирургический параметрический эквалайзер (Bell EQ).
    Выравнивает частотный горб, не внося фазовых искажений в соседние области.
    """
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2.0 * Q)
    A = 10.0 ** (gain_db / 40.0)
    
    b0 = 1.0 + alpha * A
    b1 = -2.0 * np.cos(w0)
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * np.cos(w0)
    a2 = 1.0 - alpha / A
    
    # Нормируем коэффициенты
    b = [b0/a0, b1/a0, b2/a0]
    a = [1.0, a1/a0, a2/a0]
    
    return lfilter(b, a, sig)

def declick_ar_model(sig, fs, ms_window=3.0, slew_factor=2.2, decrackle_strength=0.75):
    """
    Хирургический прибор спасения сэмплов от 8.4 кГц перегруза:
    1. Surgical Bell EQ (8407.2 Hz) — выравнивает резонансный горб кристаллов соли.
    2. Surgical IIR Notch (10.0 kHz) — убирает монотонный звон сетки.
    3. Band-Limited Slew Limiter (7.8k - 9.2k Hz) — скругляет жесткий клиппинг хруста.
    4. Dynamic De-crackle (7.8k - 9.2k Hz) — успокаивает мелкий высокочастотный зуд.
    """
    from scipy.ndimage import uniform_filter1d
    
    n_samples = len(sig)
    nyquist = fs / 2.0
    
    # === ШАГ 1: Surgical Bell EQ (Укрощение горба на 8407.2 Гц) ===
    # Подавляем резонанс кристаллов ровно в той зоне, что на скриншоте FabFilter
    sig = peaking_equalizer(sig, fs, f0=8407.2, Q=6.0, gain_db=-4.8)
    
    # === ШАГ 2: Режекция сетки на 10.0 кГц ===
    w0 = 10000.0 / nyquist
    if 0.0 < w0 < 1.0:
        b_notch, a_notch = iirnotch(w0, Q=30.0)
        sig = lfilter(b_notch, a_notch, sig)
    
    # === ШАГ 3: Полосовая изоляция проблемной зоны (7.8кГц - 9.2кГц) ===
    # Направляем всю мощь декликера строго в зону древесно-кристаллического перегруза
    b_bp, a_bp = butter(2, [7800.0 / nyquist, 9200.0 / nyquist], btype='bandpass')
    hf = lfilter(b_bp, a_bp, sig)
    lf = sig - hf  # Вся остальная часть спектра (низ, середина, воздух) полностью защищена
    
    # === ШАГ 4: Slew-Rate Limiter в проблемной полосе ===
    dy = np.diff(hf)
    dy = np.concatenate(([0.0], dy))
    
    window_samples = max(3, int((ms_window / 1000.0) * fs))
    smooth_env = uniform_filter1d(np.abs(dy), size=window_samples)
    
    # Жестче лимитируем скорость, чтобы размыть клиппинг в мягкую древесину
    max_slew = np.clip(slew_factor * smooth_env, 0.0002, 1.0)
    
    cleaned_hf = hf.copy()
    for i in range(1, n_samples):
        step = cleaned_hf[i] - cleaned_hf[i-1]
        limit = max_slew[i]
        
        if np.abs(step) > limit:
            cleaned_hf[i] = cleaned_hf[i-1] + np.sign(step) * limit

    # === ШАГ 5: Dynamic De-crackle в проблемной полосе ===
    fast_samples = max(2, int(0.0015 * fs))
    slow_samples = max(10, int(0.015 * fs))
    
    instant_energy = np.abs(cleaned_hf)
    fast_env = uniform_filter1d(instant_energy, size=fast_samples)
    slow_env = uniform_filter1d(instant_energy, size=slow_samples) + 1e-9
    
    impulsiveness = fast_env / slow_env
    crackle_threshold = 2.2 # Более чувствительный порог
    gain_reduction = np.ones(n_samples)
    
    for i in range(n_samples):
        if impulsiveness[i] > crackle_threshold:
            excess = impulsiveness[i] - crackle_threshold
            reduction = 1.0 / (1.0 + excess * decrackle_strength)
            gain_reduction[i] = reduction
            
    gain_reduction = uniform_filter1d(gain_reduction, size=fast_samples)
    cleaned_hf *= gain_reduction
            
    return lf + cleaned_hf, {"total_clicks": 1, "frames_with_clicks": 1}

class DeclickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Surgical HF De-Harsher Utility")
        self.root.geometry("520x380")
        self.files = []

        main = ttk.Frame(root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="Выбранные сэмплы для спасения:").pack(anchor=tk.W)

        self.listbox = tk.Listbox(main, selectmode=tk.EXTENDED, height=14)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(btn_frame, text="Добавить файлы...", command=self.add_files).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Удалить выбранное", command=self.remove_selected).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Очистить все", command=self.clear_all).pack(side=tk.LEFT)

        self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main, text="Перезаписывать исходные файлы (иначе добавить '_declick')", variable=self.overwrite_var).pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(main, text="Применить хирургический декликер", command=self.process).pack(fill=tk.X)
        ttk.Button(main, text="Выход", command=root.quit).pack(fill=tk.X, pady=(6, 0))

        self.status_var = tk.StringVar(value="Готов к работе")
        ttk.Label(main, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, pady=(10, 0))

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Выберите WAV-файлы для очистки",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")]
        )
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                self.listbox.insert(tk.END, p)

    def remove_selected(self):
        for i in sorted(self.listbox.curselection(), reverse=True):
            idx = self.listbox.index(i)
            self.listbox.delete(i)
            del self.files[idx]

    def clear_all(self):
        self.listbox.delete(0, tk.END)
        self.files.clear()

    def process(self):
        overwrite = self.overwrite_var.get()
        total = len(self.files)
        if total == 0:
            messagebox.showwarning("Внимание", "Список файлов пуст.")
            return

        error_files = []
        summary_lines = []
        summary_lines.append(f"Успешно обработано файлов: {total}")
        summary_lines.append("-" * 52)

        for count, path in enumerate(self.files, start=1):
            self.status_var.set(f"Обработка {count} из {total}: {os.path.basename(path)}")
            self.root.update()
            try:
                fs, data = wav.read(path)
                original_dtype = data.dtype
                
                # Автоматическая адаптация под битность (16, 24, 32 bit)
                if np.issubdtype(original_dtype, np.integer):
                    if original_dtype == np.int16:
                        scale = 32767.0
                    elif original_dtype == np.int32:
                        scale = 2147483647.0
                    else:
                        scale = float(np.iinfo(original_dtype).max)
                    sig_norm = data.astype(np.float32) / scale
                else:
                    sig_norm = data.astype(np.float32)
                    scale = 1.0

                # Поканальный Stereo-процессинг
                if sig_norm.ndim > 1:
                    num_channels = sig_norm.shape[1]
                    cleaned_channels = []
                    for ch in range(num_channels):
                        ch_cleaned, _ = declick_ar_model(sig_norm[:, ch], fs)
                        cleaned_channels.append(ch_cleaned)
                    cleaned = np.column_stack(cleaned_channels)
                else:
                    cleaned, _ = declick_ar_model(sig_norm, fs)

                # Восстановление оригинальной разрядности
                if np.issubdtype(original_dtype, np.integer):
                    out = np.clip(cleaned, -1.0, 1.0)
                    out = (out * scale).astype(original_dtype)
                else:
                    out = cleaned.astype(original_dtype)

                if overwrite:
                    out_path = path
                else:
                    base, ext = os.path.splitext(path)
                    out_path = f"{base}_declick{ext}"

                wav.write(out_path, fs, out)
                summary_lines.append(f"{count}. {os.path.basename(path)} -> Очищен (Stereo сохранено)")
            except Exception as e:
                error_files.append((path, str(e)))
                summary_lines.append(f"{count}. {os.path.basename(path)} -> ОШИБКА: {e}")

        self.status_var.set("Обработка завершена.")
        summary_text = "\n".join(summary_lines)
        if error_files:
            msg = "Часть файлов обработана с ошибками:\n\n" + "\n".join(f"{p}: {e}" for p, e in error_files)
            messagebox.showerror("Готово с замечаниями", msg)
        else:
            messagebox.showinfo("Операция завершена", summary_text)

if __name__ == "__main__":
    root = tk.Tk()
    app = DeclickerApp(root)
    root.mainloop()