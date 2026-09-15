from dataclasses import dataclass
import json
import time
from typing import Callable, Iterator

import requests

import config


@dataclass
class ModelMetrics:
    model_name: str = config.MODEL_NAME
    ttft_seconds: float | None = None
    total_response_seconds: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None
    active: bool = False
    available: bool = False


class LLMManager:
    def __init__(self):
        self.model_name = config.MODEL_NAME
        self.api_base = config.OLLAMA_API_BASE.rstrip("/")
        self.history_enabled = config.CONVERSATION_HISTORY
        self.messages: list[dict[str, str]] = []
        self.metrics = ModelMetrics(model_name=self.model_name)

    def check_availability(self) -> tuple[bool, str]:
        try:
            response = requests.get(
                f"{self.api_base}/tags",
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            self.metrics.available = False
            return False, f"Ollama API unavailable: {exc}"

        model_names = {
            item.get("name") or item.get("model")
            for item in data.get("models", [])
        }

        if self.model_name not in model_names:
            self.metrics.available = False
            return False, f"Model '{self.model_name}' is not installed in Ollama"

        self.metrics.available = True
        return True, ""

    def clear_history(self) -> None:
        self.messages.clear()

    def stream_response(
        self,
        prompt: str,
        on_metrics_update: Callable[[ModelMetrics], None] | None = None,
    ) -> Iterator[str]:
        self._reset_current_metrics()
        self.metrics.active = True
        if on_metrics_update:
            on_metrics_update(self.metrics)

        request_messages = self._build_request_messages(prompt)
        payload = {
            "model": self.model_name,
            "messages": request_messages,
            "stream": True,
            "options": {
                "num_predict": config.NUM_PREDICT,
            },
        }

        start_time = time.perf_counter()
        first_token_time: float | None = None
        response_parts: list[str] = []
        final_data: dict = {}

        try:
            with requests.post(
                f"{self.api_base}/chat",
                json=payload,
                stream=True,
                timeout=None,
            ) as response:
                response.raise_for_status()

                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue

                    try:
                        data = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    message = data.get("message") or {}
                    chunk = message.get("content") or ""

                    if chunk:
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                            self.metrics.ttft_seconds = first_token_time - start_time
                            if on_metrics_update:
                                on_metrics_update(self.metrics)

                        response_parts.append(chunk)
                        yield chunk

                    if data.get("done"):
                        final_data = data

            end_time = time.perf_counter()
            self.metrics.total_response_seconds = end_time - start_time
            self._apply_final_metrics(final_data)

            assistant_text = "".join(response_parts)
            if self.history_enabled:
                self.messages.append({"role": "user", "content": prompt})
                self.messages.append({"role": "assistant", "content": assistant_text})

        except requests.RequestException:
            self.metrics.available = False
            raise
        finally:
            self.metrics.active = False
            if on_metrics_update:
                on_metrics_update(self.metrics)

    def _build_request_messages(self, prompt: str) -> list[dict[str, str]]:
        system_message = {
            "role": "system",
            "content": config.SYSTEM_PROMPT,
        }
        if self.history_enabled:
            return [system_message, *self.messages, {"role": "user", "content": prompt}]
        return [system_message, {"role": "user", "content": prompt}]

    def _reset_current_metrics(self) -> None:
        self.metrics.ttft_seconds = None
        self.metrics.total_response_seconds = None
        self.metrics.prompt_tokens = None
        self.metrics.output_tokens = None
        self.metrics.tokens_per_second = None

    def _apply_final_metrics(self, data: dict) -> None:
        self.metrics.prompt_tokens = data.get("prompt_eval_count")
        self.metrics.output_tokens = data.get("eval_count")

        eval_duration_ns = data.get("eval_duration")
        output_tokens = self.metrics.output_tokens

        if output_tokens is not None and eval_duration_ns:
            eval_seconds = eval_duration_ns / 1_000_000_000
            if eval_seconds > 0:
                self.metrics.tokens_per_second = output_tokens / eval_seconds
