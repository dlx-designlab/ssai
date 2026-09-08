from dataclasses import dataclass
from pathlib import Path

import psutil

import config


@dataclass
class HardwareSnapshot:
    cpu_percent: float | None = None
    ram_percent: float | None = None
    temperature_c: float | None = None


class HardwareMonitor:
    def __init__(self, temperature_path: str = config.TEMPERATURE_PATH):
        self.temperature_path = Path(temperature_path)

    def read_snapshot(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            cpu_percent=self._read_cpu_percent(),
            ram_percent=self._read_ram_percent(),
            temperature_c=self._read_temperature_c(),
        )

    @staticmethod
    def _read_cpu_percent() -> float | None:
        try:
            return psutil.cpu_percent(interval=None)
        except Exception:
            return None

    @staticmethod
    def _read_ram_percent() -> float | None:
        try:
            return psutil.virtual_memory().percent
        except Exception:
            return None

    def _read_temperature_c(self) -> float | None:
        try:
            raw_value = self.temperature_path.read_text(encoding="utf-8").strip()
            return float(raw_value) / 1000.0
        except (OSError, ValueError):
            return None
