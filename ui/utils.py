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
# --- END OF FILE ui/utils.py ---
