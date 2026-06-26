## Overview

The Troakar Physical Acoustic Synthesis Orchestrator uses a **logging-centric, try/except-based error handling strategy** built on Python's standard `logging` module. There is no dedicated error types system, custom exception hierarchy, or middleware pattern. Errors are caught at integration boundaries (DLC loading, UI actions, engine initialization) and handled through logging + user-facing dialogs.

---

## System / Approach

### Core Mechanism: Standard Library `logging`
- All error reporting flows through Python's `logging` module (`logging.getLogger(...)`).
- A single global logger configuration is established in `main.py`:
  - Dual output: file handler (`troakar_debug.log`, UTF-8) + console `StreamHandler`.
  - Level set to `DEBUG` for maximum verbosity during development.
- Individual modules create named loggers (e.g., `"Troakar.DLCLoader"`, `"CoreInstrumentation"`, `"Troakar.DrumsGUI"`).

### Error Propagation Pattern
- **Catch-at-boundary**: Exceptions are caught at the outermost layer where they can be meaningfully reported (UI callbacks, DLC loader, main entry point).
- **No re-raising**: Once caught, errors are logged and either:
  - Displayed via `tkinter.messagebox.showerror()` (UI context), or
  - Silently swallowed with a warning (non-critical paths like Taichi runtime checks).
- **No custom exception types**: The codebase uses built-in exceptions (`ValueError`, `InterruptedError`) and bare `Exception` catches exclusively.

### Graceful Degradation
- **Taichi GPU fallback** (`dhol_engine.py`, `dlc/Drums/drums_engine.py`): If GPU initialization fails, the engine falls back to CPU with a printed warning. This is a critical resilience pattern for hardware-dependent computation.
- **DLC isolation** (`dlc_loader.py`): Each DLC plugin is loaded inside its own `try/except`. A failure in one plugin does not prevent other plugins from loading.
- **Render abort support** (`dlc/Drums/drums_gui.py`): Long-running FDTD simulations support user-initiated abortion via an `abort_current_render` flag checked in yield callbacks. Aborted renders still produce partial output files with an `_Aborted` suffix.

---

## Key Files

| File | Role |
|------|------|
| `main.py` | Application entry point; configures root logger; wraps DLC mounting in try/except with `exc_info=True`. |
| `engine/core_logging.py` | Dedicated instrumentation logger (`CoreLogger`) with async background writer, ring buffer, and disk flush error handling. Not a general-purpose error handler — focused on physics telemetry. |
| `dlc_loader.py` | Dynamic plugin discovery; each DLC wrapped in individual `try/except` block; failures logged but do not halt startup. |
| `ui/tab_acoustic.py` | UI action handler; runs generation in daemon thread; catches `Exception`, logs with full traceback, shows `messagebox.showerror`. |
| `ui/tab_percussion.py` | Same pattern as `tab_acoustic.py`. |
| `dlc/Drums/drums_gui.py` | Render loop error handling; `try/except/finally` ensures UI state is always reset; errors logged and shown in dialog. |
| `config/materials.py` | Optional import of `core_logger` wrapped in `try/except` to avoid hard dependency. |

---

## Architecture & Conventions

### Logger Naming Convention
- Loggers follow a dotted namespace pattern: `"Troakar.<ComponentName>"` (e.g., `"Troakar.DLCLoader"`, `"Troakar.DrumsGUI"`).
- The core instrumentation logger uses `"CoreInstrumentation"`.

### Exception Handling Conventions
1. **Bare `except Exception` is the norm**: Nearly all catch blocks use `except Exception` rather than specific exception types. This reflects a "catch everything, log it, move on" philosophy appropriate for a GUI application where crashes are unacceptable.
2. **`exc_info=True` for diagnostic logging**: All error-level log calls include `exc_info=True` to capture full tracebacks in the log file.
3. **User-facing errors via `messagebox`**: In UI contexts, after logging, errors are presented to users via `tkinter.messagebox.showerror()` with the stringified exception message.
4. **Thread-safe error reporting**: Background threads (e.g., render tasks) use `self.after(0, lambda: ...)` to marshal error dialogs back to the main Tkinter thread.

### Non-Error Resilience Patterns
- **Optional dependencies**: `config/materials.py` imports `core_logger` inside a `try/except` to allow the module to function even if the logging subsystem is unavailable.
- **File I/O protection**: `core_logging.py` wraps disk flush operations in `try/except` to prevent logger crashes from affecting the main application.
- **Widget tree scanning fallback** (`main.py`): The `find_all_notebooks` function catches exceptions during recursive widget traversal to handle incomplete UI trees gracefully.

---

## Rules Developers Should Follow

1. **Always log with `exc_info=True`** when catching unexpected exceptions. This ensures tracebacks are captured in `troakar_debug.log`.
2. **Never let exceptions escape UI event handlers**. All button callbacks and threaded tasks must wrap their logic in `try/except Exception` blocks.
3. **Use named loggers** following the `"Troakar.<Component>"` convention. Do not use the root logger directly.
4. **Isolate plugin failures**. When adding new DLC modules, wrap initialization in `try/except` so one broken plugin does not break the entire application.
5. **Provide graceful fallbacks for hardware-dependent code**. If Taichi GPU initialization fails, fall back to CPU (see `init_taichi_headless()` pattern).
6. **Reset UI state in `finally` blocks**. When disabling/enabling buttons during long operations, use `try/except/finally` to ensure buttons are re-enabled even on error.
7. **Do not create custom exception types** unless there is a clear need for structured error handling across module boundaries. The current convention is to rely on built-in exceptions and descriptive log messages.
8. **Use `InterruptedError` for user-initiated cancellation**. The render loops check for GUI closure or abort flags and raise `InterruptedError` to signal intentional termination.
