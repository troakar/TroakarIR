# --- START OF FILE config/instruments.py ---

# === 1. ШАБЛОНЫ РЕЗОНАТОРОВ (Математические модели) ===
RESONATOR_TEMPLATES = {
    "bowed_coupled": {
        "name": "Смычковый корпус", "default_material": "spruce", "transient_click": 0.01, "has_helmholtz": True, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["A0"], "amp": 1.0, "is_air": True},
            {"f": (inst["B1_center"] - inst["B1_width"] * k_aniso) * scale, "amp": 0.8, "is_air": False},
            {"f": (inst["B1_center"] + inst["B1_width"] * k_aniso) * scale, "amp": 0.7, "is_air": False}
        ]
    },
    "drum_shell": {
        "name": "Корпус барабана", "default_material": "spruce", "transient_click": 0.70, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst.get("A0", inst.get("f0", 60.0)), "amp": 1.2, "is_air": True},
            {"f": inst["f0"] * scale * 1.00, "amp": 1.0, "is_air": False},
            {"f": inst["f0"] * scale * 1.90 * k_aniso, "amp": 0.7, "is_air": False},
            {"f": inst["f0"] * scale * 3.10, "amp": 0.4, "is_air": False}
        ]
    },
    "cymbal_plate": {
        "name": "Тарелка", "default_material": "steel", "transient_click": 0.95, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["f0"] * scale * 1.00, "amp": 1.2, "is_air": False},
            {"f": inst["f0"] * scale * 2.72, "amp": 0.8, "is_air": False},
            {"f": inst["f0"] * scale * 4.96, "amp": 0.6, "is_air": False},
            {"f": inst["f0"] * scale * 7.30, "amp": 0.4, "is_air": False},
            {"f": inst["f0"] * scale * 10.70, "amp": 0.25, "is_air": False}
        ]
    },
    "flat_braced": {
        "name": "Дека с пружинами", "default_material": "spruce", "transient_click": 0.05, "has_helmholtz": True, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["A0"], "amp": 1.2, "is_air": True},
            {"f": inst["T1"] * scale, "amp": 1.0, "is_air": False},
            {"f": inst["T2"] * scale * k_aniso, "amp": 0.6, "is_air": False},
            {"f": inst["T3"] * scale, "amp": 0.5, "is_air": False}
        ]
    },
    "stretched_membrane": {
        "name": "Мембрана", "default_material": "mylar", "transient_click": 0.99, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["f0"] * scale * 1.00, "amp": 1.5, "is_air": False},
            {"f": inst["f0"] * scale * 1.59 * k_aniso, "amp": 0.9, "is_air": False},
            {"f": inst["f0"] * scale * 2.14, "amp": 0.6, "is_air": False},
            {"f": inst["f0"] * scale * 2.30 * k_aniso, "amp": 0.4, "is_air": False},
            {"f": inst["f0"] * scale * 3.60, "amp": 0.2, "is_air": False}
        ]
    },
    "tuned_bar": {
        "name": "Настроенный брусок", "default_material": "rosewood", "transient_click": 0.80, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["f0"] * scale, "amp": 1.5, "is_air": False},
            {"f": inst["f0"] * scale * inst["ratio_harmonic_1"], "amp": 0.7, "is_air": False},
            {"f": inst["f0"] * scale * inst["ratio_harmonic_2"], "amp": 0.3, "is_air": False}
        ]
    },
    "metal_bar": {
        "name": "Вибрирующий стержень", "default_material": "steel", "transient_click": 0.95, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["f0"] * scale * 1.00, "amp": 1.0, "is_air": False},
            {"f": inst["f0"] * scale * 2.76, "amp": 0.8, "is_air": False},
            {"f": inst["f0"] * scale * 5.40, "amp": 0.6, "is_air": False},
            {"f": inst["f0"] * scale * 8.93, "amp": 0.4, "is_air": False},
            {"f": inst["f0"] * scale * 13.34, "amp": 0.2, "is_air": False}
        ]
    },
    "woodwind_bell": {
        "name": "Раструб духового инструмента", "default_material": "apricot", "transient_click": 0.85, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["F1"] * scale, "amp": 1.0, "is_air": False},
            {"f": inst["F2"] * scale, "amp": 1.4, "is_air": False}, 
            {"f": inst["F3"] * scale, "amp": 0.8, "is_air": False},
            {"f": inst["F4"] * scale, "amp": 0.5, "is_air": False}
        ]
    },
    "isotropic_plate": {
        "name": "Изотропная плита (Plate)", "default_material": "steel", "transient_click": 0.75, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [
            {"f": inst["f0"] * scale * 1.00, "amp": 1.0, "is_air": False},
            {"f": inst["f0"] * scale * 1.62 * k_aniso, "amp": 0.9, "is_air": False},
            {"f": inst["f0"] * scale * 2.13, "amp": 0.8, "is_air": False},
            {"f": inst["f0"] * scale * 2.75 * k_aniso, "amp": 0.7, "is_air": False},
            {"f": inst["f0"] * scale * 3.38, "amp": 0.6, "is_air": False},
            {"f": inst["f0"] * scale * 4.05 * k_aniso, "amp": 0.5, "is_air": False}
        ]
    },
    "space_cathedral": {
        "name": "Собор (3D Space)", "default_material": "spruce", "transient_click": 0.30, "has_helmholtz": False, "is_space": True,
        "base_size": 35.0, "modes_builder": lambda inst, scale, k_aniso: []
    },
    "space_cistern": {
        "name": "Цистерна (3D Space)", "default_material": "steel", "transient_click": 0.50, "has_helmholtz": False, "is_space": True,
        "base_size": 12.0, "modes_builder": lambda inst, scale, k_aniso: []
    },
    "ideal_medium": {
        "name": "Изотропный шумовой монолит (Lab Reference)", "default_material": "steel", "transient_click": 1.0, "has_helmholtz": False, "is_space": False,
        "modes_builder": lambda inst, scale, k_aniso: [{"f": 20.0 * (1.025 ** i), "amp": 0.5, "is_air": False} for i in range(280)]
    }
}

# === 2. КАТЕГОРИИ И ПРЕСЕТЫ УДАРНЫХ / ПЕРКУССИИ ===
PERCUSSION_CATEGORIES = {
    "drums": "🥁 Барабаны",
    "cymbals": "🔔 Тарелы и Литья",
    "metallic": "⚙️ Металлические",
    "special": "❓ Специальные",
    "lab_testing": "🔬 Лабораторные Эталоны"
}

PERCUSSION_PRESETS = {
    # --- Барабаны ---
    "kick_drum": {"category": "drums", "name": "Кик-барабан", "resonator_template": "drum_shell", "mask_image": "Drum.png", "size_m": 0.56, "low_cut": 35.0, "bridge_hill": 800.0, "f0": 60.0, "sympathetic_strings": []},
    "snare_drum": {"category": "drums", "name": "Малый барабан", "resonator_template": "drum_shell", "mask_image": "Drum.png", "size_m": 0.35, "low_cut": 120.0, "bridge_hill": 2500.0, "f0": 180.0, "sympathetic_strings": []},
    "tom_low": {"category": "drums", "name": "Том низкий", "resonator_template": "drum_shell", "mask_image": "Drum.png", "low_cut": 70.0, "bridge_hill": 1500.0, "f0": 95.0, "sympathetic_strings": []},
    "tom_mid": {"category": "drums", "name": "Том средний", "resonator_template": "drum_shell", "mask_image": "Drum.png", "low_cut": 90.0, "bridge_hill": 2000.0, "f0": 135.0, "sympathetic_strings": []},
    "tom_high": {"category": "drums", "name": "Том высокий", "resonator_template": "drum_shell", "mask_image": "Drum.png", "low_cut": 130.0, "bridge_hill": 2800.0, "f0": 200.0, "sympathetic_strings": []},

    # --- Тарелы ---
    "crash_cymbal": {"category": "cymbals", "name": "Краш-тарела", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "low_cut": 150.0, "bridge_hill": 6000.0, "f0": 400.0, "sympathetic_strings": []},
    "ride_cymbal": {"category": "cymbals", "name": "Райд-тарела", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "low_cut": 180.0, "bridge_hill": 5000.0, "f0": 350.0, "sympathetic_strings": []},
    "hi_hat": {"category": "cymbals", "name": "Хай-хэт", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "low_cut": 200.0, "bridge_hill": 4500.0, "f0": 300.0, "sympathetic_strings": []},

    # --- Металлические ---
    "gong": {"category": "metallic", "name": "Гонг", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "low_cut": 40.0, "bridge_hill": 3000.0, "f0": 120.0, "sympathetic_strings": []},
    "cowbell": {"category": "metallic", "name": "Ковбелл", "resonator_template": "tuned_bar", "mask_image": "anvil.png", "low_cut": 300.0, "bridge_hill": 3500.0, "f0": 500.0, "ratio_harmonic_1": 2.72, "ratio_harmonic_2": 4.96, "sympathetic_strings": []},
    "triangle": {"category": "metallic", "name": "Треугольник", "resonator_template": "tuned_bar", "mask_image": "triangle.png", "low_cut": 400.0, "bridge_hill": 4000.0, "f0": 650.0, "ratio_harmonic_1": 2.82, "ratio_harmonic_2": 5.12, "sympathetic_strings": []},
    "woodblock": {"category": "metallic", "name": "Вудблок", "resonator_template": "stretched_membrane", "mask_image": "coffin.png", "low_cut": 250.0, "bridge_hill": 2000.0, "f0": 380.0, "sympathetic_strings": []},
    "tuning_fork": {"category": "metallic", "name": "Камертон", "resonator_template": "tuned_bar", "mask_image": "camertone.png", "low_cut": 400.0, "bridge_hill": 4000.0, "f0": 440.0, "ratio_harmonic_1": 6.26, "ratio_harmonic_2": 17.55, "sympathetic_strings": []},

    # --- Специальные ---
    "tibetan_bowl": {"category": "special", "name": "Тибетская чаша", "resonator_template": "tuned_bar", "mask_image": "Bowl.png", "low_cut": 120.0, "bridge_hill": 2500.0, "f0": 180.0, "ratio_harmonic_1": 2.72, "ratio_harmonic_2": 4.96, "sympathetic_strings": [90.0, 135.0, 270.0]},
    "steel_drum": {"category": "special", "name": "Стальной панно", "resonator_template": "tuned_bar", "mask_image": "Waterphone.png", "low_cut": 200.0, "bridge_hill": 3500.0, "f0": 250.0, "ratio_harmonic_1": 2.50, "ratio_harmonic_2": 4.00, "sympathetic_strings": [165.0, 220.0, 330.0]},
    
    # --- Лабораторные ---
    "perfect_lab_pad": {"category": "lab_testing", "name": "Лабораторный краш-тест", "resonator_template": "ideal_medium", "low_cut": 15.0, "bridge_hill": 6000.0, "f0": 100.0, "sympathetic_strings": []}
}

# === 2. КАТЕГОРИИ И ПРЕСЕТЫ УДАРНЫХ / ПЕРКУССИИ ===
PERCUSSION_CATEGORIES = {
    "drums": "🥁 Барабаны",
    "cymbals": "🔔 Тарелы и Литья",
    "metallic": "⚙️ Металлические",
    "special": "❓ Специальные",
    "lab_testing": "🔬 Лабораторные Эталоны"
}

PERCUSSION_PRESETS = {
    # --- Барабаны ---
    "kick_drum": {"category": "drums", "name": "Кик-барабан", "resonator_template": "drum_shell", "mask_image": "Drum.png", "size_m": 0.56, "body_depth": 0.45, "low_cut": 35.0, "bridge_hill": 800.0, "f0": 60.0, "sympathetic_strings": []},
    "snare_drum": {"category": "drums", "name": "Малый барабан", "resonator_template": "drum_shell", "mask_image": "Drum.png", "size_m": 0.35, "body_depth": 0.15, "low_cut": 120.0, "bridge_hill": 2500.0, "f0": 180.0, "sympathetic_strings": []},
    "tom_low": {"category": "drums", "name": "Том низкий", "resonator_template": "drum_shell", "mask_image": "Drum.png", "body_depth": 0.35, "low_cut": 70.0, "bridge_hill": 1500.0, "f0": 95.0, "sympathetic_strings": []},
    "tom_mid": {"category": "drums", "name": "Том средний", "resonator_template": "drum_shell", "mask_image": "Drum.png", "body_depth": 0.25, "low_cut": 90.0, "bridge_hill": 2000.0, "f0": 135.0, "sympathetic_strings": []},
    "tom_high": {"category": "drums", "name": "Том высокий", "resonator_template": "drum_shell", "mask_image": "Drum.png", "body_depth": 0.20, "low_cut": 130.0, "bridge_hill": 2800.0, "f0": 200.0, "sympathetic_strings": []},

    # --- Тарелы (минимальная толщина коробки для плоского звука) ---
    "crash_cymbal": {"category": "cymbals", "name": "Краш-тарела", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "body_depth": 0.05, "low_cut": 150.0, "bridge_hill": 6000.0, "f0": 400.0, "sympathetic_strings": []},
    "ride_cymbal": {"category": "cymbals", "name": "Райд-тарела", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "body_depth": 0.06, "low_cut": 180.0, "bridge_hill": 5000.0, "f0": 350.0, "sympathetic_strings": []},
    "hi_hat": {"category": "cymbals", "name": "Хай-хэт", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "body_depth": 0.05, "low_cut": 200.0, "bridge_hill": 4500.0, "f0": 300.0, "sympathetic_strings": []},

    # --- Металлические ---
    "gong": {"category": "metallic", "name": "Гонг", "resonator_template": "cymbal_plate", "mask_image": "circle_hole.png", "body_depth": 0.08, "low_cut": 40.0, "bridge_hill": 3000.0, "f0": 120.0, "sympathetic_strings": []},
    "cowbell": {"category": "metallic", "name": "Ковбелл", "resonator_template": "tuned_bar", "mask_image": "anvil.png", "body_depth": 0.18, "low_cut": 300.0, "bridge_hill": 3500.0, "f0": 500.0, "ratio_harmonic_1": 2.72, "ratio_harmonic_2": 4.96, "sympathetic_strings": []},
    "triangle": {"category": "metallic", "name": "Треугольник", "resonator_template": "tuned_bar", "mask_image": "triangle.png", "body_depth": 0.05, "low_cut": 400.0, "bridge_hill": 4000.0, "f0": 650.0, "ratio_harmonic_1": 2.82, "ratio_harmonic_2": 5.12, "sympathetic_strings": []},
    "woodblock": {"category": "metallic", "name": "Вудблок", "resonator_template": "stretched_membrane", "mask_image": "coffin.png", "body_depth": 0.06, "low_cut": 250.0, "bridge_hill": 2000.0, "f0": 380.0, "sympathetic_strings": []},
    "tuning_fork": {"category": "metallic", "name": "Камертон", "resonator_template": "tuned_bar", "mask_image": "camertone.png", "body_depth": 0.05, "low_cut": 400.0, "bridge_hill": 4000.0, "f0": 440.0, "ratio_harmonic_1": 6.26, "ratio_harmonic_2": 17.55, "sympathetic_strings": []},

    # --- Специальные ---
    "tibetan_bowl": {"category": "special", "name": "Тибетская чаша", "resonator_template": "tuned_bar", "mask_image": "Bowl.png", "body_depth": 0.12, "low_cut": 120.0, "bridge_hill": 2500.0, "f0": 180.0, "ratio_harmonic_1": 2.72, "ratio_harmonic_2": 4.96, "sympathetic_strings": [90.0, 135.0, 270.0]},
    "steel_drum": {"category": "special", "name": "Стальной панно", "resonator_template": "tuned_bar", "mask_image": "Waterphone.png", "body_depth": 0.18, "low_cut": 200.0, "bridge_hill": 3500.0, "f0": 250.0, "ratio_harmonic_1": 2.50, "ratio_harmonic_2": 4.00, "sympathetic_strings": [165.0, 220.0, 330.0]},
    
    # --- Лабораторные ---
    "perfect_lab_pad": {"category": "lab_testing", "name": "Лабораторный краш-тест", "resonator_template": "ideal_medium", "body_depth": 0.05, "low_cut": 15.0, "bridge_hill": 6000.0, "f0": 100.0, "sympathetic_strings": []}
}

# === 3. КАТЕГОРИИ И ПРЕСЕТЫ МЕЛОДИКИ / ПРОСТРАНСТВ ===
INSTRUMENT_CATEGORIES = {
    "strings_bowed": "🎻 Смычковые резонаторы",
    "strings_plucked": "🎸 Щипковые и Плоские",
    "wind_horns": "📯 Раструбы и Рупоры",
    "spaces_3d": "🏛️ 3D Залы и Пространства",
    "industrial_horror": "🏥 Индустриальные Аномалии",
    "lab_testing": "🔬 Лабораторные Эталоны"
}

INSTRUMENT_PRESETS = {
    # --- Смычковые ---
    "violin": {"category": "strings_bowed", "name": "Скрипка", "resonator_template": "bowed_coupled", "mask_image": "violin.png", "size_m": 0.60, "body_depth": 0.06, "low_cut": 190.0, "bridge_hill": 2500.0, "A0": 275.0, "B1_center": 505.0, "B1_width": 45.0, "sympathetic_strings": [196.00, 293.66, 440.00, 659.25]},
    "cello": {"category": "strings_bowed", "name": "Виолончель", "resonator_template": "bowed_coupled", "mask_image": "cello.png", "size_m": 1.20, "body_depth": 0.15, "low_cut": 65.0, "bridge_hill": 1200.0, "A0": 117.0, "B1_center": 195.0, "B1_width": 30.0, "sympathetic_strings": [65.41, 98.00, 146.83, 220.00]},
    "double_bass": {"category": "strings_bowed", "name": "Контрабас", "resonator_template": "bowed_coupled", "mask_image": "double bass.png", "body_depth": 0.24, "low_cut": 35.0, "bridge_hill": 800.0, "A0": 60.0, "B1_center": 100.0, "B1_width": 20.0, "sympathetic_strings": [41.20, 55.00, 73.42, 98.00]},
    "shichepshin": {"category": "strings_bowed", "name": "Шичепшин (Адыгская скрипка)", "resonator_template": "bowed_coupled", "mask_image": "shichepshin.png", "body_depth": 0.08, "low_cut": 140.0, "bridge_hill": 2000.0, "A0": 225.0, "B1_center": 395.0, "B1_width": 50.0, "sympathetic_strings": [196.00, 293.66]},
    
    # --- Щипковые ---
    "acoustic_guitar": {"category": "strings_plucked", "name": "Акустическая гитара", "resonator_template": "flat_braced", "mask_image": "guitar.png", "size_m": 1.05, "body_depth": 0.12, "low_cut": 80.0, "bridge_hill": 1500.0, "A0": 100.0, "T1": 190.0, "T2": 300.0, "T3": 410.0, "sympathetic_strings": [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]},
    "banjo": {"category": "strings_plucked", "name": "Банджо", "resonator_template": "stretched_membrane", "mask_image": "circle_hole.png", "size_m": 0.60, "body_depth": 0.08, "low_cut": 120.0, "bridge_hill": 2200.0, "f0": 260.0, "sympathetic_strings": [146.83, 196.00, 246.94, 293.66, 392.00]},
    "mandolin": {"category": "strings_plucked", "name": "Мандолина", "resonator_template": "flat_braced", "mask_image": "mandolin.png", "size_m": 0.65, "body_depth": 0.07, "low_cut": 200.0, "bridge_hill": 3000.0, "A0": 280.0, "T1": 400.0, "T2": 550.0, "T3": 750.0, "sympathetic_strings": [196.00, 293.66, 440.00, 659.25]},
    "lute": {"category": "strings_plucked", "name": "Лютня (Ренессанс)", "resonator_template": "flat_braced", "mask_image": "lute.png", "body_depth": 0.16, "low_cut": 90.0, "bridge_hill": 1200.0, "A0": 115.0, "T1": 210.0, "T2": 290.0, "T3": 380.0, "sympathetic_strings": [73.42, 98.00, 130.81, 174.61, 220.00, 293.66, 392.00]},
    "dechig_pondar": {"category": "strings_plucked", "name": "Дечиг-Пондар / Пандури", "resonator_template": "flat_braced", "mask_image": "dechig_pondar.png", "body_depth": 0.09, "low_cut": 90.0, "bridge_hill": 1500.0, "A0": 150.0, "T1": 240.0, "T2": 330.0, "T3": 440.0, "sympathetic_strings": [196.00, 220.00, 261.63]},
        "piano_soundboard": {
        "category": "strings_plucked", 
        "name": "Дека классического пианино", 
        "resonator_template": "flat_braced", 
        "mask_image": "piano_classic.png", 
        "size_m": 1.45, 
        "body_depth": 0.45, 
        "low_cut": 28.0, 
        "bridge_hill": 1200.0, 
        "A0": 80.0,      # Резонанс воздуха внутри корпуса пианино
        "T1": 120.0,     # Основной резонанс деревянного щита
        "T2": 220.0,     # Вторичные гармоники деки
        "T3": 380.0, 
        "sympathetic_strings": [55.00, 110.00, 165.00, 220.00, 330.00, 440.00] # Эффект открытых струн (педаль сустейна)
    },
    # --- Духовые ---
    "zurna_body": {"category": "wind_horns", "name": "Зурна (Абрикосовый раструб)", "resonator_template": "woodwind_bell", "mask_image": "woodwind.png", "body_depth": 0.10, "low_cut": 450.0, "bridge_hill": 3500.0, "F1": 950.0, "F2": 1800.0, "F3": 2800.0, "F4": 4200.0, "sympathetic_strings": []},
    "trumpet_bell": {"category": "wind_horns", "name": "Раструб трубы (Trumpet)", "resonator_template": "woodwind_bell", "mask_image": "trumpet.png", "body_depth": 0.15, "low_cut": 200.0, "bridge_hill": 4500.0, "F1": 800.0, "F2": 1500.0, "F3": 2500.0, "F4": 4000.0, "sympathetic_strings": []},
    "trombone_bell": {"category": "wind_horns", "name": "Раструб тромбона (Trombone)", "resonator_template": "woodwind_bell", "mask_image": "tube curved.png", "body_depth": 0.20, "low_cut": 80.0, "bridge_hill": 3000.0, "F1": 400.0, "F2": 900.0, "F3": 1800.0, "F4": 3200.0, "sympathetic_strings": []},
    "saxophone_bell": {"category": "wind_horns", "name": "Раструб саксофона (Alto/Tenor)", "resonator_template": "woodwind_bell", "mask_image": "sax.png", "body_depth": 0.18, "low_cut": 120.0, "bridge_hill": 2200.0, "F1": 350.0, "F2": 750.0, "F3": 1600.0, "F4": 2800.0, "sympathetic_strings": []},
    "tuba_bell": {"category": "wind_horns", "name": "Раструб тубы (Tuba / Horn)", "resonator_template": "woodwind_bell", "mask_image": "gramophone.png", "body_depth": 0.40, "low_cut": 35.0, "bridge_hill": 1000.0, "F1": 150.0, "F2": 450.0, "F3": 900.0, "F4": 1500.0, "sympathetic_strings": []},
    
    # --- Пространства (тут body_depth работает как высота потолка зала) ---
    "space_cathedral": {"category": "spaces_3d", "name": "Зал: Большой Собор (Cathedral)", "resonator_template": "space_cathedral", "mask_image": "temple.png", "size_m": 40.0, "body_depth": 25.0, "low_cut": 20.0, "bridge_hill": 1500.0, "sympathetic_strings": [196.00, 220.00, 261.63, 293.66, 329.63]},
    "space_cistern": {"category": "spaces_3d", "name": "Зал: Закрытая Цистерна (Cistern)", "resonator_template": "space_cistern", "mask_image": "spiral.png", "size_m": 12.0, "body_depth": 8.0, "low_cut": 35.0, "bridge_hill": 2500.0, "sympathetic_strings": []},
    "karnak_temple": {"category": "spaces_3d", "name": "Зал: Храм Амона в Карнаке", "resonator_template": "space_cathedral", "mask_image": "temple.png", "body_depth": 20.0, "low_cut": 25.0, "bridge_hill": 1300.0, "sympathetic_strings": [196.00, 220.00, 261.63, 293.66, 329.63]},

    # --- Индустриальные Аномалии ---
    "absolute_monolith": {
        "category": "industrial_horror", "name": "Абсолютный Монолит (Plate Canvas)", "resonator_template": "isotropic_plate", "mask_image": "Monolith.png", 
        "body_depth": 0.50, "low_cut": 120.0, "bridge_hill": 3500.0, "f0": 240.0, "sympathetic_strings": []
    },
    "iron_lung_chamber": {
        "category": "industrial_horror", "name": "Аппарат 'Железные лёгкие'", "resonator_template": "space_cistern", "mask_image": "iron_lung.png", 
        "body_depth": 0.80, "low_cut": 85.0, "bridge_hill": 900.0, "sympathetic_strings": [55.00, 65.41, 110.00] 
    },
    "spider_cone_resonator": {
        "category": "industrial_horror", "name": "Акустический паук (Web)", "resonator_template": "stretched_membrane", "mask_image": "web.png", 
        "body_depth": 0.15, "low_cut": 250.0, "bridge_hill": 4500.0, "f0": 380.0, "sympathetic_strings": [146.83, 196.00, 246.94]
    },
    "cracked_church_bell": {
        "category": "industrial_horror", "name": "Расколотый вечевой колокол", "resonator_template": "flat_braced", "mask_image": "broken_bell.png", 
        "body_depth": 1.20, "low_cut": 40.0, "bridge_hill": 2200.0, "A0": 70.0, "T1": 142.0, "T2": 215.0, "T3": 311.0, "sympathetic_strings": [70.0, 72.5] 
    },
    "propaganda_horn": {
        "category": "industrial_horror", "name": "Мегафон пропаганды", "resonator_template": "woodwind_bell", "mask_image": "gramophone.png", 
        "body_depth": 0.60, "low_cut": 600.0, "bridge_hill": 5000.0, "F1": 1200.0, "F2": 2500.0, "F3": 3800.0, "F4": 5500.0, "sympathetic_strings": []
    },
    "pure_skull": {
        "category": "industrial_horror", "name": "Череп (Cranium)", "resonator_template": "drum_shell", "mask_image": "skull.png", "size_m": 0.22,
        "body_depth": 0.15, "low_cut": 250.0, "bridge_hill": 4000.0, "f0": 450.0, "sympathetic_strings": []
    },
    "rib_cage": {
        "category": "industrial_horror", "name": "Грудная клетка (Ribcage)", "resonator_template": "flat_braced", "mask_image": "chest.png", "size_m": 0.45,
        "body_depth": 0.25, "low_cut": 120.0, "bridge_hill": 2000.0, "A0": 180.0, "T1": 320.0, "T2": 550.0, "T3": 850.0, "sympathetic_strings": []
    },
    "cursed_pentagram": {
        "category": "industrial_horror", "name": "Оккультная Пентаграмма", "resonator_template": "cymbal_plate", "mask_image": "pentagram.png", 
        "body_depth": 0.05, "low_cut": 80.0, "bridge_hill": 4000.0, "f0": 200.0, "sympathetic_strings": [66.6, 133.2]
    },
    "shattered_glass": {
        "category": "industrial_horror", "name": "Разбитое стекло (Shattered)", "resonator_template": "isotropic_plate", "mask_image": "broken glass.png", 
        "body_depth": 0.05, "low_cut": 300.0, "bridge_hill": 8000.0, "f0": 1000.0, "sympathetic_strings": []
    },
    "darbuka_shell": {
        "category": "drums", 
        "name": "Кубок Дарбуки", 
        "resonator_template": "drum_shell", 
        "mask_image": "Drum.png", 
        "size_m": 0.25, 
        "body_depth": 0.35, 
        "low_cut": 60.0, 
        "bridge_hill": 2500.0, 
        "f0": 200.0, 
        "sympathetic_strings": []
    },
    # --- Лабораторные ---
    "perfect_lab_medium": {"category": "lab_testing", "name": "Шумовой сканер материала", "resonator_template": "ideal_medium", "body_depth": 0.05, "low_cut": 15.0, "bridge_hill": 6000.0, "f0": 100.0, "sympathetic_strings": []}
}
# --- END OF FILE config/instruments.py ---