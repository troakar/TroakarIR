## Overview

The Troakar Physical Acoustic Synthesis Orchestrator employs a **dual-channel logging architecture** that separates general application diagnostics from structured physics simulation telemetry.

### Channel 1: Standard Python `logging` (Application Diagnostics)

The standard `logging` module handles operational messages, errors, and user-facing events across the application.

**Initialization** (`main.py`):
- Configured at startup via `logging.basicConfig()`
- Level: `DEBUG`
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Dual sinks: file handler writing to `troakar_debug.log` (UTF-8) + console `StreamHandler`

**Logger naming convention**: Hierarchical dotted names scoped by module:
- `Troakar.DLCLoader` — DLC discovery and mounting
- `Troakar.DrumsGUI` — Drums plugin GUI
- `TheHall.GUI` — Shared GUI logger used by dhol and darbuka plugins
- `TheHall.Packer` — Dhol packer utility
- `engine.core_dsp` — DSP engine internals
- `ui.tab_acoustic`, `ui.tab_percussion` — UI tab modules

**Usage patterns**:
- `logger.info()` for lifecycle events (startup, DLC detection, render completion)
- `logger.error(..., exc_info=True)` for exceptions with full tracebacks
- `logger.warning()` for non-fatal issues (e.g., cancelled save dialogs)

### Channel 2: `CoreLogger` (Structured Physics Telemetry)

A custom `CoreLogger` class in `engine/core_logging.py` provides structured, time-series logging specifically for Taichi-accelerated FDTD simulation data.

**Configuration via environment variables**:
| Variable | Default | Purpose |
|---|---|---|
| `TAICHI_LOG_VERBOSITY` | `1` | Controls output detail (0=silent, 1=summary, 2=detailed, 3=micro-events) |
| `TAICHI_LOG_FORMAT` | `json` | Output format: `json` or `csv` |
| `TAICHI_LOG_PATH` | `taichi_physics_log` | Base filename prefix |

**Output files**:
- `taichi_physics_log.jsonl` — JSON Lines format (always written)
- `taichi_physics_log.csv` — CSV format (written when `TAICHI_LOG_FORMAT=csv`)

**Structured event schema** (JSON/CSV fields):
```json
{
  "timestamp": <unix_epoch_float>,
  "event_type": "resolved_physics" | "physics_summary" | "modal_dispersion" | "energy_decay" | "tactile_summary" | "tactile_event" | "inclusion_collision",
  "material": "<material_name>",
  "detail": "<human_readable_description>",
  "value": { ... material-specific metrics ... }
}
```

**Architecture**:
- Thread-safe `RingBuffer` (deque, maxlen 16384) collects events in-memory
- Background daemon thread (`TaichiLogWriter`) flushes buffer to disk every 350ms
- Graceful shutdown via `atexit.register()` ensures final flush
- Console output uses ANSI color codes (blue for core physics, yellow for tactile, red for collisions)

**Event types**:
- `resolved_physics` — Material blend results (density, Young's modulus, loss factor)
- `physics_summary` — General physics parameter summaries
- `modal_dispersion` — Computed modal frequencies
- `energy_decay` — Decay rates per frequency band (dB/ms)
- `tactile_summary` / `tactile_event` — Tactile texture simulation statistics
- `inclusion_collision` — Micro-collision events within material inclusions

## Key Files

- `engine/core_logging.py` — CoreLogger implementation, RingBuffer, singleton instance
- `main.py` — Standard logging initialization, dual-sink configuration
- `dlc_loader.py` — DLC lifecycle logging
- `engine/core_dsp.py` — DSP engine error logging
- `ui/tab_acoustic.py`, `ui/tab_percussion.py` — UI-level operation logging

## Developer Conventions

1. **Use standard `logging` for operational concerns**: startup, errors, user actions, plugin lifecycle. Always include `exc_info=True` on error logs for stack traces.

2. **Use `core_logger` for physics simulation telemetry**: material properties, modal analysis, energy decay, tactile events. The singleton `core_logger` is imported directly from `engine.core_logging`.

3. **Respect verbosity levels**: Check `self.verbosity` before emitting console output in `CoreLogger`. Level 0 suppresses all output; level 3 enables micro-event tracing.

4. **Environment-driven configuration**: Control physics log verbosity and format via `TAICHI_LOG_VERBOSITY` and `TAICHI_LOG_FORMAT` environment variables rather than code changes.

5. **Named loggers**: Use `logging.getLogger(__name__)` for module-scoped loggers, or hierarchical names like `Troakar.<Component>` for cross-module grouping.
