# --- START OF FILE ui/utils.py ---
def build_category_dict(db, cat_ref=None):
    """Собирает базу в словарь по категориям для Combobox"""
    categories = {}
    for key, data in db.items():
        raw_cat_id = data.get("category", "unknown")
        display_name = cat_ref.get(raw_cat_id, "❓ Разное") if cat_ref else "Барабаны"
        if display_name not in categories:
            categories[display_name] = []
        categories[display_name].append((key, data["name"]))
    for cat in categories:
        categories[cat] = sorted(categories[cat], key=lambda x: x[1])
    return dict(sorted(categories.items()))


def format_material_display(key, db):
    """Форматирует один материал: 'Русское название [key]'"""
    data = db.get(key, {})
    return f"{data.get('name', key)} [{key}]"


def format_material_list(db):
    """Формирует список для Combobox в формате 'Русское название [key]'"""
    return [f"{data['name']} [{k}]" for k, data in db.items()]


def extract_key_from_display(display_str):
    """Извлекает ключ материала из отображаемой строки 'Название [key]'"""
    if "[" in display_str and "]" in display_str:
        return display_str.split("[")[1].rstrip("]").strip()
    return display_str.strip()
# --- END OF FILE ui/utils.py ---
