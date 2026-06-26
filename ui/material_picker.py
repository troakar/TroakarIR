"""
Гибкий диалог выбора материала с группировкой по категориям.
Использует tkinter, читает MATERIAL_PHYSICS и MATERIAL_CATEGORIES.
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Tuple

# Импорты ваших данных (пути адаптируйте под свою структуру)
from config.materials import MATERIAL_PHYSICS, MATERIAL_CATEGORIES


class MaterialPickerDialog(tk.Toplevel):
    """
    Модальное окно выбора материала.
    Возвращает ключ материала (str) или None.
    """
    def __init__(self, parent, materials: Dict, categories: Dict):
        super().__init__(parent)
        self.title("Выбор материала")
        self.geometry("700x520")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.materials = materials
        self.categories = categories
        self.result = None

        # Инициализируем/подстраиваем стили для диалогового окна
        self._setup_dialog_styles()

        self._create_widgets()
        self._populate_categories()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.wait_window(self)

    def _setup_dialog_styles(self):
        """Настройка стилей, чтобы окно соответствовало общей теме приложения."""
        style = ttk.Style(self)
        
        # Цвета заголовков (под золото из вашего скриншота)
        style.configure(
            "Category.TLabel", 
            font=("Segoe UI", 11, "bold"), 
            foreground="#ffb700"
        )
        # Стиль для описания материалов
        style.configure(
            "Description.TLabel", 
            font=("Segoe UI", 9, "italic"), 
            foreground="#cccccc",
            wraplength=450
        )

    def _create_widgets(self):
        # Основной контейнер
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Общие параметры оформления списков (под темную тему приложения)
        listbox_style = {
            "bg": "#242424",
            "fg": "#ffffff",
            "selectbackground": "#ffb700",  # Золотистый фокус при выборе
            "selectforeground": "#121212",
            "font": ("Segoe UI", 10),
            "borderwidth": 1,
            "relief": "solid",
            "highlightthickness": 0,
            "activestyle": "none"
        }

        # Левая панель: категории
        left_frame = ttk.Frame(main_frame, width=220)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)

        ttk.Label(left_frame, text="Категории", style="Category.TLabel").pack(anchor=tk.W, pady=(0, 5))

        # Применяем единый стиль для списка категорий
        self.category_listbox = tk.Listbox(left_frame, **listbox_style)
        self.category_listbox.pack(fill=tk.BOTH, expand=True)
        self.category_listbox.bind('<<ListboxSelect>>', self._on_category_select)

        # Правая панель: материалы
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(right_frame, text="Материалы", style="Category.TLabel").pack(anchor=tk.W, pady=(0, 5))

        # Применяем тот же стиль для списка материалов
        self.material_listbox = tk.Listbox(right_frame, **listbox_style)
        self.material_listbox.pack(fill=tk.BOTH, expand=True)
        self.material_listbox.bind('<<ListboxSelect>>', self._on_material_select)

        # Панель описания
        desc_frame = ttk.Frame(right_frame, height=60)
        desc_frame.pack(fill=tk.X, pady=(10, 0))
        desc_frame.pack_propagate(False)

        self.desc_label = ttk.Label(desc_frame, text="", style="Description.TLabel")
        self.desc_label.pack(anchor=tk.W, fill=tk.BOTH, expand=True)

        # Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Выбрать", command=self._on_select).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self._on_close).pack(side=tk.RIGHT)

    def _populate_categories(self):
        """Заполняем список категорий уникальными значениями из MATERIAL_PHYSICS."""
        seen = set()
        for mat_key, mat_data in self.materials.items():
            cat = mat_data.get("category", "other")
            if cat not in seen:
                cat_display = self.categories.get(cat, cat.capitalize())
                self.category_listbox.insert(tk.END, cat_display)
                seen.add(cat)
        if self.category_listbox.size() > 0:
            self.category_listbox.selection_set(0)
            self._on_category_select(None)

    def _on_category_select(self, event):
        """При выборе категории заполняем правый список материалами."""
        selection = self.category_listbox.curselection()
        if not selection:
            return
        cat_display = self.category_listbox.get(selection[0])

        # Находим ключ категории по отображаемому имени
        cat_key = None
        for k, v in self.categories.items():
            if v == cat_display:
                cat_key = k
                break

        if cat_key is None:
            return

        self.material_listbox.delete(0, tk.END)
        self._current_materials = []

        for mat_key, mat_data in self.materials.items():
            if mat_data.get("category") == cat_key:
                name = mat_data.get("name", mat_key)
                self.material_listbox.insert(tk.END, name)
                self._current_materials.append((mat_key, mat_data))

        if self.material_listbox.size() > 0:
            self.material_listbox.selection_set(0)
            self._on_material_select(None)

    def _on_material_select(self, event):
        """Отображаем описание выбранного материала."""
        selection = self.material_listbox.curselection()
        if not selection:
            self.desc_label.config(text="")
            return
        idx = selection[0]
        _, mat_data = self._current_materials[idx]
        desc = mat_data.get("description", "Нет описания")
        self.desc_label.config(text=desc)

    def _on_select(self):
        """Подтверждение выбора."""
        selection = self.material_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        mat_key, _ = self._current_materials[idx]
        self.result = mat_key
        self.destroy()

    def _on_close(self):
        self.result = None
        self.destroy()

    @staticmethod
    def ask_material(parent=None,
                     materials: Dict = MATERIAL_PHYSICS,
                     categories: Dict = MATERIAL_CATEGORIES) -> Optional[str]:
        """
        Статический метод для быстрого вызова диалога.
        Возвращает ключ материала или None.
        """
        is_temp_parent = False
        if parent is None:
            parent = tk.Tk()
            parent.withdraw()  # Скрываем временное главное окно
            is_temp_parent = True
            
        dialog = MaterialPickerDialog(parent, materials, categories)
        
        # Уничтожаем parent ТОЛЬКО если мы его сами создали в этой функции!
        if is_temp_parent and parent.winfo_exists():
            try:
                parent.destroy()
            except Exception:
                pass
                
        return dialog.result