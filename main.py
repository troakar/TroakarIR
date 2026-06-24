# main.py
import logging
import tkinter as tk
from tkinter import ttk
from ui.gui import IRGeneratorApp
from dlc_loader import discover_and_load_dlcs

def find_all_notebooks(widget):
    """
    Рекурсивно сканирует дерево виджетов Tkinter в поисках панелей вкладок (ttk.Notebook).
    Это позволяет найти панель, даже если мы не знаем точное имя переменной.
    """
    notebooks = []
    if isinstance(widget, ttk.Notebook):
        notebooks.append(widget)
    try:
        for child in widget.winfo_children():
            notebooks.extend(find_all_notebooks(child))
    except Exception:
        pass
    return notebooks

def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("troakar_debug.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("Troakar Lab Engine starting...")
    from tkinterdnd2 import TkinterDnD
    root = TkinterDnD.Tk()
    root.title("Troakar Lab - Physical Modeling Engine")
    
    style = ttk.Style(root)
    style.theme_use('clam')
    
    # Запуск оригинального интерфейса
    app = IRGeneratorApp(root)
    
    logger.info("Сканирование DLC-директории...")
    
    # 1. Ищем панель вкладок в дереве виджетов окна
    notebooks = find_all_notebooks(root)
    
    # 2. Если дерево еще не успело полностью построиться, ищем Notebook среди атрибутов класса app
    if not notebooks:
        for attr_name, attr_val in app.__dict__.items():
            if isinstance(attr_val, ttk.Notebook):
                notebooks.append(attr_val)
                
    if notebooks:
        target_notebook = notebooks[0]
        logger.info(f"Найдена активная панель вкладок (Notebook): {target_notebook}")
        
        try:
            # Загружаем DLC и передаем ссылку на найденный Notebook
            dlc_tabs = discover_and_load_dlcs(target_notebook, app)
            for tab_name, tab_widget in dlc_tabs:
                target_notebook.add(tab_widget, text=f"📦 {tab_name}")
                logger.info(f"Монтирование DLC-вкладки '{tab_name}' в основную панель.")
        except Exception as e:
            logger.error(f"Не удалось смонтировать вкладки DLC: {e}", exc_info=True)
    else:
        logger.error(
            "Критическая ошибка: Ни в главном окне, ни в объекте IRGeneratorApp "
            "не найдена панель вкладок (ttk.Notebook). DLC некуда примонтировать!"
        )
    
    root.mainloop()

if __name__ == "__main__":
    main()