## Overview

The Troakar Physical Acoustic Synthesis Orchestrator uses a **pure Python module-based configuration system** rather than external configuration files (YAML, TOML, JSON, .env). All runtime configuration is defined as Python dictionaries and constants within dedicated modules in the `config/` package, supplemented by a plugin manifest system for dynamically-loaded DLC modules.

## System Architecture

### 1. Core Configuration Package (`config/`)

Three Python modules serve as the central configuration store:

- **`config/instruments.py`** — Defines resonator templates, instrument presets, and percussion presets as nested dictionaries. Contains:
  - `RESONATOR_TEMPLATES`: Mathematical models for physical resonators (bowed_coupled, drum_shell, cymbal_plate, etc.) with lambda functions for mode building
  - `PERCUSSION_PRESETS`: Pre-configured percussion instruments (kick_drum, snare_drum, crash_cymbal, etc.)
  - `INSTRUMENT_PRESETS`: Melodic and spatial instrument presets (violin, cello, acoustic_guitar, space_cathedral, etc.)
  - Category label dictionaries (`PERCUSSION_CATEGORIES`, `INSTRUMENT_CATEGORIES`) for UI organization

- **`config/materials.py`** — Defines physical material properties for acoustic simulation. Contains:
  - `MATERIAL_PHYSICS`: A large dictionary (~60+ entries) mapping material keys to their physical properties including density, Young's modulus (E_long, E_trans), Poisson ratio, loss factor, viscoelastic gamma, base thickness, and tactile profiles
  - `MATERIAL_CATEGORIES`: Category labels for UI grouping (wood, metal, bio, polymer, mineral, synthetic)
  - `blend_materials(mat1, mat2, blend_ratio)`: A function that performs linear interpolation between two material definitions, supporting heterogeneous inclusions and art-layer blending

- **`config/shapes.py`** — Minimal module defining geometric shape templates (square, circle, cello, zurna)

### 2. DLC Plugin Manifest System (`dlc/*/manifest.py`)

Each DLC (downloadable content) plugin directory contains a `manifest.py` file exposing a `DLC_MANIFEST` dictionary with metadata:
```python
DLC_MANIFEST = {
    "name": "The Dhol",
    "version": "1.0.0",
    "author": "Troakar Lab",
    "description": "...",
    "gui_entry_file": "dhol_gui.py",
    "gui_class_name": "DholDLCFrame"
}
```

The `dlc_loader.py` module dynamically discovers and loads these plugins at runtime using `importlib.util.spec_from_file_location()`, scanning the `dlc/` directory for subdirectories containing `manifest.py` files.

### 3. Environment Variable Configuration (Limited)

A small subset of runtime behavior is controlled via environment variables in `engine/core_logging.py`:
- `TAICHI_LOG_VERBOSITY` (default: "1") — Controls logging detail level
- `TAICHI_LOG_FORMAT` (default: "json") — Output format (json or csv)
- `TAICHI_LOG_PATH` (default: "taichi_physics_log") — Base path for log files

These are read once at module import time using `os.getenv()` with hardcoded defaults.

## Key Design Decisions

1. **No External Config Files**: The application deliberately avoids YAML/TOML/JSON configuration files. All configuration lives in Python code, enabling:
   - Lambda functions and computed values (e.g., `modes_builder` lambdas in resonator templates)
   - Direct type safety through Python's native data structures
   - No need for config parsing libraries

2. **Import-Based Access Pattern**: Configuration is accessed via direct imports throughout the codebase:
   ```python
   from config.materials import MATERIAL_PHYSICS, MATERIAL_CATEGORIES
   from config.instruments import RESONATOR_TEMPLATES, INSTRUMENT_PRESETS
   ```
   This pattern appears consistently across engine modules, UI tabs, and DLC plugins.

3. **Mutable Dictionary Configuration**: All configuration dictionaries are mutable Python objects. The `blend_materials()` function demonstrates this by creating new blended material dicts at runtime through interpolation.

4. **Plugin Discovery Over Static Registration**: DLC plugins are discovered dynamically at startup rather than being statically registered, enabling hot-pluggable extension without modifying core code.

5. **Duplicate Definitions**: Note that `config/instruments.py` contains duplicate definitions of `PERCUSSION_CATEGORIES` and `PERCUSSION_PRESETS` (lines 104-138 and 141-175), with the second definition overriding the first. This appears to be an oversight where the second version added `body_depth` fields.

## Developer Conventions

### Adding New Instruments/Materials
- Add new entries directly to the appropriate dictionary in `config/instruments.py` or `config/materials.py`
- Follow the existing schema exactly — all presets reference a `resonator_template` key that must match a key in `RESONATOR_TEMPLATES`
- Material definitions require specific physical property keys: `density`, `E_long`, `E_trans`, `poisson`, `loss_factor`, `visco_gamma`, `base_thickness`, `tactile_profile`, and layer configs (`granular`, `fibrous`, `fluid`)

### Creating DLC Plugins
- Create a subdirectory under `dlc/` with at minimum: `manifest.py`, a GUI module, and optionally an engine module
- `manifest.py` must expose `DLC_MANIFEST` dict with required keys: `name`, `version`, `author`, `description`, `gui_entry_file`, `gui_class_name`
- The GUI class specified in `gui_class_name` must accept `(parent_widget, main_app_ref)` as constructor arguments

### Environment Variables
- Only three env vars are recognized: `TAICHI_LOG_VERBOSITY`, `TAICHI_LOG_FORMAT`, `TAICHI_LOG_PATH`
- These affect only the core instrumentation/logging system, not application behavior
- No `.env` file support or `dotenv` integration exists

### Configuration Import Pattern
- Always import specific symbols rather than the whole module: `from config.materials import MATERIAL_PHYSICS` not `import config`
- Configuration modules have no initialization side effects beyond dictionary construction
