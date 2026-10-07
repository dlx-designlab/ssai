"""Local Piper speech synthesis and PipeWire playback."""

from pathlib import Path
import subprocess
import wave

import config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def generate_speech(text: str) -> Path:
    """Synthesize text with Piper and save it to SSAI's output.wav."""
    if not text.strip():
        raise ValueError("Speech text must not be empty.")

    executable = _project_path(config.VOICE_PIPER_EXECUTABLE)
    model = _project_path(config.VOICE_PIPER_MODEL)
    output = _project_path(config.VOICE_OUTPUT_FILENAME)

    for description, path in (
        ("Piper executable", executable),
        ("Piper voice model", model),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{description} not found: {path}")

    output.unlink(missing_ok=True)
    try:
        subprocess.run(
            [str(executable), "-m", str(model), "-f", str(output), "--", text],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not start Piper: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Piper speech generation failed: {details}") from exc

    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Piper did not create audio output: {output}")

    try:
        with wave.open(str(output), "rb") as audio:
            if audio.getnframes() == 0:
                raise RuntimeError(f"Piper created empty audio output: {output}")
    except wave.Error as exc:
        raise RuntimeError(f"Piper created an invalid WAV file: {output}") from exc

    return output


def play_output() -> None:
    """Play SSAI's generated output.wav and wait for playback to finish."""
    output = _project_path(config.VOICE_OUTPUT_FILENAME)
    if not output.is_file():
        raise FileNotFoundError(f"Audio output not found: {output}")

    if (
        not isinstance(config.VOICE_OUTPUT_VOLUME, int)
        or isinstance(config.VOICE_OUTPUT_VOLUME, bool)
        or not 0 <= config.VOICE_OUTPUT_VOLUME <= 100
    ):
        raise ValueError("VOICE_OUTPUT_VOLUME must be an integer from 0 to 100.")

    try:
        subprocess.run(
            [
                "pw-play",
                "--target",
                config.VOICE_AUDIO_OUTPUT_DEVICE,
                "--volume",
                f"{config.VOICE_OUTPUT_VOLUME / 100:.2f}",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not start audio playback: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Audio playback failed: {details}") from exc


def speak(text: str) -> Path:
    """Generate speech from text, play it, and return the output path."""
    output = generate_speech(text)
    play_output()
    return output
