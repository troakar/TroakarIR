# dlc/dhol/config/materials.py
import json

try:
    from engine.core_logging import core_logger
except Exception:
    core_logger = None

MATERIAL_CATEGORIES = {
    "wood": "🌲 Древесные породы",
    "metal": "⚙️ Металлы и сплавы",
    "bio": "🦴 Биоматериалы и органика",
    "polymer": "🧪 Полимеры и композиты",
    "mineral": "💎 Минералы и кристаллы",
    "synthetic": "🔬 Синтетика"
}

MATERIAL_PHYSICS = {
    # ----------------------------------------------------------------------
    #  БАЗОВЫЕ МАТЕРИАЛЫ ИЗ ПРЕДЫДУЩИХ СЕССИЙ (ДЛЯ СТАБИЛЬНОСТИ И КОРРЕКТНОСТИ)
    # ----------------------------------------------------------------------
    "steel": {
        "category": "metal",
        "name": "Инструментальная сталь",
        "description": "Экстремально звонкий и упругий металл. Чистый, яркий и бесконечный сустейн без вязких потерь.",
        "density": 7.80, "E_long": 200.0, "E_trans": 200.0, "poisson": 0.30,
        "loss_factor": 0.0005, "visco_gamma": 0.0, "base_thickness": 0.0015,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "rusty_iron": {
        "category": "metal",
        "name": "Ржавый чугун (Серый)",
        "description": "Крупнозернистая графитовая структура. Тяжелый матовый звон с грязным осыпанием ржавчины.",
        "density": 7.15, "E_long": 95.0, "E_trans": 95.0, "poisson": 0.26,
        "loss_factor": 0.022, "visco_gamma": 5.0e-6, "base_thickness": 0.006,
        "granular": {
            "enabled": True, "intensity": 0.9, "particle_count": 15000, "density": 1.2,
            "freq_range": [800.0, 7000.0], "duration_range": [0.002, 0.03], "env_power": 0.85
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.9, "brittleness": 0.2},
        "inclusions": []
    },
    "pomor_bog_pine": {
        "category": "wood",
        "name": "Поморская морёная сосна (Топлёк)",
        "description": "Минерализованная древесина сосны, пролежавшая 500 лет подо льдами. Тяжелый, сухой, костяной звук.",
        "density": 0.85, "E_long": 16.5, "E_trans": 1.8, "poisson": 0.31,
        "loss_factor": 0.014, "visco_gamma": 1.2e-5, "base_thickness": 0.004,
        "granular": {
            "enabled": True, "intensity": 0.8, "particle_count": 8000, "density": 1.2,
            "freq_range": [6000.0, 15000.0], "duration_range": [0.001, 0.004], "env_power": 1.8
        },
        "fibrous": {"enabled": True, "intensity": 0.4, "tension": 2.0, "tear_freq": 22.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.4, "fluidity": 0.0, "granularity": 0.55, "brittleness": 0.65},
        "inclusions": [
            {
                "material": "sea_salt_crystal",
                "density_ratio": 0.15,
                "pattern": "specks",
                "granular": {
                    "enabled": True, "particle_count": 8000,
                    "freq_range": [6000.0, 15000.0], "duration_range": [0.001, 0.004], "env_power": 1.8
                }
            }
        ]
    },
    "walnut": {
        "category": "wood",
        "name": "Кавказский орех",
        "description": "Плотная благородная порода дерева. Идеально сбалансированный теплый тембр с выраженной серединой.",
        "density": 0.64, "E_long": 11.2, "E_trans": 1.25, "poisson": 0.34,
        "loss_factor": 0.018, "visco_gamma": 5.0e-6, "base_thickness": 0.004,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.45, "tension": 1.5, "tear_freq": 15.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.45, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },

    # ----------------------------------------------------------------------
    #  НОВЫЕ ДРЕВЕСНЫЕ ПОРОДЫ (WOODS)
    # ----------------------------------------------------------------------
    "spruce": {
        "category": "wood",
        "name": "Резонансная ель",
        "description": "Сверхлегкое и упругое дерево с рекордным акустическим резонансом и выраженной анизотропией волокон.",
        "density": 0.45, "E_long": 14.5, "E_trans": 0.95, "poisson": 0.37,
        "loss_factor": 0.012, "visco_gamma": 4.0e-6, "base_thickness": 0.003,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.6, "tension": 1.8, "tear_freq": 18.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.6, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "cedar": {
        "category": "wood",
        "name": "Красный кедр",
        "description": "Очень легкое резонансное дерево. Обладает мягким, бархатистым тоном с выраженным поглощением высоких частот.",
        "density": 0.38, "E_long": 9.0, "E_trans": 0.65, "poisson": 0.37,
        "loss_factor": 0.017, "visco_gamma": 1.1e-5, "base_thickness": 0.0035,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.5, "tension": 1.2, "tear_freq": 14.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.5, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "rosewood": {
        "category": "wood",
        "name": "Индийский палисандр",
        "description": "Тяжелая, маслянистая порода. Обладает металлическим, колокольным звоном и невероятным сустейном.",
        "density": 0.85, "E_long": 16.0, "E_trans": 1.8, "poisson": 0.36,
        "loss_factor": 0.009, "visco_gamma": 3.0e-6, "base_thickness": 0.004,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.3, "tension": 2.2, "tear_freq": 20.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.3, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "maple": {
        "category": "wood",
        "name": "Волнистый клён",
        "description": "Плотное, твердое дерево. Дает яркий, пробивной тембр с мгновенной динамической отдачей.",
        "density": 0.65, "E_long": 11.5, "E_trans": 1.35, "poisson": 0.35,
        "loss_factor": 0.015, "visco_gamma": 6.5e-6, "base_thickness": 0.004,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.4, "tension": 1.6, "tear_freq": 16.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.4, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "ebony": {
        "category": "wood",
        "name": "Чёрное дерево (Эбен)",
        "description": "Экстремально плотная, хрупкая древесина. Звенит почти как металл, практически не имея внутренних потерь.",
        "density": 1.15, "E_long": 18.0, "E_trans": 2.2, "poisson": 0.35,
        "loss_factor": 0.007, "visco_gamma": 2.5e-6, "base_thickness": 0.0045,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.25, "tension": 2.8, "tear_freq": 24.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.25, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.4},
        "inclusions": []
    },
    "apricot": {
        "category": "wood",
        "name": "Абрикос (Древесина дудука)",
        "description": "Вязкая резонансная древесина. Создает глубокий, дышащий нижний спектр с бархатным затуханием.",
        "density": 0.75, "E_long": 10.0, "E_trans": 1.5, "poisson": 0.34,
        "loss_factor": 0.019, "visco_gamma": 8.0e-6, "base_thickness": 0.004,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.45, "tension": 1.3, "tear_freq": 13.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.45, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "sacred_sycamore": {
        "category": "wood",
        "name": "Священная сикомора",
        "description": "Пористая древнеегипетская древесина. Легкий, шуршащий, исторический тембр с быстрым затуханием.",
        "density": 0.48, "E_long": 7.5, "E_trans": 0.8, "poisson": 0.32,
        "loss_factor": 0.022, "visco_gamma": 1.2e-5, "base_thickness": 0.005,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.55, "tension": 1.1, "tear_freq": 11.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.55, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    

    # ----------------------------------------------------------------------
    #  ПОЛИМЕРЫ И КОМПОЗИТЫ (POLYMERS & COMPOSITES)
    # ----------------------------------------------------------------------
    "carbon_fiber": {
        "category": "polymer",
        "name": "Углеволокно (Карбон)",
        "description": "Высокотехнологичный изотропно-направленный композит. Обладает высочайшей жесткостью при малом весе.",
        "density": 1.55, "E_long": 135.0, "E_trans": 8.0, "poisson": 0.32,
        "loss_factor": 0.004, "visco_gamma": 2.0e-6, "base_thickness": 0.001,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.2, "tension": 3.0, "tear_freq": 25.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.2, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.1},
        "inclusions": []
    },
    "mylar_standard": {
        "category": "polymer",
        "name": "Майлар стандартный (ПЭТ)",
        "description": "Классический яркий пластик. Введена микро-анизотропия и физическое затухание для устранения ведерного гула.",
        "density": 1.39, 
        "E_long": 4.0, 
        "E_trans": 3.82,  # [ФИКС] Легкая анизотропия натяжения размазывает идеальные резонансы (убирает синусоидальный гул)
        "poisson": 0.38,
        "loss_factor": 0.035, # [ФИКС] Было 0.015. Увеличено для естественного гашения (как у пластика, надетого на кадушку)
        "visco_gamma": 5.5e-5, # [ФИКС] Было 8.0e-6. Увеличено для среза высокочастотного пластикового "звона"
        "base_thickness": 0.00025,
        "granular": {"enabled": False}, 
        "fibrous": {"enabled": False}, 
        "fluid": {"enabled": False},
        # [ФИКС] Добавлена микроскопическая "хрупкость/жесткость", чтобы щелчок был ярче, но не гудел
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.12},
        "inclusions": []
    },
    "mylar": {
        "category": "polymer",
        "name": "Майлар уплотненный",
        "description": "Более плотная версия ПЭТ-мембраны (0.35 мм). Увеличивает сустейн низких частот и плотность удара.",
        "density": 1.39, 
        "E_long": 4.5, 
        "E_trans": 4.2,  
        "poisson": 0.38,
        "loss_factor": 0.028, 
        "visco_gamma": 3.5e-5, 
        "base_thickness": 0.00035,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.08},
        "inclusions": []
    },
    "kevlar_snare_head": {
        "category": "polymer",
        "name": "Кевларовый плетеный корд",
        "description": "Армированный пуленепробиваемый композит. Дает экстремально жесткий, сухой и хлесткий щелчок.",
        "density": 1.44, "E_long": 74.0, "E_trans": 5.0, "poisson": 0.36,
        "loss_factor": 0.025, "visco_gamma": 1.2e-5, "base_thickness": 0.0004,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.5, "tension": 2.6, "tear_freq": 22.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.5, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.2},
        "inclusions": []
    },
    "chitin_plated": {
        "category": "polymer",
        "name": "Хитиновый панцирный композит",
        "description": "Био-армированный полимерный панцирь. Сочетает костяную жесткость и легкое органическое демпфирование.",
        "density": 1.30, "E_long": 8.5, "E_trans": 4.0, "poisson": 0.35,
        "loss_factor": 0.022, "visco_gamma": 9.0e-6, "base_thickness": 0.0006,
        "granular": {
            "enabled": True, "intensity": 0.45, "particle_count": 3000, "density": 0.8,
            "freq_range": [3000.0, 9000.0], "duration_range": [0.001, 0.005], "env_power": 1.4
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.45, "brittleness": 0.3},
        "inclusions": []
    },

    # ----------------------------------------------------------------------
    #  БИОМАТЕРИАЛЫ И ОРГАНИКА (BIO)
    # ----------------------------------------------------------------------
    "animal_skin": {
        "category": "bio",
        "name": "Натуральная кожа (Козья)",
        "description": "Классическая мембрана для перкуссии. Упругая волокнистая ткань с естественным вязким демпфированием.",
        "density": 1.05, "E_long": 0.15, "E_trans": 0.15, "poisson": 0.45,
        "loss_factor": 0.05, "visco_gamma": 2.0e-5, "base_thickness": 0.0008,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.3, "tension": 1.0, "tear_freq": 12.0},
        "fluid": {"enabled": True, "intensity": 0.4, "lfo_freq_range": [5.0, 15.0]},
        "tactile_profile": {"fibrousness": 0.3, "fluidity": 0.4, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "fish_skin": {
        "category": "bio",
        "name": "Рыбья кожа",
        "description": "Кожа осетра или лосося. Специфический, «сырой», водянистый тон для шаманских бубнов.",
        "density": 0.95, "E_long": 0.25, "E_trans": 0.25, "poisson": 0.45,
        "loss_factor": 0.05, "visco_gamma": 2.0e-5, "base_thickness": 0.0008,
        "granular": {"enabled": False}, "fibrous": {"enabled": False},
        "fluid": {"enabled": True, "intensity": 0.5, "lfo_freq_range": [5.0, 20.0]},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.5, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "catgut_membrane": {
        "category": "bio",
        "name": "Сухая бычья кишка",
        "description": "Тончайшая мембрана из высушенных внутренностей. Резкий, щелкающий, «бумажный» звук.",
        "density": 1.25, "E_long": 0.85, "E_trans": 0.85, "poisson": 0.45,
        "loss_factor": 0.03, "visco_gamma": 1.0e-5, "base_thickness": 0.0003,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.6, "tension": 1.8, "tear_freq": 16.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.6, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.5},
        "inclusions": []
    },
    "birch_bark_membrane": {
        "category": "bio",
        "name": "Промасленная береста",
        "description": "Кора березы в качестве мембраны. Глухой, шуршащий, деревянный шлепок без сустейна.",
        "density": 0.65, "E_long": 1.2, "E_trans": 0.4, "poisson": 0.35,
        "loss_factor": 0.12, "visco_gamma": 1.0e-5, "base_thickness": 0.0012,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.7, "tension": 0.8, "tear_freq": 10.0},
        "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.7, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.1},
        "inclusions": []
    },
    "chitin": {
        "category": "bio", "name": "Хитин (Панцирь)", "description": "Легкий, хрупкий биополимер. Дает сухой, чешуйчатый тактильный хруст.",
        "density": 1.20, "E_long": 8.5, "E_trans": 4.5, "poisson": 0.34,
        "loss_factor": 0.03, "visco_gamma": 1.0e-5, "base_thickness": 0.0006,
        "granular": {"enabled": True, "intensity": 0.5, "particle_count": 4000, "density": 0.9, "freq_range": [3000.0, 9500.0], "duration_range": [0.001, 0.006], "env_power": 1.5},
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.5, "brittleness": 0.4}, "inclusions": []
    },
    "cortical_bone": {
        "category": "bio", "name": "Кортикальная кость (Бедренная)", "description": "Сверхплотная биологическая ткань. Выдает резкий, костяной клик на атаке.",
        "density": 1.90, "E_long": 18.0, "E_trans": 11.5, "poisson": 0.32,
        "loss_factor": 0.040, "visco_gamma": 5.0e-6, "base_thickness": 0.005,
        "granular": {"enabled": False}, "fibrous": {"enabled": True, "intensity": 0.2, "tension": 2.5, "tear_freq": 18.0}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.2, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.6}, "inclusions": []
    },
    "enamel": {
        "category": "bio", "name": "Зубная эмаль", "description": "Кристаллическая ткань максимальной жесткости. Рождает ультра-высокий, хрупкий щелчок.",
        "density": 2.90, "E_long": 80.0, "E_trans": 80.0, "poisson": 0.30,
        "loss_factor": 0.003, "visco_gamma": 2.0e-6, "base_thickness": 0.001,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.95}, "inclusions": []
    },
    "ancient_vellum": {
        "category": "bio", "name": "Ритуальный пергамент (Сухие жилы)", "description": "Высушенная под натяжением кожа. Резкий, сухой хруст с постоянным микротреском.",
        "density": 1.15, "E_long": 0.95, "E_trans": 0.95, "poisson": 0.40,
        "loss_factor": 0.04, "visco_gamma": 1.5e-5, "base_thickness": 0.0004,
        "granular": {"enabled": False}, "fibrous": {"enabled": True, "intensity": 0.95, "tension": 2.5, "tear_freq": 25.0}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.95, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.5}, "inclusions": []
    },
    "goat_skin_heavy": {
        "category": "bio",
        "name": "Толстая козья кожа",
        "description": "Тяжелая, глухая перкуссионная мембрана. Мощный бас, мгновенное затухание высоких частот.",
        "density": 1.10, "E_long": 0.22, "E_trans": 0.22, "poisson": 0.44,
        "loss_factor": 0.06, "visco_gamma": 2.5e-5, "base_thickness": 0.0012,
        "granular": {"enabled": False},
        "fibrous": {"enabled": True, "intensity": 0.3, "tension": 0.9, "tear_freq": 11.0},
        "fluid": {"enabled": True, "intensity": 0.45, "lfo_freq_range": [4.0, 12.0]},
        "tactile_profile": {"fibrousness": 0.3, "fluidity": 0.45, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "snake_skin": {
        "category": "bio",
        "name": "Змеиная кожа",
        "description": "Тончайшая чешуйчатая мембрана. Легкий, шуршащий звук с тактильным эффектом трения чешуек.",
        "density": 0.90, "E_long": 0.18, "E_trans": 0.18, "poisson": 0.42,
        "loss_factor": 0.045, "visco_gamma": 1.8e-5, "base_thickness": 0.0003,
        "granular": {
            "enabled": True, "intensity": 0.6, "particle_count": 4000, "density": 1.1,
            "freq_range": [4000.0, 11000.0], "duration_range": [0.001, 0.003], "env_power": 1.3
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.6, "brittleness": 0.0},
        "inclusions": []
    },
    "silk_lacquered": {
        "category": "bio",
        "name": "Лакированный шелк",
        "description": "Натянутый шелк под слоями лака. Певучий, упругий, стеклянно-кристальный тон с ровным затуханием.",
        "density": 1.15, "E_long": 4.5, "E_trans": 4.5, "poisson": 0.38,
        "loss_factor": 0.02, "visco_gamma": 8.0e-6, "base_thickness": 0.0004,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.1},
        "inclusions": []
    },

    # ----------------------------------------------------------------------
    #  МЕТАЛЛЫ И ТЯЖЕЛЫЕ СПЛАВЫ (METALS)
    # ----------------------------------------------------------------------
    "aluminum": {
        "category": "metal",
        "name": "Алюминий",
        "description": "Легкий упругий металл. Обладает очень ярким, высоким, упругим звоном с малым затуханием.",
        "density": 2.70, "E_long": 70.0, "E_trans": 70.0, "poisson": 0.33,
        "loss_factor": 0.001, "visco_gamma": 1.0e-6, "base_thickness": 0.003,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "titanium": {
        "category": "metal",
        "name": "Титан",
        "description": "Экстремально прочный авиационный металл. Рождает хрустальный, чистый звон невероятной длительности.",
        "density": 4.50, "E_long": 116.0, "E_trans": 116.0, "poisson": 0.34,
        "loss_factor": 0.0002, "visco_gamma": 5.0e-7, "base_thickness": 0.002,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "meteoric_iron": {
        "category": "metal", "name": "Метеоритное железо (Камасит)", "description": "Космический сплав. Обладает тяжелым, сверхдолгим, слегка диссонирующим эхо.",
        "density": 7.90, "E_long": 190.0, "E_trans": 190.0, "poisson": 0.29,
        "loss_factor": 0.00015, "visco_gamma": 1.0e-6, "base_thickness": 0.005,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.15, "brittleness": 0.0},
        "inclusions": [{"material": "taenite_alloy", "density_ratio": 0.10, "pattern": "veins"}]
    },
    "pewter": {
        "category": "metal",
        "name": "Пьютер (Оловянный сплав)",
        "description": "Мягкий вязкий сплав. Рождает матовый, глухой удар с полным отсутствием высоких частот.",
        "density": 7.28, "E_long": 42.0, "E_trans": 42.0, "poisson": 0.33,
        "loss_factor": 0.008, "visco_gamma": 3.0e-6, "base_thickness": 0.004,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "pure_gold": {
        "category": "metal", "name": "Чистое золото (Au 99.9%)", "description": "Сверхтяжелый пластичный металл. Низкий, благородный звон с ощущением вязкой массы.",
        "density": 19.30, "E_long": 78.0, "E_trans": 78.0, "poisson": 0.42,
        "loss_factor": 0.005, "visco_gamma": 4.0e-6, "base_thickness": 0.002,
        "granular": {"enabled": False}, "fibrous": {"enabled": False},
        "fluid": {"enabled": True, "intensity": 0.1, "lfo_freq_range": [5.0, 10.0]},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.1, "granularity": 0.0, "brittleness": 0.0}, "inclusions": []
    },
    "lead_shielding": {
        "category": "metal",
        "name": "Тяжелый свинец",
        "description": "Сверхплотный мягкий металл. Полностью поглощает акустическую энергию, выдавая абсолютно мертвый удар.",
        "density": 11.34, "E_long": 16.0, "E_trans": 16.0, "poisson": 0.44,
        "loss_factor": 0.015, "visco_gamma": 8.0e-6, "base_thickness": 0.008,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },
    "depleted_uranium": {
        "category": "metal",
        "name": "Обедненный уран (U-238)",
        "description": "Металл экстремальной плотности и высокой жесткости. Выдает невероятно массивный, тяжелый металлический гул.",
        "density": 19.10, "E_long": 172.0, "E_trans": 172.0, "poisson": 0.23,
        "loss_factor": 0.002, "visco_gamma": 1.5e-6, "base_thickness": 0.005,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.0},
        "inclusions": []
    },

    "taenite_alloy": {
        "category": "metal",
        "name": "Тэнит (Космический никель-железный сплав)",
        "description": "Высоконикилистая фаза метеоритного железа (Ni-Fe). Обладает исключительной плотностью, высокой вязкостью и чистым, холодным металлическим резонансом. Используется как внутреннее включение.",
        "density": 8.15,          # Выше, чем у чистого железа (7.87), из-за содержания никеля
        "E_long": 210.0,          # Модуль Юнга характерен для высокопрочных Ni-Fe сплавов
        "E_trans": 210.0,         # Изотропный кристаллический материал
        "poisson": 0.30,          # Стандартный коэффициент Пуассона для переходных металлов
        "loss_factor": 0.0004,    # Экстремально низкие потери: тэнит звенит долго и чисто
        "visco_gamma": 1.0e-7,    # Практически нулевая вязкоупругость
        "base_thickness": 0.001,  # Тонкие прожилки (veins) внутри матрицы камасита
        
        # Арт-слои отключены, так как это внутреннее включение. 
        # Внешний звук формируется матрицей (meteoric_iron), а тэнит лишь обогащает гармонический спектр.
        "granular": {"enabled": False},
        "fibrous": {"enabled": False},
        "fluid": {"enabled": False},
        
        "tactile_profile": {
            "fibrousness": 0.0,
            "fluidity": 0.0,
            "granularity": 0.0,
            "brittleness": 0.1      # Немного хрупче камасита, но все еще очень вязкий металл
        },
        "inclusions": []
    },


    # ----------------------------------------------------------------------
    #  МИНЕРАЛЫ, КРИСТАЛЛЫ И ГЕО-МАТЕРИАЛЫ (GEOLOGICAL)
    # ----------------------------------------------------------------------
    "ice": {
        "category": "mineral",
        "name": "Природный лёд",
        "description": "Хрупкий гексагональный массив. Звенит высоко и хрустально, сопровождая затухание микро-треском.",
        "density": 0.917, "E_long": 9.0, "E_trans": 9.0, "poisson": 0.33,
        "loss_factor": 0.01, "visco_gamma": 1.0e-5, "base_thickness": 0.01,
        "granular": {
            "enabled": True, "intensity": 0.75, "particle_count": 3000, "density": 0.9,
            "freq_range": [4000.0, 14000.0], "duration_range": [0.001, 0.004], "env_power": 1.6
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.75, "brittleness": 0.8},
        "inclusions": []
    },
    "terracotta": {
        "category": "mineral",
        "name": "Терракота (Обожженная глина)",
        "description": "Пористый запекшийся минерал. Глухой глиняный стук с выраженным песчаным шорохом при трении.",
        "density": 2.15, "E_long": 15.0, "E_trans": 15.0, "poisson": 0.21,
        "loss_factor": 0.02, "visco_gamma": 3.0e-6, "base_thickness": 0.008,
        "granular": {
            "enabled": True, "intensity": 0.8, "particle_count": 8000, "density": 1.1,
            "freq_range": [1500.0, 8000.0], "duration_range": [0.002, 0.015], "env_power": 1.2
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.8, "brittleness": 0.3},
        "inclusions": []
    },
    "solid_basalt": {
        "category": "mineral",
        "name": "Монолитный базальт",
        "description": "Тяжелая вулканическая порода. Обладает глубоким, плотным каменным тембром с быстрым затуханием.",
        "density": 3.00, "E_long": 80.0, "E_trans": 80.0, "poisson": 0.25,
        "loss_factor": 0.004, "visco_gamma": 8.0e-7, "base_thickness": 0.012,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.1},
        "inclusions": []
    },
    "pyrite": {
        "category": "mineral",
        "name": "Пирит (Железный колчедан)",
        "description": "Кристаллический дисульфид железа. Выдает жесткий металлический звон с хрупким золотистым хрустом.",
        "density": 5.00, "E_long": 140.0, "E_trans": 140.0, "poisson": 0.16,
        "loss_factor": 0.001, "visco_gamma": 5.0e-7, "base_thickness": 0.005,
        "granular": {
            "enabled": True, "intensity": 0.5, "particle_count": 5000, "density": 1.0,
            "freq_range": [5000.0, 13000.0], "duration_range": [0.001, 0.005], "env_power": 1.7
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.5, "brittleness": 0.7},
        "inclusions": []
    },
    "imperial_porphyry": {
        "category": "mineral",
        "name": "Императорский порфир (Кровавый камень)",
        "description": "Древний царский камень сверхвысокой прочности. Дает плотный, монументальный каменный звон.",
        "density": 2.75, "E_long": 65.0, "E_trans": 65.0, "poisson": 0.24,
        "loss_factor": 0.003, "visco_gamma": 8.0e-7, "base_thickness": 0.01,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 0.2},
        "inclusions": []
    },
    "cinnabar_ore": {
        "category": "mineral",
        "name": "Киноварь (Ртутная руда)",
        "description": "Тяжелый, но очень мягкий минерал ртути. Дает низкий глухой удар с ощущением тяжелой массы.",
        "density": 8.10, "E_long": 25.0, "E_trans": 25.0, "poisson": 0.30,
        "loss_factor": 0.012, "visco_gamma": 4.0e-6, "base_thickness": 0.008,
        "granular": {
            "enabled": True, "intensity": 0.7, "particle_count": 8000, "density": 1.3,
            "freq_range": [800.0, 5000.0], "duration_range": [0.002, 0.02], "env_power": 1.1
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.7, "brittleness": 0.2},
        "inclusions": []
    },
    "diamond_lattice": {
        "category": "mineral",
        "name": "Алмазная решетка (Diamond)",
        "description": "Экстремальная жесткость кристаллической решетки. Кристально чистый, вечный, ультра-высокий звон.",
        "density": 3.51, "E_long": 1050.0, "E_trans": 1050.0, "poisson": 0.10,
        "loss_factor": 0.0001, "visco_gamma": 1.0e-7, "base_thickness": 0.002,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.0, "brittleness": 1.0},
        "inclusions": []
    },
    "arsenic_crystal": {
        "category": "mineral",
        "name": "Кристаллический мышьяк",
        "description": "Ядовитый хрупкий полуметалл. Выдает сухой, металлический шелест с резким тактильным треском.",
        "density": 5.70, "E_long": 30.0, "E_trans": 30.0, "poisson": 0.20,
        "loss_factor": 0.008, "visco_gamma": 2.0e-6, "base_thickness": 0.004,
        "granular": {
            "enabled": True, "intensity": 0.8, "particle_count": 6000, "density": 1.2,
            "freq_range": [2000.0, 10000.0], "duration_range": [0.001, 0.008], "env_power": 1.6
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.8, "brittleness": 0.8},
        "inclusions": []
    },
    "fulgurite_silica": {
        "category": "mineral",
        "name": "Фульгурит (Спекшаяся молния)",
        "description": "Аморфное шероховатое стекло из удара молнии. Дает легкий хрустящий звон с обилием пустотных шорохов.",
        "density": 2.20, "E_long": 45.0, "E_trans": 45.0, "poisson": 0.17,
        "loss_factor": 0.006, "visco_gamma": 1.2e-6, "base_thickness": 0.003,
        "granular": {
            "enabled": True, "intensity": 0.9, "particle_count": 9000, "density": 1.4,
            "freq_range": [3500.0, 14000.0], "duration_range": [0.001, 0.005], "env_power": 1.7
        },
        "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.9, "brittleness": 0.9},
        "inclusions": []
    },
    "lapis_lazuli": {
        "category": "mineral",
        "name": "Лазурит (Бадахшанский)",
        "description": "Красивый синий поделочный камень. Дает приятный плотный звон с золотистыми искорками пирита.",
        "density": 2.75, "E_long": 60.0, "E_trans": 60.0, "poisson": 0.25,
        "loss_factor": 0.004, "visco_gamma": 1.0e-6, "base_thickness": 0.01,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False},
        "tactile_profile": {"fibrousness": 0.0, "fluidity": 0.0, "granularity": 0.4, "brittleness": 0.3},
        "inclusions": [
            {
                "material": "pyrite_crystal",
                "density_ratio": 0.12,
                "pattern": "specks",
                "granular": {
                    "enabled": True, "particle_count": 4000,
                    "freq_range": [5000.0, 13000.0], "duration_range": [0.001, 0.005], "env_power": 1.7
                }
            }
        ]
    },
    "petrified_wood": {
        "category": "mineral",
        "name": "Окаменелое дерево",
        "description": "Древесина, полностью замещенная халцедоном. Чистый кристаллический звон камня с глубоким резонансом.",
        "density": 2.65, "E_long": 75.0, "E_trans": 40.0, "poisson": 0.20,
        "loss_factor": 0.004, "visco_gamma": 5.0e-7, "base_thickness": 0.008,
        "granular": {"enabled": False},
        "fibrous": {
            "enabled": False,  # Камень не имеет волокнистого скрипа! Обнуляем шум трения.
            "intensity": 0.0
        },
        "fluid": {"enabled": False},
        "tactile_profile": {
            "fibrousness": 0.0, 
            "fluidity": 0.0, 
            "granularity": 0.0, 
            "brittleness": 0.35  # Оставляем только тонкий стекловидный клик контакта при ударе
        },
        "inclusions": []
    },

    # ----------------------------------------------------------------------
    #  ВНУТРЕННИЕ ВСПОМОГАТЕЛЬНЫЕ ШАБЛОНЫ ВКЛЮЧЕНИЙ (INCLUSION REFERENCE TEMPLATES)
    # ----------------------------------------------------------------------
    "sea_salt_crystal": {
        "category": "mineral", "name": "Кристаллы морской соли", "description": "Вспомогательный материал включения.",
        "density": 2.16, "E_long": 25.0, "E_trans": 25.0, "poisson": 0.25, "loss_factor": 0.005, "visco_gamma": 0.0, "base_thickness": 0.001,
        "granular": {"enabled": True, "freq_range": [6000.0, 15000.0], "duration_range": [0.001, 0.004], "env_power": 1.8},
        "fibrous": {"enabled": False}, "fluid": {"enabled": False}, "tactile_profile": {"granularity": 1.0, "brittleness": 1.0}, "inclusions": []
    },
    "pyrite_crystal": {
        "category": "mineral", "name": "Кристаллы пирита", "description": "Вспомогательный материал включения.",
        "density": 5.01, "E_long": 140.0, "E_trans": 140.0, "poisson": 0.16, "loss_factor": 0.001, "visco_gamma": 0.0, "base_thickness": 0.001,
        "granular": {"enabled": True, "freq_range": [5000.0, 13000.0], "duration_range": [0.001, 0.005], "env_power": 1.7},
        "fibrous": {"enabled": False}, "fluid": {"enabled": False}, "tactile_profile": {"granularity": 0.8, "brittleness": 0.8}, "inclusions": []
    },
    "taenite_alloy": {
        "category": "metal", "name": "Сплав Тэнит (Космический Никель)", "description": "Вспомогательный материал включения.",
        "density": 8.20, "E_long": 210.0, "E_trans": 210.0, "poisson": 0.30, "loss_factor": 0.0004, "visco_gamma": 0.0, "base_thickness": 0.001,
        "granular": {"enabled": False}, "fibrous": {"enabled": False}, "fluid": {"enabled": False}, "tactile_profile": {}, "inclusions": []
    }
}

def blend_materials(mat1: dict, mat2: dict, blend_ratio: float) -> dict:
    """
    Создает физический сплав (Alloy) двух материалов.
    Полная поддержка гетерогенных включений (inclusions) и интерполяция арт-слоёв на корневом уровне.
    blend_ratio: 0.0 = 100% mat1, 1.0 = 100% mat2.
    """
    ratio = max(0.0, min(1.0, blend_ratio))
    inv_ratio = 1.0 - ratio
    
    blended = {
        "name": f"Alloy ({mat1.get('name', 'A')} + {mat2.get('name', 'B')})",
        "category": "alloy",
        "description": f"Физический сплав на основе {mat1.get('name', 'A')} ({int(inv_ratio*100)}%) и {mat2.get('name', 'B')} ({int(ratio*100)}%).",
        
        # Линейная интерполяция базовой (гомогенной) физики матрицы
        "density": mat1.get("density", 1.0) * inv_ratio + mat2.get("density", 1.0) * ratio,
        "E_long": mat1.get("E_long", 1.0) * inv_ratio + mat2.get("E_long", 1.0) * ratio,
        "E_trans": mat1.get("E_trans", 1.0) * inv_ratio + mat2.get("E_trans", 1.0) * ratio,
        "poisson": mat1.get("poisson", 0.3) * inv_ratio + mat2.get("poisson", 0.3) * ratio,
        "loss_factor": mat1.get("loss_factor", 0.01) * inv_ratio + mat2.get("loss_factor", 0.01) * ratio,
        "visco_gamma": mat1.get("visco_gamma", 1e-5) * inv_ratio + mat2.get("visco_gamma", 1e-5) * ratio,
        "base_thickness": mat1.get("base_thickness", 0.003) * inv_ratio + mat2.get("base_thickness", 0.003) * ratio,
        
        "tactile_profile": {},
        "granular": {"enabled": False},
        "fibrous": {"enabled": False},
        "fluid": {"enabled": False},
        "inclusions": [] 
    }
    
    # Смешиваем тактильные свойства
    t1 = mat1.get("tactile_profile", {})
    t2 = mat2.get("tactile_profile", {})
    for key in ["fibrousness", "fluidity", "granularity", "brittleness"]:
        val1 = t1.get(key, 0.0)
        val2 = t2.get(key, 0.0)
        blended["tactile_profile"][key] = val1 * inv_ratio + val2 * ratio

    # Дефолтные значения параметров на случай полного отсутствия в обоих структурах
    layer_defaults = {
        "granular": {
            "intensity": 0.0,
            "particle_count": 0,
            "density": 0.0,
            "freq_range": [2500.0, 12000.0],
            "duration_range": [0.002, 0.012],
            "env_power": 1.0,
            "exponential_rise": 1.0,
        },
        "fibrous": {
            "intensity": 0.0,
            "tension": 1.0,
            "tear_freq": 15.0,
        },
        "fluid": {
            "intensity": 0.0,
            "lfo_freq_range": [5.0, 20.0],
        }
    }

    # Интерполируем арт-слои напрямую на корневом уровне
    for layer in ["granular", "fibrous", "fluid"]:
        l1 = mat1.get(layer, {"enabled": False})
        l2 = mat2.get(layer, {"enabled": False})
        
        if l1.get("enabled") or l2.get("enabled"):
            blended[layer] = {"enabled": True}
            
            # Собираем все уникальные ключи параметров для этого слоя
            all_keys = (set(l1.keys()).union(set(l2.keys()))) - {"enabled"}
            for k in all_keys:
                # Определяем качественные (тембральные) свойства
                is_qualitative = k in [
                    "freq_range", "duration_range", "lfo_freq_range", 
                    "tension", "tear_freq", "env_power", "exponential_rise"
                ]
                
                # Извлекаем значения. Если свойство отсутствует у одного из материалов:
                # - Качественные параметры копируем из второго материала (чтобы не занулять диапазоны частот)
                # - Количественные параметры зануляем
                if k in l1:
                    v1 = l1[k]
                else:
                    v1 = l2.get(k) if is_qualitative else layer_defaults[layer].get(k, 0.0)
                    
                if k in l2:
                    v2 = l2[k]
                else:
                    v2 = l1.get(k) if is_qualitative else layer_defaults[layer].get(k, 0.0)
                    
                # Страховочный фолбэк
                if v1 is None: v1 = layer_defaults[layer].get(k, 0.0)
                if v2 is None: v2 = layer_defaults[layer].get(k, 0.0)
                
                # Проводим интерполяцию в зависимости от типа структуры
                if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    blended[layer][k] = v1 * inv_ratio + v2 * ratio
                elif isinstance(v1, list) and isinstance(v2, list) and len(v1) == len(v2):
                    blended[layer][k] = [v1[i] * inv_ratio + v2[i] * ratio for i in range(len(v1))]
                else:
                    # Фолбэк для несовпадающих типов данных
                    blended[layer][k] = v2 if ratio > 0.5 else v1

    # --- ЛОГИКА ГЕТЕРОГЕННЫХ ВКЛЮЧЕНИЙ ---
    # 1. Добавляем вкрапления от первого материала (уменьшаем их плотность на inv_ratio)
    for inc in mat1.get("inclusions", []):
        inc_copy = dict(inc)
        orig_ratio = float(inc_copy.get("density_ratio", 0.1))
        inc_copy["density_ratio"] = orig_ratio * inv_ratio
        
        if inc_copy["density_ratio"] > 0.001:
            blended["inclusions"].append(inc_copy)
            
    # 2. Добавляем вкрапления от второго материала (уменьшаем их плотность на ratio)
    for inc in mat2.get("inclusions", []):
        inc_copy = dict(inc)
        orig_ratio = float(inc_copy.get("density_ratio", 0.1))
        inc_copy["density_ratio"] = orig_ratio * ratio
        
        if inc_copy["density_ratio"] > 0.001:
            blended["inclusions"].append(inc_copy)
            
    if core_logger is not None:
        core_logger.log_material_blend(mat1, mat2, ratio, blended)
    return blended