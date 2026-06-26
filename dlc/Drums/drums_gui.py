# dlc/drums/drums_gui.py
import tkinter as tk
from tkinter import ttk, messagebox
import scipy.io.wavfile as wav
import numpy as np
import os
import logging

from .drums_engine import synthesize_drum_hit
from config.materials import MATERIAL_PHYSICS
from ui.utils import format_material_display, format_material_list, extract_key_from_display

logger = logging.getLogger("Troakar.DrumsGUI")

class DrumsDLCFrame(ttk.Notebook):
    def __init__(self, parent, main_app_ref):
        super().__init__(parent)
        self.main_app = main_app_ref
        self.is_rendering = False
        self.abort_current_render = False  # Флаг для прерывания рендера
        self.mat_list = format_material_list(MATERIAL_PHYSICS)

        self.tab_builder = ttk.Frame(self, padding="6")
        self.tab_physics = ttk.Frame(self, padding="6")
        
        self.add(self.tab_builder, text="🥁 Drum Kit Builder")
        self.add(self.tab_physics, text="🪵 Материалы & Физика")

        self.setup_builder_ui()
        self.setup_physics_ui()

    def setup_builder_ui(self):
        header = ttk.Label(self.tab_builder, text="ПОЛНОЦЕННАЯ УДАРНАЯ УСТАНОВКА (Batch Render)", font=("Helvetica", 12, "bold"), foreground="#00ff96")
        header.pack(anchor=tk.W, pady=(0, 6))

        grid_frame = ttk.Frame(self.tab_builder)
        grid_frame.pack(fill=tk.X, pady=2)
        ttk.Label(grid_frame, text="Качество симуляции (Сетка / Grid):").pack(side=tk.LEFT, padx=4)
        
        self.grid_res_var = tk.StringVar(value="256")
        self.grid_combo = ttk.Combobox(grid_frame, textvariable=self.grid_res_var, values=["128", "192", "256", "384", "512"], state="readonly", width=8)
        self.grid_combo.pack(side=tk.LEFT, padx=4)

        matrix_frame = ttk.LabelFrame(self.tab_builder, text=" Элементы установки ", padding="6")
        matrix_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        
        ttk.Label(matrix_frame, text="Рендер").grid(row=0, column=0, padx=4, pady=2)
        ttk.Label(matrix_frame, text="Элемент").grid(row=0, column=1, sticky=tk.W, padx=4, pady=2)
        ttk.Label(matrix_frame, text="Нота/Тюнинг").grid(row=0, column=2, padx=4, pady=2)
        ttk.Label(matrix_frame, text="Глубина (Depth)").grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(matrix_frame, text="Ударник (Beater)").grid(row=0, column=4, padx=4, pady=2)

        self.kit_elements = {
            "kick": {"name": "Kick Drum", "note": "C1", "depth": 18.0, "beater": "felt_beater"},
            "snare": {"name": "Snare Drum", "note": "G2", "depth": 5.5, "beater": "wood_stick"},
            "tom_high": {"name": "Tom High", "note": "E3", "depth": 8.0, "beater": "wood_stick"},
            "tom_mid": {"name": "Tom Mid", "note": "C3", "depth": 10.0, "beater": "wood_stick"},
            "tom_low": {"name": "Tom Low", "note": "G2", "depth": 14.0, "beater": "wood_stick"},
            "hihat": {"name": "Hi-Hat (Closed)", "note": "F#3", "depth": 0.0, "beater": "wood_stick"},
            "cymbal_ride": {"name": "Ride Cymbal", "note": "D#4", "depth": 0.0, "beater": "nylon_stick"},
            "cymbal_crash": {"name": "Crash Cymbal", "note": "C#4", "depth": 0.0, "beater": "wood_stick"}
        }

        self.kit_vars = {}
        row = 1
        for key, data in self.kit_elements.items():
            var_active = tk.BooleanVar(value=(key in ["kick", "snare", "hihat"]))
            var_note = tk.StringVar(value=data["note"])
            var_depth = tk.DoubleVar(value=data["depth"])
            var_beater = tk.StringVar(value=data["beater"])
            
            self.kit_vars[key] = {
                "active": var_active, "note": var_note, "depth": var_depth, "beater": var_beater
            }
            
            ttk.Checkbutton(matrix_frame, variable=var_active).grid(row=row, column=0)
            ttk.Label(matrix_frame, text=data["name"]).grid(row=row, column=1, sticky=tk.W)
            
            if "cymbal" not in key and "hihat" not in key:
                ttk.Entry(matrix_frame, textvariable=var_note, width=5).grid(row=row, column=2, padx=4)
                ttk.Entry(matrix_frame, textvariable=var_depth, width=5).grid(row=row, column=3, padx=4)
            else:
                ttk.Label(matrix_frame, text=data["note"]).grid(row=row, column=2, padx=4)
                ttk.Label(matrix_frame, text="N/A").grid(row=row, column=3, padx=4)
                
            ttk.Combobox(matrix_frame, textvariable=var_beater, values=["wood_stick", "nylon_stick", "felt_beater"], state="readonly", width=12).grid(row=row, column=4, padx=4)
            row += 1

        export_frame = ttk.LabelFrame(self.tab_builder, text=" Настройки Экспорта ", padding="6")
        export_frame.pack(fill=tk.X, pady=4)
        
        ttk.Label(export_frame, text="Слоев Velocity:").grid(row=0, column=0, sticky=tk.W, padx=4)
        self.vel_layers = ttk.Combobox(export_frame, values=["1 (127)", "3 (64, 96, 127)", "5 (Multilayer)"], state="readonly", width=15)
        self.vel_layers.set("3 (64, 96, 127)")
        self.vel_layers.grid(row=0, column=1, padx=4)
        
        ttk.Label(export_frame, text="Round Robins (RR):").grid(row=0, column=2, sticky=tk.W, padx=12)
        self.rr_amount = ttk.Combobox(export_frame, values=["1", "2", "3", "5"], state="readonly", width=5)
        self.rr_amount.set("2")
        self.rr_amount.grid(row=0, column=3, padx=4)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.tab_builder, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=6)

        btn_frame = ttk.Frame(self.tab_builder)
        btn_frame.pack(fill=tk.X, pady=4)
        
        self.btn_test = ttk.Button(btn_frame, text="👁 ТЕСТ SNARE (Визуализация)", command=self.generate_single_test)
        self.btn_test.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        self.btn_abort = ttk.Button(btn_frame, text="🛑 ПРЕРВАТЬ (Оставить хвост)", command=self.abort_render, state=tk.DISABLED)
        self.btn_abort.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        self.btn_render = ttk.Button(btn_frame, text="🚀 СГЕНЕРИРОВАТЬ DRUM KIT", command=self.start_batch_render)
        self.btn_render.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=2)

    def setup_physics_ui(self):
        mat_frame = ttk.LabelFrame(self.tab_physics, text=" Выбор материалов ", padding="6")
        mat_frame.pack(fill=tk.X, pady=4)

        ttk.Label(mat_frame, text="Пластик (Heads):").grid(row=0, column=0, sticky=tk.W, padx=4)
        self.head_mat = ttk.Combobox(mat_frame, values=self.mat_list, state="readonly", width=30)
        self.head_mat.set(format_material_display("animal_skin", MATERIAL_PHYSICS))
        self.head_mat.grid(row=0, column=1, padx=4, pady=2)

        ttk.Label(mat_frame, text="Кадушка (Shells):").grid(row=1, column=0, sticky=tk.W, padx=4)
        self.shell_mat = ttk.Combobox(mat_frame, values=self.mat_list, state="readonly", width=30)
        self.shell_mat.set(format_material_display("maple", MATERIAL_PHYSICS))
        self.shell_mat.grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(mat_frame, text="Тарелки (Cymbals):").grid(row=2, column=0, sticky=tk.W, padx=4)
        self.cym_mat = ttk.Combobox(mat_frame, values=self.mat_list, state="readonly", width=30)
        self.cym_mat.set(format_material_display("bronze", MATERIAL_PHYSICS))
        self.cym_mat.grid(row=2, column=1, padx=4, pady=2)

        tweak_frame = ttk.LabelFrame(self.tab_physics, text=" Глобальный Твикинг ", padding="6")
        tweak_frame.pack(fill=tk.X, pady=4)

        ttk.Label(tweak_frame, text="Демпфирование (Muffling):").grid(row=0, column=0, sticky=tk.W, padx=4)
        self.muff_scale = ttk.Scale(tweak_frame, from_=0.0, to=1.0, value=0.15)
        self.muff_scale.grid(row=0, column=1, sticky=tk.EW, padx=4)

        ttk.Label(tweak_frame, text="Натяжение пружин Snare:").grid(row=1, column=0, sticky=tk.W, padx=4)
        self.snare_scale = ttk.Scale(tweak_frame, from_=0.0, to=1.0, value=0.5)
        self.snare_scale.grid(row=1, column=1, sticky=tk.EW, padx=4)
        
        ttk.Label(tweak_frame, text="Тактильный Хруст/Песок:").grid(row=2, column=0, sticky=tk.W, padx=4)
        self.tactile_scale = ttk.Scale(tweak_frame, from_=0.0, to=2.0, value=0.8)
        self.tactile_scale.grid(row=2, column=1, sticky=tk.EW, padx=4)

        self.use_bells_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tweak_frame, text="Добавить бубенцы (Tambourine Jingles) к Snare/Hihat", variable=self.use_bells_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=4)
        
        tweak_frame.columnconfigure(1, weight=1)

    def abort_render(self):
        """Вызывается при нажатии на кнопку ПРЕРВАТЬ."""
        self.abort_current_render = True
        logger.info("Пользователь запросил прерывание FDTD-цикла. Идет обработка хвоста...")
        self.btn_abort.config(state=tk.DISABLED, text="Прерывание...")

    def generate_single_test(self):
        if self.is_rendering: return
        self.is_rendering = True
        self.abort_current_render = False
        
        self.btn_test.config(state=tk.DISABLED)
        self.btn_render.config(state=tk.DISABLED)
        self.btn_abort.config(state=tk.NORMAL, text="🛑 ПРЕРВАТЬ (Оставить хвост)")
        self.progress_var.set(0)

        try:
            def step_cb(step, num_steps):
                self.progress_var.set((step / num_steps) * 100)
                self.update() 
                if self.abort_current_render:
                    return False # Сигнал остановки в FDTD
                return True

            grid_res = int(self.grid_res_var.get())
            snare_data = self.kit_vars.get("snare")
            
            note = snare_data["note"].get() if snare_data else "G2"
            beater = snare_data["beater"].get() if snare_data else "wood_stick"
            depth = snare_data["depth"].get() if snare_data else 5.5

            audio = synthesize_drum_hit(
                drum_type="snare",
                note=note,
                beater_type=beater,
                strike_force=1.0,
                head_mat_name=extract_key_from_display(self.head_mat.get()),
                shell_mat_name=extract_key_from_display(self.shell_mat.get()),
                cym_mat_name=extract_key_from_display(self.cym_mat.get()),
                shell_depth_inches=depth,
                muffling=self.muff_scale.get(),
                tactile_boost=self.tactile_scale.get(),
                snare_tension=self.snare_scale.get(),
                use_bells=self.use_bells_var.get(),
                duration=1.5,
                N_grid=grid_res,
                show_gui=True, 
                yield_cb=step_cb
            )

            out_dir = "@DrumKit_Renders"
            if not os.path.exists(out_dir): os.makedirs(out_dir)
            
            suffix = "_Aborted" if self.abort_current_render else ""
            out_path = os.path.join(out_dir, f"Test_Snare{suffix}.wav")
            wav.write(out_path, 44100, audio.astype(np.float32))
            
            msg = "Сэмпл (с прерванным хвостом) сохранен" if self.abort_current_render else "Сэмпл сохранен"
            messagebox.showinfo("Готово!", f"{msg}: {out_path}")

        except Exception as e:
            logger.error(f"Ошибка рендера: {e}", exc_info=True)
            error_msg = str(e)
            self.after(0, lambda err=error_msg: messagebox.showerror("Ошибка", f"Сбой: {err}"))
        finally:
            self.is_rendering = False
            self.abort_current_render = False
            self.progress_var.set(100)
            self.btn_test.config(state=tk.NORMAL)
            self.btn_render.config(state=tk.NORMAL)
            self.btn_abort.config(state=tk.DISABLED, text="🛑 ПРЕРВАТЬ (Оставить хвост)")

    def start_batch_render(self):
        if self.is_rendering: return
        self.is_rendering = True
        self.abort_current_render = False
        
        self.btn_render.config(state=tk.DISABLED, text="Идет Рендеринг (Не закрывайте окно)...")
        self.btn_test.config(state=tk.DISABLED)
        self.btn_abort.config(state=tk.NORMAL, text="🛑 ПРЕРВАТЬ (Перейти к следующему)")
        self.progress_var.set(0)
        
        self.run_batch_task()

    def run_batch_task(self):
        try:
            out_dir = "@DrumKit_Renders"
            if not os.path.exists(out_dir): os.makedirs(out_dir)

            v_mode = self.vel_layers.get()
            if "1" in v_mode: velocities = [127]
            elif "3" in v_mode: velocities = [64, 96, 127]
            else: velocities = [32, 64, 90, 110, 127]
            
            rr_count = int(self.rr_amount.get())
            grid_res = int(self.grid_res_var.get())
            
            active_pieces = {k: v for k, v in self.kit_vars.items() if v["active"].get()}
            if not active_pieces:
                messagebox.showwarning("Внимание", "Не выбрано ни одного барабана для рендера!")
                return

            total_files = len(active_pieces) * len(velocities) * rr_count
            current_file = 0

            for piece_key, v_data in active_pieces.items():
                d_type = "kick" if "kick" in piece_key else \
                         "snare" if "snare" in piece_key else \
                         "cymbal_ride" if "ride" in piece_key else \
                         "cymbal_crash" if "crash" in piece_key else \
                         "hihat" if "hihat" in piece_key else "tom"
                
                note = v_data["note"].get()
                depth = v_data["depth"].get()
                beater = v_data["beater"].get()
                duration = 2.5 if "cymbal" in d_type or "ride" in piece_key or "crash" in piece_key else 1.2
                
                for vel in velocities:
                    for rr in range(1, rr_count + 1):
                        self.abort_current_render = False # Сбрасываем флаг для каждого нового файла
                        force = vel / 127.0
                        
                        if rr > 1:
                            force = np.clip(force + np.random.uniform(-0.05, 0.05), 0.1, 1.0)
                        
                        def step_cb(step, num_steps):
                            base_pct = (current_file / total_files) * 100
                            file_pct = (step / num_steps) * (100 / total_files)
                            self.progress_var.set(base_pct + file_pct)
                            self.update()
                            if self.abort_current_render:
                                return False # Заглушает FDTD и переходит к пост-обработке
                            return True
                        
                        audio = synthesize_drum_hit(
                            drum_type=d_type,
                            note=note,
                            beater_type=beater,
                            strike_force=force,
                            head_mat_name=extract_key_from_display(self.head_mat.get()),
                            shell_mat_name=extract_key_from_display(self.shell_mat.get()),
                            cym_mat_name=extract_key_from_display(self.cym_mat.get()),
                            shell_depth_inches=depth,
                            muffling=self.muff_scale.get(),
                            tactile_boost=self.tactile_scale.get(),
                            snare_tension=self.snare_scale.get(),
                            use_bells=self.use_bells_var.get() if d_type in ["snare", "hihat"] else False,
                            bell_mix=0.3,
                            duration=duration,
                            N_grid=grid_res,
                            show_gui=False,
                            yield_cb=step_cb
                        )
                        
                        suffix = "_Aborted" if self.abort_current_render else ""
                        filename = f"Kit_{self.kit_elements[piece_key]['name'].replace(' ', '')}_{note}_v{vel}_rr{rr}{suffix}.wav"
                        out_path = os.path.join(out_dir, filename)
                        wav.write(out_path, 44100, audio.astype(np.float32))
                        
                        current_file += 1
                        
                        # Возвращаем название кнопки в нормальное состояние после обработки "прерванного" хвоста
                        self.btn_abort.config(state=tk.NORMAL, text="🛑 ПРЕРВАТЬ (Перейти к следующему)")

            self.progress_var.set(100)
            logger.info("Установка успешно сгенерирована!")
            messagebox.showinfo("Готово!", f"Установка отрендерена в {out_dir}")

        except Exception as e:
            logger.error(f"Ошибка пакетного рендера: {e}", exc_info=True)
            error_msg = str(e)
            self.after(0, lambda err=error_msg: messagebox.showerror("Ошибка", f"Произошел сбой: {err}"))
            
        finally:
            self.is_rendering = False
            self.btn_render.config(state=tk.NORMAL, text="🚀 СГЕНЕРИРОВАТЬ ВЫБРАННЫЙ DRUM KIT")
            self.btn_test.config(state=tk.NORMAL)
            self.btn_abort.config(state=tk.DISABLED, text="🛑 ПРЕРВАТЬ (Оставить хвост)")