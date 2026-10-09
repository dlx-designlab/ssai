# SSAI

SSAI is a standalone Raspberry Pi-based prototype for local text and voice
interaction with a language model. It uses a Tkinter interface, sends requests
to a local Ollama server, and can accept spoken input and play synthesized
responses.

## Status

The current implementation targets the Raspberry Pi/Linux environment. Voice
recognition and synthesis binaries and models are configured in the sibling
`voice_test` project; they are not included in this repository.

## Hardware

| Component | Model and specifications | Manufacturer documentation |
| --- | --- | --- |
| Single-board computer | Raspberry Pi 5 Model B, 8 GB RAM | [Raspberry Pi 5 Documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html) |
| Display | Waveshare 3.5inch RPi LCD (A), Rev 4.0; 480 x 320 | [Waveshare Wiki](https://www.waveshare.com/wiki/3.5inch_RPi_LCD_%28A%29) |
| Audio interface and microphones | Seeed Studio reSpeaker Lite USB audio interface with integrated microphones | [Seeed Studio Documentation](https://wiki.seeedstudio.com/reSpeaker_usb_v3/) |
| Speaker | External speaker; model not specified | |
| UPS | Geekworm X1201 dual-18650 battery UPS for Raspberry Pi 5B | [Geekworm X1201 Wiki](https://wiki.geekworm.com/X1201) |
| Batteries | HO LIFE 18650; 2 x Li-ion, 3.6 V nominal, stated capacity 3015 mAh per cell | |
| Cooling | Generic active cooler with fan and heatsink | |
| Keyboard | Wireless USB keyboard | |

## Software Environment

Versions below describe the current development device where verified.

| Component | Current environment or configured component |
| --- | --- |
| Operating system | Debian 13 (Trixie), 64-bit, `aarch64` |
| Python | 3.13.5 |
| GUI | Tkinter 8.6 |
| Ollama | 0.34.0; accessed through its local HTTP API |
| Language model | `phi3.5:latest` |
| Speech recognition | `whisper.cpp` executable with the `ggml-base.bin` model |
| Speech synthesis | Piper TTS 1.8.0 with `en_US-lessac-medium.onnx` |
| Audio playback | PipeWire `pw-play` |
| Hardware monitoring | Python `psutil` plus the configured Linux thermal-zone file |

The voice executable and model paths are configured in [config.py](config.py) and
point into `../voice_test`. SSAI also uses the `requests` and `psutil` Python
packages. There is no dependency manifest in this repository.

## Requirements

The application requires Linux, Python 3 with Tkinter, the `requests` and
`psutil` packages, and a local Ollama server with the configured model. Voice
input and output also require the configured `arecord`, `whisper.cpp`, Piper,
and `pw-play` tools and their model files. SSAI does not install or provision
these components.

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

The Dashboard reads the shared status file and refreshes every 0.5 seconds.
Hardware samples are collected by the main application every 15 seconds, so
the faster refresh shows question and generation-state changes without
increasing hardware sampling frequency. Press `Ctrl+C` to close it.

## Isolated voice functions

To run an isolated recording/STT test without submitting the transcript to the
LLM, record up to the configured default duration (10 seconds) and display the
recognized text:

```bash
python3 -c 'from voice import record_and_transcribe; print(record_and_transcribe())'
```

`record_audio(duration_seconds=None)` and `transcribe_audio()` are also
available separately. The recording duration can be set up to the configured
15-second maximum. Audio and transcript are saved as `input.wav` and
`transcript.txt` in the SSAI project directory. Recording uses the existing
`arecord` setup; transcription uses the existing whisper.cpp executable and
model in the sibling `voice_test` project.

## System Operation

Keyboard input is accepted in `RDY` and submitted with Enter. For voice input,
hold F8 to record; releasing F8 starts speech recognition. The recognized text
is submitted through the same LLM turn path as keyboard input.

The application collects the complete Ollama response, generates one Piper WAV
file, then plays it once through `pw-play`. During playback, the GUI reveals the
response in small word groups, timed approximately from the WAV duration and
punctuation. The first group appears as playback starts; the remaining text is
shown when playback completes. If speech generation or playback fails, the full
text response is still shown.

## States and Controls

- `RDY` accepts a new keyboard Turn or F8 press.
- `REC` records while F8 is held; releasing F8 starts transcription.
- `PROC` handles speech recognition, model generation, and speech synthesis.
- `SPK` plays the generated response.
- `ERR` blocks new input until F8 is pressed once to return to `RDY`.

The keyboard entry is disabled and cleared outside `RDY`. The mouse cursor is
hidden and mouse events do not interact with the GUI. Up and Down scroll the
transcript; scrolling upward pauses automatic following, and returning to the
bottom resumes it. Each new Turn places its `ME:` line near the top and resumes
automatic following.

- F1 toggles Context. Both transitions clear stored history; when enabled,
  history retains up to four complete conversation Turns. The initial setting
  is `CONVERSATION_HISTORY` in [config.py](config.py), currently off.
- F4 restarts SSAI after two distinct presses within three seconds. It does not
  reboot the Raspberry Pi.
- Ctrl+Alt+Q exits the application.

## Project Structure

- `main.py` coordinates the GUI, keyboard and voice input, Ollama, speech
  synthesis and playback, application states, and hardware monitoring.
- `config.py` contains model, voice, GUI, timing, hardware, and status settings.
- `gui.py` implements the Tkinter conversation interface and its controls.
- `llm_manager.py` checks Ollama availability, submits chat requests, manages
  optional conversation history, and records model metrics.
- `hardware_monitor.py` reads CPU, memory, and temperature information.
- `status_store.py` writes shared status data for the Dashboard.
- `control.py` displays the shared status in a terminal Dashboard.
- `voice/` contains recording, Whisper transcription, Piper synthesis, playback,
  and the isolated push-to-talk utility.
- `DEVELOPMENT_LOG.md` records dated development and documentation updates.
- `LICENSE` contains the project license.

## Voice Utilities

Run the isolated push-to-talk and transcription utility with:

```bash
python3 -m voice
```

For a single recording and transcription, use:

```bash
python3 -c 'from voice import record_and_transcribe; print(record_and_transcribe())'
```

To generate and play a standalone speech sample, use:

```bash
python3 -c 'from voice import speak; speak("This is a voice test.")'
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Current Constraints

- Ollama must be available locally for model responses.
- The GUI opens fullscreen by default; display and device settings are in
  [config.py](config.py).
- Voice executables and model files are external to this repository and must
  exist at the configured paths.
- This repository has no dependency manifest or documented package-manager
  installation procedure.

