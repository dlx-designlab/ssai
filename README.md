# SSAI

SSAI is a local AI conversation system designed for a Raspberry Pi 5. It uses
Ollama to run a local language model and provides a simple Tkinter interface for
conversation and system monitoring.

## Status

This project is an active prototype. The current configuration targets a Linux
system with a local Ollama server and the `phi3.5:latest` model.

## Features

- Local conversation with a language model.
- Streaming model responses in the graphical interface.
- Optional conversation history.
- CPU, RAM, and temperature monitoring.
- A separate terminal control view for hardware and model status.

## Project structure

- `main.py` - Starts the application and coordinates the main components.
- `gui.py` - Implements the Tkinter conversation interface.
- `llm_manager.py` - Checks Ollama availability and streams model responses.
- `hardware_monitor.py` - Reads CPU, RAM, and temperature data.
- `status_store.py` - Writes shared status data to a JSON file.
- `control.py` - Displays shared status in a terminal view.
- `config.py` - Contains application, model, GUI, and hardware settings.
- `DEVELOPMENT_LOG.md` - Daily development log describing completed work.
- `LICENSE` - MIT license.

## Requirements

The current implementation requires:

- Linux.
- Python 3.
- Tkinter.
- The Python packages `requests` and `psutil`.
- Ollama running locally at `http://127.0.0.1:11434`.
- The model `phi3.5:latest` installed in Ollama.

The repository does not currently include a dependency manifest such as
`requirements.txt` or `pyproject.toml`.

## Setup

1. Install Python 3 and Tkinter for the operating system.
2. Install the Python packages `requests` and `psutil`.
3. Install and start Ollama.
4. Make sure the `phi3.5:latest` model is available in Ollama.
5. Review [config.py](config.py) if the model name or Ollama address needs to
   change.

The exact package-manager commands are intentionally not documented yet because
the repository does not define a specific Linux distribution or installation
method.

## Running

Start the main graphical application:

```bash
python3 main.py
```

The application checks Ollama, opens the Tkinter interface, and periodically
writes hardware and model status to `/tmp/ssai_status.json`.

In a separate terminal, start the control view:

```bash
python3 control.py
```

The control view reads the shared status file and refreshes every 0.5 seconds.
Hardware samples are collected by the main application every 15 seconds, so
the faster control refresh also shows question and generation-state changes
promptly without increasing hardware sampling frequency. Press `Ctrl+C` to
close it.

## Configuration

The main settings are in [config.py](config.py), including:

- Ollama address and model name.
- Response generation limits.
- Conversation history.
- GUI appearance and fullscreen mode.
- Hardware and status refresh intervals.
- The technician exit shortcut.

The default technician exit shortcut in the graphical interface is
`Ctrl+Alt+Q`.

## Current limitations

- The project is currently a prototype focused on the Raspberry Pi/Linux
  environment.
- Ollama must be available locally before model responses can be generated.
- The GUI is configured for fullscreen operation by default.
- Hardware temperature monitoring uses the Linux path configured in
  `config.py`.
- The repository does not currently include automated tests or a CI workflow.
- Installation is not yet captured in a dependency or environment manifest.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
