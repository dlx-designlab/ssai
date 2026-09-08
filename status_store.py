from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

import config
from hardware_monitor import HardwareSnapshot
from llm_manager import ModelMetrics


class StatusStore:
    """Thread-safe status shared with the separate SSH control process."""

    def __init__(self, path: str = config.STATUS_FILE):
        self.path = Path(path)
        self._lock = Lock()
        self._hardware = HardwareSnapshot()
        self._model = ModelMetrics(model_name=config.MODEL_NAME)

    def update_hardware(self, hardware: HardwareSnapshot) -> None:
        with self._lock:
            self._hardware = HardwareSnapshot(**vars(hardware))
            self._write_locked()

    def update_model(self, model: ModelMetrics) -> None:
        with self._lock:
            self._model = ModelMetrics(**vars(model))
            self._write_locked()

    def _write_locked(self) -> None:
        data = {
            "hardware": {
                "cpu_percent": self._hardware.cpu_percent,
                "ram_percent": self._hardware.ram_percent,
                "temperature_c": self._hardware.temperature_c,
            },
            "model": {
                "model_name": self._model.model_name,
                "ttft_seconds": self._model.ttft_seconds,
                "total_response_seconds": self._model.total_response_seconds,
                "prompt_tokens": self._model.prompt_tokens,
                "output_tokens": self._model.output_tokens,
                "tokens_per_second": self._model.tokens_per_second,
                "active": self._model.active,
                "available": self._model.available,
            },
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            delete=False,
        ) as temp_file:
            json.dump(data, temp_file)
            temp_name = temp_file.name

        os.replace(temp_name, self.path)

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
