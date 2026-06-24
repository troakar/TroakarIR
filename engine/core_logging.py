import atexit
import csv
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger("CoreInstrumentation")

LOG_VERBOSITY = int(os.getenv("TAICHI_LOG_VERBOSITY", "1"))
LOG_FORMAT = os.getenv("TAICHI_LOG_FORMAT", "json").lower()
LOG_BASE_PATH = os.getenv("TAICHI_LOG_PATH", "taichi_physics_log")

class RingBuffer:
    def __init__(self, maxlen: int = 8192):
        self._buffer = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, item: Dict[str, Any]):
        with self._lock:
            self._buffer.append(item)

    def drain(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
        return items

    def __len__(self):
        with self._lock:
            return len(self._buffer)

class CoreLogger:
    def __init__(self, verbosity: int = LOG_VERBOSITY):
        self.verbosity = verbosity
        self.buffer = RingBuffer(maxlen=16384)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._background_writer, daemon=True, name="TaichiLogWriter")
        self._thread.start()
        atexit.register(self.shutdown)
        self._ensure_output_paths()

    def _ensure_output_paths(self):
        self.json_path = f"{LOG_BASE_PATH}.jsonl"
        self.csv_path = f"{LOG_BASE_PATH}.csv"
        try:
            os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        except Exception:
            pass
        # ensure file headers if CSV does not exist
        if LOG_FORMAT == "csv" and not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", encoding="utf-8", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=["timestamp", "event_type", "material", "detail", "value"])
                writer.writeheader()

    def _background_writer(self):
        while not self._stop_event.is_set():
            self._flush_to_disk()
            time.sleep(0.35)
        self._flush_to_disk()

    def _flush_to_disk(self):
        events = self.buffer.drain()
        if not events:
            return
        try:
            with open(self.json_path, "a", encoding="utf-8") as json_file:
                for event in events:
                    json_file.write(json.dumps(event, ensure_ascii=False) + "\n")
            if LOG_FORMAT == "csv":
                with open(self.csv_path, "a", encoding="utf-8", newline="") as csv_file:
                    writer = csv.DictWriter(csv_file, fieldnames=["timestamp", "event_type", "material", "detail", "value"])
                    for event in events:
                        writer.writerow({
                            "timestamp": event.get("timestamp"),
                            "event_type": event.get("event_type"),
                            "material": event.get("material", ""),
                            "detail": event.get("detail", ""),
                            "value": json.dumps(event.get("value", {}), ensure_ascii=False)
                        })
        except Exception as exc:
            logger.warning(f"CoreLogger disk flush failed: {exc}", exc_info=True)

    def shutdown(self):
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def _make_event(self, event_type: str, material: str, detail: str, value: Any) -> Dict[str, Any]:
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "material": material,
            "detail": detail,
            "value": value
        }
        return event

    def _console(self, text: str, color_code: str = ""):
        if self.verbosity == 0:
            return
        reset = "\033[0m" if color_code else ""
        try:
            print(f"{color_code}{text}{reset}")
        except Exception:
            logger.info(text)

    def set_verbosity(self, level: int):
        self.verbosity = max(0, min(3, int(level)))
        logger.info(f"Core instrumentation verbosity set to {self.verbosity}")

    def log_material_blend(self, mat1: Dict[str, Any], mat2: Dict[str, Any], ratio: float, blended: Dict[str, Any]):
        if self.verbosity == 0:
            return
        material = blended.get("name", "Alloy")
        detail = f"Blend {mat1.get('name','A')} + {mat2.get('name','B')} @ {ratio:.2f}"
        value = {
            "density": blended.get("density"),
            "E_long": blended.get("E_long"),
            "E_trans": blended.get("E_trans"),
            "loss_factor": blended.get("loss_factor"),
            "visco_gamma": blended.get("visco_gamma"),
            "base_thickness": blended.get("base_thickness")
        }
        self.buffer.append(self._make_event("resolved_physics", material, detail, value))
        if self.verbosity >= 1:
            self._console(f"[Core] {detail} -> ρ={value['density']:.3f}, E_long={value['E_long']:.3f}, E_trans={value['E_trans']:.3f}, η={value['loss_factor']:.5f}", "\033[94m")

    def log_physics_summary(self, material: Dict[str, Any], detail: str, value: Dict[str, Any]):
        if self.verbosity == 0:
            return
        self.buffer.append(self._make_event("physics_summary", material.get("name", "material"), detail, value))
        if self.verbosity >= 1:
            self._console(f"[Core Physics] {detail}: {value}", "\033[94m")

    def log_modal_dispersion(self, material: Dict[str, Any], freqs: List[float]):
        if self.verbosity == 0:
            return
        detail = "Modal dispersion frequencies"
        value = {f"f_{idx+1}": float(freq) for idx, freq in enumerate(freqs)}
        self.buffer.append(self._make_event("modal_dispersion", material.get("name", "material"), detail, value))
        if self.verbosity >= 1:
            short = ", ".join([f"{freq:.1f}Hz" for freq in freqs[:8]])
            self._console(f"[Core Physics] {detail}: {short}...", "\033[94m")

    def log_energy_decay(self, material: Dict[str, Any], rates: List[Dict[str, Any]]):
        if self.verbosity == 0:
            return
        detail = "Energy decay rates"
        self.buffer.append(self._make_event("energy_decay", material.get("name", "material"), detail, rates))
        if self.verbosity >= 2:
            lines = ", ".join([f"{r['frequency']}Hz={r['decay_db_per_ms']:.4f}dB/ms" for r in rates])
            self._console(f"[Core Physics] {detail}: {lines}", "\033[94m")

    def estimate_modal_dispersion(self, material: Dict[str, Any], num_modes: int = 12) -> List[float]:
        density = material.get("density", 1.0) * 1000.0
        E_long = material.get("E_long", 10.0) * 1e9
        thickness = max(material.get("base_thickness", 0.003), 0.0005)
        c = np.sqrt(max(E_long, 1e3) / density)
        base_f = max(20.0, c / (2.0 * thickness * 25.0))
        freqs = [base_f * (1.0 + 0.22 * i + 0.03 * i**1.2) for i in range(num_modes)]
        return [round(float(np.clip(f, 10.0, 22000.0)), 1) for f in freqs]

    def estimate_energy_decay(self, material: Dict[str, Any], freqs: List[float] = None) -> List[Dict[str, Any]]:
        if freqs is None:
            freqs = [120.0, 250.0, 500.0, 1000.0, 5000.0, 10000.0]
        loss = material.get("loss_factor", 0.01)
        visco = material.get("visco_gamma", 1e-5)
        rates = []
        for f in freqs:
            eta_total = loss + visco * f
            tau = 1.0 / max(1e-12, np.pi * f * eta_total)
            db_per_ms = 8.686 / (tau * 1000.0)
            rates.append({"frequency": float(f), "decay_db_per_ms": float(db_per_ms)})
        return rates

    def log_tactile_summary(self, material: Dict[str, Any], stats: Dict[str, Any]):
        if self.verbosity == 0:
            return
        self.buffer.append(self._make_event("tactile_summary", material.get("name", "material"), "Tactile profile summary", stats))
        if self.verbosity >= 2:
            self._console(f"[Tactile] granularity={stats.get('granular_density',0)} particles, fibrous_events={stats.get('fibrous_events',0)}, inclusion_hits={stats.get('inclusion_collisions',0)}", "\033[93m")

    def log_tactile_event(self, material: Dict[str, Any], event: Dict[str, Any]):
        if self.verbosity < 3:
            return
        self.buffer.append(self._make_event("tactile_event", material.get("name", "material"), event.get("detail", "micro event"), event))
        if self.verbosity >= 3:
            self._console(f"[Tactile Event] {event.get('detail')} -> {event.get('value')}", "\033[93m")

    def log_inclusion_collision(self, material: Dict[str, Any], collision: Dict[str, Any]):
        if self.verbosity == 0:
            return
        self.buffer.append(self._make_event("inclusion_collision", material.get("name", "material"), collision.get("detail", "collision"), collision))
        if self.verbosity >= 2:
            self._console(f"[Inclusion] {collision.get('detail')}", "\033[91m")

core_logger = CoreLogger()
