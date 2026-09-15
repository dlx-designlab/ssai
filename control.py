from __future__ import annotations

import json
import time
from pathlib import Path

import config


def clear_terminal() -> None:
    print("\033[2J\033[H", end="", flush=True)


def format_percent(value) -> str:
    return "--" if value is None else f"{value:.0f}%"


def format_temperature(value) -> str:
    return "--" if value is None else f"{value:.1f}C"


def format_seconds(value) -> str:
    return "--" if value is None else f"{value:.2f}s"


def format_int(value) -> str:
    return "--" if value is None else str(value)


def format_rate(value) -> str:
    return "--" if value is None else f"{value:.1f}"


def format_ram(used, total, percent) -> str:
    if used is None or total is None or percent is None:
        return "--"
    return f"{used:.1f} / {total:.1f} GB ({percent:.0f}%)"


def read_status(path: Path) -> dict | None:
    try:
        if time.time() - path.stat().st_mtime > config.STATUS_STALE_AFTER_SECONDS:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def render(status: dict | None) -> None:
    clear_terminal()
    print(f"{config.PROGRAM_NAME}  {config.PROGRAM_VERSION}")
    print("=" * 42)

    if status is None:
        print("Status: waiting for main SSAI process...")
        return

    hardware = status.get("hardware", {})
    model = status.get("model", {})
    model_status = "RUNNING" if model.get("active") else (
        "READY" if model.get("available") else "OFFLINE"
    )

    print(f"{model.get('model_name', config.MODEL_NAME)} | {model_status}")
    print()
    print("HARDWARE")
    print(f"CPU:  {format_percent(hardware.get('cpu_percent'))}")
    print(
        f"RAM:  {format_ram(hardware.get('ram_used_gb'), hardware.get('ram_total_gb'), hardware.get('ram_percent'))}"
    )
    print(f"Temp: {format_temperature(hardware.get('temperature_c'))}")
    print()
    print("MODEL")
    print(f"Name:   {model.get('model_name', '--')}")
    print(f"TTFT:   {format_seconds(model.get('ttft_seconds'))}")
    print(f"Total:  {format_seconds(model.get('total_response_seconds'))}")
    print(f"Prompt: {format_int(model.get('prompt_tokens'))}")
    print(f"Output: {format_int(model.get('output_tokens'))}")
    print(f"Tok/s:  {format_rate(model.get('tokens_per_second'))}")
    print()
    print("Ctrl+C to close control view")


def main() -> None:
    path = Path(config.STATUS_FILE)
    try:
        while True:
            render(read_status(path))
            time.sleep(config.CONTROL_REFRESH_INTERVAL)
    except KeyboardInterrupt:
        clear_terminal()
        print("SSAI control closed.")


if __name__ == "__main__":
    main()
