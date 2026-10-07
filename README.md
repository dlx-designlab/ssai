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
- `voice/` - Isolated local TTS generation and audio playback.
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

To test physical-button push-to-talk:

```bash
python3 -m voice
```

Hold F8 to record; release it to stop recording and start transcription. If
the 15-second recording limit is reached while F8 is held, recording stops and
the test waits for F8 to be released before transcribing or waiting for another
press. Press `Ctrl+C` to stop the test.

To test Stage 1 TTS and playback independently:

```bash
python3 -c 'from voice import speak; speak("This is a voice test.")'
```

TTS uses the existing Piper and PipeWire playback setup in `voice_test` and
writes `output.wav` in the SSAI project directory. Voice audio, STT, Piper,
output device, and playback settings are grouped in [config.py](config.py).
The main SSAI conversation flow generates speech for complete model responses.

## Input states

SSAI displays its current input state beside the keyboard entry:

- `RDY` accepts one keyboard Turn or a new F8 push-to-talk press.
- `REC` records while F8 is held. Releasing F8 starts transcription.
- `PROC` covers voice transcription, full LLM response generation, and TTS.
- `SPK` plays the generated response. Input remains blocked until playback
  completes.
- `ERR` blocks both input methods. Pressing F8 resets to `RDY` without
  recording; release it and press again to start a recording.

The text-only state indicator is in the upper-right corner. The former CTX
indicator is removed; this does not alter the conversation history setting or
LLM message history.

The keyboard entry is disabled and cleared outside `RDY`. Button events
received outside `RDY` are discarded, not queued. An F8 press held across a
transition back to `RDY` does not start a recording.

To test keyboard and button input blocking in the running SSAI application:

```bash
python3 main.py
```

While a keyboard response is generating (`PROC`), try typing and pressing
Enter, and press F8. Neither should start another Turn or recording. The
keyboard entry remains empty after generation finishes. To test voice input,
wait for `RDY`, hold F8 and speak, then release it. The state should change
from `REC` to `PROC`; the recognized text appears as `ME:` and is submitted
through the same LLM flow as keyboard input. During `REC`, try typing and
pressing Enter; the entry should remain empty. For `ERR` recovery, when an
operation reports an error, press F8 once to reset to `RDY`; that press must
not record. Release F8, then press it again to start a fresh recording.

For each successful Turn, the response is generated in full and synthesized
before any model text appears. The full `MODEL:` response then appears, audio
playback starts, and the state stays at `SPK` until playback completes.

Voice and keyboard Turns use the same LLM manager and configured conversation
history. To test shared context with history enabled, set
`CONVERSATION_HISTORY = True` in [config.py](config.py), launch SSAI, make a
voice Turn saying “Remember that my favorite color is blue,” then make a
keyboard Turn asking “What is my favorite color?” The response should use the
voice Turn's context. Then make a keyboard Turn giving a different fact and
ask about it in a voice Turn to test the reverse direction.

## Integrated voice and keyboard test

Launch SSAI in one terminal:

```bash
cd /home/ssai-pi/Projects/ssai && python3 main.py
```

Launch the existing Dashboard in a second terminal:

```bash
cd /home/ssai-pi/Projects/ssai && python3 control.py
```

With `CONVERSATION_HISTORY = True`, hold F8 and say in English: “Remember that
my favorite color is blue.” Release the button. No model answer should appear
while it is being generated or synthesized. Once TTS is ready, the GUI should
show the complete `ME:` transcript and complete `MODEL:` answer, then play the
answer. During `PROC` and `SPK`, try typing and pressing Enter; input should
remain blocked. After playback ends and state returns to `RDY`, type “What is
my favorite color?” The answer should reflect the earlier Voice Turn.

Then make a Keyboard Turn that provides a different fact and ask about it in a
Voice Turn to verify that history is shared in the other direction.

To verify history-disabled behavior, stop SSAI, set
`CONVERSATION_HISTORY = False` in [config.py](config.py), restart with the
command above, and repeat the Voice-then-Keyboard fact test. The later Turn
should not rely on the earlier fact. Restore `CONVERSATION_HISTORY = True`
after testing if that is the desired configuration.

In the GUI, confirm the upper-right text state changes through `RDY`, `REC`,
`PROC`, and `SPK` during a Voice Turn; a Keyboard Turn should pass through
`PROC` and `SPK`. In the Dashboard, confirm `Input` is `VOICE` or `KEYBOARD`,
`State` follows the GUI state, `STT Time` updates after Voice recognition, and
`TTS Time` updates after response synthesis. Existing hardware and LLM fields
remain visible in the Dashboard. Conversation history is verified by asking
about a fact given in a previous Voice or Keyboard Turn while no CTX indicator
is displayed.

Press `Ctrl+C` in the Dashboard terminal. Close SSAI with `Ctrl+Alt+Q`.

## Safe error-flow test

To simulate one playback failure without changing files, settings, or system
components, launch SSAI with this temporary in-process test override:

```bash
cd /home/ssai-pi/Projects/ssai && python3 - <<'PY'
import main

real_play_output = main.play_output
fail_once = True

def fail_first_playback():
    global fail_once
    if fail_once:
        fail_once = False
        raise RuntimeError("simulated Stage 7 playback failure")
    real_play_output()

main.play_output = fail_first_playback
main.main()
PY
```

Submit one Keyboard Turn. The complete `MODEL:` response should appear, then
the state should remain `ERR` after the simulated playback failure. Keyboard
input and F8 should not start a new Turn while `ERR` is shown. Press F8 once:
the state should return to `RDY`, without starting a recording. Release F8,
then press it again and speak a short English Voice Turn. The next playback is
not overridden; the new Turn should be transcribed, answered, and spoken
normally. This checks the ERR reset, confirms its reset press did not record,
and verifies a fresh press can start a new Voice Turn. Stop the application
with `Ctrl+C`.

Technical failure details are written to the launching Terminal; the GUI
indicates failure using the `ERR` state only. If a complete model response
exists before TTS or playback fails, its text remains visible.

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
