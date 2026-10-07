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
        self._question_count = 0
        self._current_question: str | None = None
        self._completed_turn: dict | None = None
        self._input = "KEYBOARD"
        self._state = "RDY"
        self._stt_time_seconds: float | None = None
        self._tts_time_seconds: float | None = None

    def update_hardware(self, hardware: HardwareSnapshot) -> None:
        with self._lock:
            self._hardware = HardwareSnapshot(**vars(hardware))
            self._write_locked()

    def update_model(self, model: ModelMetrics) -> None:
        with self._lock:
            self._model = ModelMetrics(**vars(model))
            self._write_locked()

    def update_input(self, input_source: str) -> None:
        with self._lock:
            self._input = input_source
            self._write_locked()

    def update_state(self, state: str) -> None:
        with self._lock:
            self._state = state
            self._write_locked()

    def update_stt_time(self, seconds: float | None) -> None:
        with self._lock:
            self._stt_time_seconds = seconds
            self._write_locked()

    def update_tts_time(self, seconds: float | None) -> None:
        with self._lock:
            self._tts_time_seconds = seconds
            self._write_locked()

    def submit_question(self, question: str) -> None:
        with self._lock:
            self._question_count += 1
            self._current_question = question
            self._write_locked()

    def complete_turn(
        self,
        answer: str | None,
        success: bool,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self._completed_turn = {
                "question": self._current_question,
                "answer": answer,
                "model": self._model_data_locked(),
                "hardware": self._hardware_data_locked(),
                "success": success,
                "error": error,
            }
            self._write_locked()

    def _hardware_data_locked(self) -> dict:
        return {
            "cpu_percent": self._hardware.cpu_percent,
            "ram_used_gb": self._hardware.ram_used_gb,
            "ram_total_gb": self._hardware.ram_total_gb,
            "ram_percent": self._hardware.ram_percent,
            "temperature_c": self._hardware.temperature_c,
        }

    def _model_data_locked(self) -> dict:
        return {
            "model_name": self._model.model_name,
            "ttft_seconds": self._model.ttft_seconds,
            "total_response_seconds": self._model.total_response_seconds,
            "prompt_tokens": self._model.prompt_tokens,
            "output_tokens": self._model.output_tokens,
            "tokens_per_second": self._model.tokens_per_second,
            "active": self._model.active,
            "available": self._model.available,
        }

    def _write_locked(self) -> None:
        data = {
            "hardware": self._hardware_data_locked(),
            "model": self._model_data_locked(),
            "input": self._input,
            "state": self._state,
            "stt_time_seconds": self._stt_time_seconds,
            "tts_time_seconds": self._tts_time_seconds,
            "question_count": self._question_count,
            "current_question": self._current_question,
            "generation": "GENERATING" if self._model.active else "IDLE",
            "completed_turn": self._completed_turn,
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
