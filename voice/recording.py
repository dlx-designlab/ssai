"""Local microphone recording and Whisper speech recognition."""

import os
import signal
import subprocess
import wave
from pathlib import Path

import config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _audio_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getframerate() != config.VOICE_AUDIO_SAMPLE_RATE
                or audio.getnchannels() != config.VOICE_AUDIO_CHANNELS
                or audio.getsampwidth() * 8 != config.VOICE_AUDIO_BIT_DEPTH
            ):
                raise RuntimeError(
                    "Recording must be 16 kHz, mono, 16-bit PCM audio."
                )
            if audio.getnframes() == 0:
                raise RuntimeError(f"Recording contains no audio: {path}")
            return audio.getnframes() / audio.getframerate()
    except wave.Error as exc:
        raise RuntimeError(f"Could not read recording WAV file: {path}") from exc


def _recording_command(output: Path, duration: int) -> list[str]:
    return [
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


def _validate_recording(output: Path, duration: int) -> Path:
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Recording was not created: {output}")

    actual_duration = _audio_duration(output)
    if actual_duration > duration + 1.0:
        raise RuntimeError(
            f"Recording exceeded its {duration}-second limit "
            f"({actual_duration:.2f} seconds)."
        )
    return output


def record_audio(duration_seconds: int | None = None) -> Path:
    """Record from the configured microphone for up to the requested duration."""
    duration = (
        config.VOICE_RECORDING_DURATION
        if duration_seconds is None
        else duration_seconds
    )
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration <= 0
        or duration > config.VOICE_MAX_RECORDING_DURATION
    ):
        raise ValueError(
            "Recording duration must be a positive integer no greater than "
            f"{config.VOICE_MAX_RECORDING_DURATION} seconds."
        )

    output = _project_path(config.VOICE_INPUT_FILENAME)
    output.unlink(missing_ok=True)
    try:
        subprocess.run(
            _recording_command(output, duration),
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not start microphone recording: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Microphone recording failed: {details}") from exc

    return _validate_recording(output, duration)


def start_button_recording() -> subprocess.Popen[str]:
    """Start a maximum-duration recording for the integrated button flow."""
    duration = config.VOICE_MAX_RECORDING_DURATION
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration <= 0
    ):
        raise ValueError("Maximum button recording duration must be a positive integer.")

    output = _project_path(config.VOICE_INPUT_FILENAME)
    output.unlink(missing_ok=True)
    try:
        return subprocess.Popen(
            _recording_command(output, duration),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not start microphone recording: {exc}") from exc


def stop_button_recording(process: subprocess.Popen[str]) -> None:
    """Stop an active button recording, retaining arecord's WAV header."""
    if process.poll() is None:
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass


def finish_button_recording(
    process: subprocess.Popen[str],
    stopped_by_release: bool,
) -> Path:
    """Wait for arecord and validate its output after a button recording."""
    _stdout, stderr = process.communicate()
    if process.returncode and not stopped_by_release:
        details = stderr.strip() or f"exit code {process.returncode}"
        raise RuntimeError(f"Microphone recording failed: {details}")
    return _validate_recording(
        _project_path(config.VOICE_INPUT_FILENAME),
        config.VOICE_MAX_RECORDING_DURATION,
    )


def transcribe_audio(audio_path: Path | None = None) -> str:
    """Transcribe a WAV file with whisper.cpp and return the recognized text."""
    source = (
        _project_path(config.VOICE_INPUT_FILENAME)
        if audio_path is None
        else Path(audio_path)
    )
    executable = _project_path(config.VOICE_STT_EXECUTABLE)
    model = _project_path(config.VOICE_STT_MODEL)
    transcript = _project_path(config.VOICE_TRANSCRIPT_FILENAME)

    for description, path in (
        ("Input audio", source),
        ("whisper.cpp executable", executable),
        ("Whisper model", model),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{description} not found: {path}")
    if not os.access(executable, os.X_OK):
        raise PermissionError(f"whisper.cpp is not executable: {executable}")

    _audio_duration(source)
    transcript.unlink(missing_ok=True)
    output_prefix = transcript.with_suffix("")
    command = [
        str(executable),
        "-m",
        str(model),
        "-f",
        str(source),
        "-l",
        config.VOICE_STT_LANGUAGE,
        "-otxt",
        "-of",
        str(output_prefix),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError(f"Could not start whisper.cpp: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Speech transcription failed: {details}") from exc

    if not transcript.is_file():
        raise RuntimeError(f"whisper.cpp did not create a transcript: {transcript}")
    try:
        return transcript.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Could not read transcript: {transcript}") from exc


def record_and_transcribe(duration_seconds: int | None = None) -> str:
    """Record microphone audio, transcribe it, and return the recognized text."""
    audio_path = record_audio(duration_seconds)
    return transcribe_audio(audio_path)
