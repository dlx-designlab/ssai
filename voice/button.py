"""Isolated physical-button push-to-talk recording loop."""

import os
import select
import signal
import struct
import subprocess

import config

from .recording import _project_path, transcribe_audio


INPUT_EVENT = struct.Struct("@llHHi")
EV_KEY = 1


def _read_button_event(fd: int, timeout: float) -> tuple[int, int] | None:
    try:
        readable, _, _ = select.select([fd], [], [], timeout)
        if not readable:
            return None
        data = os.read(fd, INPUT_EVENT.size)
    except OSError as exc:
        raise RuntimeError(f"Button device disconnected or unreadable: {exc}") from exc
    if not data:
        raise RuntimeError("Button device disconnected.")
    if len(data) != INPUT_EVENT.size:
        raise RuntimeError("Incomplete event received from button device.")

    _, _, event_type, code, value = INPUT_EVENT.unpack(data)
    if event_type == EV_KEY:
        return code, value
    return None


def _wait_for_press(button_fd: int) -> None:
    print(f"Waiting for {config.VOICE_BUTTON_KEY_NAME}...")
    while True:
        if _read_button_event(button_fd, 0.5) == (
            config.VOICE_BUTTON_KEY_CODE,
            1,
        ):
            return


def _wait_for_release(button_fd: int) -> None:
    while True:
        if _read_button_event(button_fd, 0.5) == (
            config.VOICE_BUTTON_KEY_CODE,
            0,
        ):
            return


def _stop_recording(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            return process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
    return process.communicate()


def _record_while_held(button_fd: int) -> bool:
    duration = config.VOICE_MAX_RECORDING_DURATION
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration <= 0
    ):
        raise ValueError("Maximum button recording duration must be a positive integer.")

    output = _project_path(config.VOICE_INPUT_FILENAME)
    output.unlink(missing_ok=True)
    command = [
        "arecord",
        "-D",
        config.VOICE_AUDIO_INPUT_DEVICE,
        "-f",
        "S16_LE",
        "-c",
        str(config.VOICE_AUDIO_CHANNELS),
        "-r",
        str(config.VOICE_AUDIO_SAMPLE_RATE),
        "-t",
        "wav",
        "-d",
        str(duration),
        str(output),
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not start microphone recording: {exc}") from exc

    stopped_by_release = False
    print("Recording started.")
    try:
        while True:
            try:
                _stdout, stderr = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass

            while select.select([button_fd], [], [], 0)[0]:
                event = _read_button_event(button_fd, 0)
                if event == (config.VOICE_BUTTON_KEY_CODE, 0):
                    _stdout, stderr = _stop_recording(process)
                    stopped_by_release = True
                    break
            if stopped_by_release:
                break
    except BaseException:
        if process.poll() is None:
            _stop_recording(process)
        raise

    if process.returncode and not stopped_by_release:
        detail = stderr.strip() or f"exit code {process.returncode}"
        raise RuntimeError(f"Microphone recording failed: {detail}")

    if not stopped_by_release:
        print(f"Maximum recording duration reached ({duration} seconds).")
        _wait_for_release(button_fd)

    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Recording was not created: {output}")
    return stopped_by_release


def run_push_to_talk() -> None:
    """Run button-controlled recording and STT until interrupted."""
    device = config.VOICE_BUTTON_INPUT_DEVICE
    try:
        button_fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError(f"Button device unavailable at {device}: {exc}") from exc

    print(
        f"Push-to-talk active. Hold {config.VOICE_BUTTON_KEY_NAME} to record; "
        "release to transcribe. Press Ctrl+C to stop."
    )
    try:
        while True:
            _wait_for_press(button_fd)
            _record_while_held(button_fd)
            text = transcribe_audio()
            print(f"Recognized text: {text or '(no speech recognized)'}")
            print(f"Transcript saved to {_project_path(config.VOICE_TRANSCRIPT_FILENAME)}")
    except KeyboardInterrupt:
        print("\nPush-to-talk stopped.")
    finally:
        os.close(button_fd)
