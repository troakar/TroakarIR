import tkinter as tk
from tkinter import ttk

from ui.tab_acoustic import AcousticTab
from ui.tab_percussion import PercussionTab
from ui.tab_taichi import TaichiTab

class IRGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Troakar Lab Engine")
        self.root.geometry("640x700")
        self.root.minsize(1200, 660)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.main_frame = ttk.Frame(root, padding="12")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Готово к генерации IR")
        self.build_notebook()
        self.build_status_bar()

    def build_notebook(self):
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.acoustic_tab = AcousticTab(self.notebook, status_var=self.status_var)
        self.percussion_tab = PercussionTab(self.notebook, status_var=self.status_var)
        self.tab_taichi = TaichiTab(self.notebook, self.status_var)

        self.notebook.add(self.acoustic_tab, text="Акустика")
        self.notebook.add(self.percussion_tab, text="Ударные")
        self.notebook.add(self.tab_taichi, text="Taichi FDTD Лаборатория")

    def build_status_bar(self):
        status_frame = ttk.Frame(self.main_frame)
        status_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, font=("Arial", 9), foreground="gray")
        self.status_label.grid(row=0, column=0, sticky="w")
