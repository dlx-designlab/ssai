from __future__ import annotations

import os
import queue
import select
import signal
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from enum import Enum

import psutil
import requests

import config
from gui import ConversationGUI
from hardware_monitor import HardwareMonitor
from llm_manager import LLMManager, ModelMetrics
from status_store import StatusStore
from voice.recording import (
    finish_button_recording,
    start_button_recording,
    stop_button_recording,
    transcribe_audio,
)
from voice.tts import generate_speech, get_audio_duration_seconds, play_output


class SystemState(str, Enum):
    RDY = "RDY"
    REC = "REC"
    PROC = "PROC"
    SPK = "SPK"
    ERR = "ERR"


INPUT_EVENT = struct.Struct("@llHHi")
EV_KEY = 1


class SSAIApplication:
    """Coordinates the GUI, local LLM, hardware monitor and SSH status data."""

    def __init__(self):
        self.stop_event = threading.Event()
        self.hardware_monitor = HardwareMonitor()
        self.llm_manager = LLMManager()
        self.status_store = StatusStore()

        self.background_thread: threading.Thread | None = None
        self.generation_thread: threading.Thread | None = None
        self.button_thread: threading.Thread | None = None
        self.voice_processing_thread: threading.Thread | None = None
        self.playback_thread: threading.Thread | None = None
        self.voice_events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.state_lock = threading.Lock()
        self.system_state = SystemState.RDY
        self.restart_requested = False
        self.turn_id = 0
        self.last_error_message: str | None = None
        self.button_down = False
        self.voice_recording_process: subprocess.Popen[str] | None = None

        self.root: tk.Tk | None = None
        self.gui: ConversationGUI | None = None

    def run(self) -> None:
        self._install_signal_handlers()

        self.llm_manager.check_availability()
        self._update_model_status(self.llm_manager.metrics)
        self._start_background_thread()

        self.root = tk.Tk()
        self.gui = ConversationGUI(
            root=self.root,
            on_submit=self._handle_prompt,
            on_exit=self._request_exit,
            on_response_ready=self._response_ready,
            on_toggle_context=self.llm_manager.toggle_context,
            context_enabled=self.llm_manager.history_enabled,
            on_restart=self._request_restart,
        )
        self.gui.set_system_state(self.system_state.value)
        self._start_button_thread()
        self.root.after(40, self._poll_voice_events)

        try:
            self.root.mainloop()
        finally:
            self._shutdown()

        if self.restart_requested:
            self._restart_application()

    def _handle_prompt(self, prompt: str) -> bool:
        if self.stop_event.is_set() or self.gui is None:
            return False

        if self._get_system_state() is not SystemState.RDY:
            return False

        self.status_store.update_input("KEYBOARD")
        self.status_store.update_stt_time(None)
        self.status_store.update_tts_time(None)
        self._set_system_state(SystemState.PROC)
        self._submit_turn(prompt)
        return True

    def _submit_turn(self, prompt: str) -> None:
        if self.gui is None:
            return
        self.turn_id += 1
        turn_id = self.turn_id
        self.status_store.submit_question(prompt)
        self.gui.add_user_message(prompt, turn_id)

        if not self.llm_manager.metrics.available:
            self._log_error("LLM unavailable")
            self.status_store.complete_turn(
                answer=None,
                success=False,
                error="model_unavailable",
            )
            self._set_system_state(SystemState.ERR)
            return

        self._start_generation(prompt, turn_id)

    def _submit_voice_transcript(self, transcript: str) -> None:
        if self._get_system_state() is not SystemState.PROC:
            return
        prompt = transcript.strip()
        if not prompt:
            self._enter_error("Speech recognition returned an empty transcript")
            return
        self._submit_turn(prompt)

    def _start_generation(self, prompt: str, turn_id: int) -> None:
        try:
            self.generation_thread = threading.Thread(
                target=self._generation_loop,
                args=(prompt, turn_id),
                name="ssai-generation-loop",
                daemon=True,
            )
            self.generation_thread.start()
        except RuntimeError as exc:
            self._enter_error(f"Could not start LLM generation: {exc}")

    def _generation_loop(self, prompt: str, turn_id: int) -> None:
        assert self.gui is not None
        generation_completed = False
        error_reported = False
        response_parts: list[str] = []

        try:
            for chunk in self.llm_manager.stream_response(
                prompt,
                on_metrics_update=self._update_model_status,
            ):
                if self.stop_event.is_set():
                    return
                response_parts.append(chunk)

            if not self.stop_event.is_set():
                generation_completed = True
                response = "".join(response_parts)
                self.status_store.complete_turn(
                    answer=response,
                    success=True,
                )
                tts_error = None
                audio_duration = None
                tts_started = time.perf_counter()
                try:
                    audio_path = generate_speech(response)
                    audio_duration = get_audio_duration_seconds(audio_path)
                except (OSError, RuntimeError, ValueError) as exc:
                    tts_error = f"Speech generation failed: {exc}"
                    self._log_error(tts_error)
                finally:
                    self.status_store.update_tts_time(
                        time.perf_counter() - tts_started
                    )
                self.gui.queue_model_response(
                    response,
                    audio_duration,
                    tts_error,
                    turn_id,
                )

        except (
            requests.RequestException,
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            subprocess.SubprocessError,
        ) as exc:
            self._log_error(f"LLM generation failed: {exc}")
            if not self.stop_event.is_set():
                self.gui.queue_model_error(turn_id)
                error_reported = True
            self._update_model_status(self.llm_manager.metrics)
            if not self.stop_event.is_set():
                self.status_store.complete_turn(
                    answer="".join(response_parts) or None,
                    success=False,
                    error="communication_error",
                )
        finally:
            if not generation_completed and not error_reported and not self.stop_event.is_set():
                self.gui.queue_model_error(turn_id)
                self.status_store.complete_turn(
                    answer="".join(response_parts) or None,
                    success=False,
                    error="generation_error",
                )

    def _response_ready(self, tts_ready: bool, turn_id: int) -> None:
        if not tts_ready:
            self._set_system_state(SystemState.ERR)
            return

        self._set_system_state(SystemState.SPK)
        self.playback_thread = threading.Thread(
            target=self._play_response,
            args=(turn_id,),
            name="ssai-voice-playback",
            daemon=True,
        )
        try:
            self.playback_thread.start()
        except RuntimeError as exc:
            if self.gui is not None:
                self.gui.finish_progressive_response(turn_id)
            self._enter_error(f"Could not start audio playback: {exc}")

    def _play_response(self, turn_id: int) -> None:
        try:
            play_output()
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            self.voice_events.put(
                ("playback_error", (turn_id, f"Audio playback failed: {exc}"))
            )
            return
        self.voice_events.put(("playback_complete", turn_id))

    def _get_system_state(self) -> SystemState:
        with self.state_lock:
            return self.system_state

    def _set_system_state(self, state: SystemState) -> None:
        with self.state_lock:
            self.system_state = state
        self.status_store.update_state(state.value)
        if self.gui is not None:
            self.gui.set_system_state(state.value)

    def _start_button_thread(self) -> None:
        self.button_thread = threading.Thread(
            target=self._button_loop,
            name="ssai-voice-button",
            daemon=True,
        )
        self.button_thread.start()

    def _button_loop(self) -> None:
        device = config.VOICE_BUTTON_INPUT_DEVICE
        while not self.stop_event.is_set():
            try:
                button_fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
            except OSError as exc:
                self.voice_events.put(("error", f"Button device unavailable: {exc}"))
                self.stop_event.wait(1.0)
                continue

            try:
                while not self.stop_event.is_set():
                    readable, _, _ = select.select([button_fd], [], [], 0.1)
                    if not readable:
                        continue
                    try:
                        data = os.read(button_fd, INPUT_EVENT.size)
                    except BlockingIOError:
                        continue
                    if not data:
                        raise RuntimeError("Button device disconnected.")
                    if len(data) != INPUT_EVENT.size:
                        raise RuntimeError("Incomplete event received from button device.")

                    _, _, event_type, code, value = INPUT_EVENT.unpack(data)
                    if event_type == EV_KEY and code == config.VOICE_BUTTON_KEY_CODE:
                        self.voice_events.put(
                            ("button", (value, self._get_system_state()))
                        )
            except OSError as exc:
                if not self.stop_event.is_set():
                    self.voice_events.put(
                        ("error", f"Button device disconnected or unreadable: {exc}")
                    )
            except RuntimeError as exc:
                if not self.stop_event.is_set():
                    self.voice_events.put(("error", str(exc)))
            finally:
                os.close(button_fd)

            if not self.stop_event.is_set():
                self.stop_event.wait(1.0)

    def _poll_voice_events(self) -> None:
        while True:
            try:
                event_type, payload = self.voice_events.get_nowait()
            except queue.Empty:
                break

            if event_type == "button":
                value, state_at_press = payload
                self._handle_button_event(value, state_at_press)
            elif event_type == "transcribed":
                self._submit_voice_transcript(str(payload))
            elif event_type == "playback_complete":
                turn_id = int(payload)
                if turn_id == self.turn_id:
                    if self.gui is not None:
                        self.gui.finish_progressive_response(turn_id)
                    if self._get_system_state() is SystemState.SPK:
                        self._set_system_state(SystemState.RDY)
            elif event_type == "playback_error":
                turn_id, message = payload
                if turn_id == self.turn_id:
                    if self.gui is not None:
                        self.gui.finish_progressive_response(turn_id)
                    self._enter_error(str(message))
            elif event_type == "error":
                self._enter_error(str(payload))

        process = self.voice_recording_process
        if (
            self._get_system_state() is SystemState.REC
            and process is not None
            and process.poll() is not None
        ):
            self._finish_voice_recording(process, stopped_by_release=False)

        if self.root is not None and self.root.winfo_exists():
            self.root.after(40, self._poll_voice_events)

    def _handle_button_event(
        self,
        value: int,
        state_at_event: SystemState,
    ) -> None:
        if value == 0:
            was_down = self.button_down
            self.button_down = False
            if (
                was_down
                and self._get_system_state() is SystemState.REC
            ):
                process = self.voice_recording_process
                if process is not None:
                    self._finish_voice_recording(process, stopped_by_release=True)
            return

        if value == 2:
            self.button_down = True
            return
        if value != 1:
            return

        if self.button_down:
            return
        self.button_down = True

        current_state = self._get_system_state()
        if state_at_event is not current_state:
            return
        if current_state is SystemState.ERR:
            self.last_error_message = None
            self._set_system_state(SystemState.RDY)
            return
        if current_state is not SystemState.RDY:
            return

        self._start_voice_recording()

    def _start_voice_recording(self) -> None:
        self.status_store.update_input("VOICE")
        self.status_store.update_stt_time(None)
        self.status_store.update_tts_time(None)
        self._set_system_state(SystemState.REC)
        try:
            self.voice_recording_process = start_button_recording()
        except (OSError, RuntimeError, ValueError) as exc:
            self.voice_recording_process = None
            self._enter_error(f"Recording failed: {exc}")

    def _finish_voice_recording(
        self,
        process: subprocess.Popen[str],
        stopped_by_release: bool,
    ) -> None:
        if self.voice_recording_process is not process:
            return
        self.voice_recording_process = None
        self._set_system_state(SystemState.PROC)
        if stopped_by_release:
            try:
                stop_button_recording(process)
            except OSError as exc:
                threading.Thread(
                    target=self._discard_recording_process,
                    args=(process,),
                    name="ssai-voice-recording-cleanup",
                    daemon=True,
                ).start()
                self._enter_error(f"Could not stop recording: {exc}")
                return

        try:
            self.voice_processing_thread = threading.Thread(
                target=self._transcribe_voice_recording,
                args=(process, stopped_by_release),
                name="ssai-voice-transcription",
                daemon=True,
            )
            self.voice_processing_thread.start()
        except RuntimeError as exc:
            self._enter_error(f"Could not start speech recognition: {exc}")

    def _transcribe_voice_recording(
        self,
        process: subprocess.Popen[str],
        stopped_by_release: bool,
    ) -> None:
        stt_started: float | None = None
        try:
            audio_path = finish_button_recording(process, stopped_by_release)
            stt_started = time.perf_counter()
            text = transcribe_audio(audio_path)
            if not text.strip():
                raise RuntimeError("Speech recognition returned an empty transcript")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            if stt_started is not None:
                self.status_store.update_stt_time(time.perf_counter() - stt_started)
            self.voice_events.put(("error", f"Voice processing failed: {exc}"))
            return
        assert stt_started is not None
        self.status_store.update_stt_time(time.perf_counter() - stt_started)
        self.voice_events.put(("transcribed", text))

    def _enter_error(self, message: str) -> None:
        process = self.voice_recording_process
        self.voice_recording_process = None
        if process is not None:
            try:
                stop_button_recording(process)
            except OSError as exc:
                message = f"{message}; recording cleanup failed: {exc}"
            threading.Thread(
                target=self._discard_recording_process,
                args=(process,),
                name="ssai-voice-recording-cleanup",
                daemon=True,
            ).start()
        self._set_system_state(SystemState.ERR)
        if message != self.last_error_message:
            self._log_error(message)
            self.last_error_message = message

    @staticmethod
    def _log_error(message: str) -> None:
        print(f"ERROR: {message}", file=sys.stderr)

    def _discard_recording_process(self, process: subprocess.Popen[str]) -> None:
        try:
            process.communicate()
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self.voice_events.put(
                ("error", f"Could not clean up recording process: {exc}")
            )

    def _start_background_thread(self) -> None:
        self.background_thread = threading.Thread(
            target=self._background_loop,
            name="ssai-monitor-loop",
            daemon=True,
        )
        self.background_thread.start()

    def _background_loop(self) -> None:
        while not self.stop_event.is_set():
            hardware = self.hardware_monitor.read_snapshot()
            self.status_store.update_hardware(hardware)
            self.stop_event.wait(config.HARDWARE_SAMPLE_INTERVAL)

    def _update_model_status(self, metrics: ModelMetrics) -> None:
        if not self.stop_event.is_set():
            self.status_store.update_model(metrics)

    def _request_exit(self) -> None:
        self.stop_event.set()
        if self.gui is not None:
            self.gui.cancel_progressive_response()
        if self.root is not None and self.root.winfo_exists():
            self.root.quit()

    def _request_restart(self) -> None:
        self.restart_requested = True
        self.llm_manager.clear_history()
        self._request_exit()

    def _restart_application(self) -> None:
        script_path = os.path.abspath(sys.argv[0])
        command = [sys.executable, script_path, *sys.argv[1:]]
        try:
            os.execv(sys.executable, command)
        except OSError as exc:
            self._log_error(f"Could not replace SSAI process: {exc}")
            try:
                subprocess.Popen(command)
            except OSError as fallback_exc:
                self._log_error(f"Could not start SSAI replacement: {fallback_exc}")

    def _install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, _signum, _frame) -> None:
        self.stop_event.set()
        if self.root is not None:
            try:
                self.root.after(0, self.root.quit)
            except tk.TclError:
                pass

    def _shutdown(self) -> None:
        self.stop_event.set()

        if self.background_thread and self.background_thread.is_alive():
            self.background_thread.join(timeout=1.0)

        process = self.voice_recording_process
        self.voice_recording_process = None
        if process is not None:
            try:
                stop_button_recording(process)
            except OSError as exc:
                print(f"Could not stop recording during shutdown: {exc}", file=sys.stderr)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.communicate()
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                print(f"Could not clean up recording during shutdown: {exc}", file=sys.stderr)

        if self.button_thread and self.button_thread.is_alive():
            self.button_thread.join(timeout=1.0)

        if self.voice_processing_thread and self.voice_processing_thread.is_alive():
            self.voice_processing_thread.join(timeout=1.0)

        if self.generation_thread and self.generation_thread.is_alive():
            self.generation_thread.join(timeout=config.GENERATION_SHUTDOWN_TIMEOUT)

        if self.restart_requested:
            self._stop_child_processes()
            if self.playback_thread and self.playback_thread.is_alive():
                self.playback_thread.join(timeout=1.0)

        self.status_store.clear()

        if self.root is not None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

    def _stop_child_processes(self) -> None:
        try:
            children = psutil.Process().children(recursive=True)
        except psutil.Error as exc:
            self._log_error(f"Could not find SSAI child processes: {exc}")
            return

        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass

        _, remaining = psutil.wait_procs(children, timeout=1.0)
        for child in remaining:
            try:
                child.kill()
            except psutil.Error:
                pass
        psutil.wait_procs(remaining, timeout=1.0)


def main() -> None:
    SSAIApplication().run()


if __name__ == "__main__":
    main()
