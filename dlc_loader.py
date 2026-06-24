# dlc_loader.py
import os
import sys
import importlib
import logging

logger = logging.getLogger("Troakar.DLCLoader")

def discover_and_load_dlcs(parent_widget, main_app_ref):
    """
    Сканирует папку 'dlc/', загружает плагины и возвращает список виджетов (вкладок).
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dlc_dir = os.path.join(base_dir, "dlc")
    project_dir = base_dir
    dlc_tabs = []

    if not os.path.exists(dlc_dir):
        os.makedirs(dlc_dir)
        logger.info("Папка 'dlc/' создана.")
        return dlc_tabs

    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    if dlc_dir not in sys.path:
        sys.path.insert(0, dlc_dir)

    for item in os.listdir(dlc_dir):
        item_path = os.path.join(dlc_dir, item)
        if os.path.isdir(item_path) and not item.startswith("__"):
            manifest_path = os.path.join(item_path, "manifest.py")
            if os.path.exists(manifest_path):
                try:
                    # Динамический импорт манифеста
                    spec = importlib.util.spec_from_file_location(f"{item}.manifest", manifest_path)
                    manifest_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(manifest_module)
                    
                    metadata = manifest_module.DLC_MANIFEST
                    logger.info(f"Обнаружен DLC: {metadata['name']} v{metadata['version']} от {metadata['author']}")

                    # Импорт графического интерфейса плагина
                    gui_path = os.path.join(item_path, metadata["gui_entry_file"])
                    if item_path not in sys.path:
                        sys.path.insert(0, item_path)
                    spec_gui = importlib.util.spec_from_file_location(f"{item}.gui", gui_path)
                    gui_module = importlib.util.module_from_spec(spec_gui)
                    spec_gui.loader.exec_module(gui_module)

                    # Получаем класс вкладки
                    tab_class = getattr(gui_module, metadata["gui_class_name"])
                    
                    # Создаем инстанс вкладки, передавая родительский контейнер и ссылку на главное приложение
                    tab_instance = tab_class(parent_widget, main_app_ref)
                    dlc_tabs.append((metadata["name"], tab_instance))
                    logger.info(f"DLC '{metadata['name']}' успешно инициализирован.")

                except Exception as e:
                    logger.error(f"Не удалось загрузить DLC в папке '{item}': {e}", exc_info=True)

    return dlc_tabs