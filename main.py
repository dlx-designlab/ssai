from __future__ import annotations

import signal
import threading
import tkinter as tk

import requests

import config
from gui import ConversationGUI
from hardware_monitor import HardwareMonitor
from llm_manager import LLMManager, ModelMetrics
from status_store import StatusStore


class SSAIApplication:
    """Coordinates the GUI, local LLM, hardware monitor and SSH status data."""

    def __init__(self):
        self.stop_event = threading.Event()
        self.hardware_monitor = HardwareMonitor()
        self.llm_manager = LLMManager()
        self.status_store = StatusStore()

        self.background_thread: threading.Thread | None = None
        self.generation_thread: threading.Thread | None = None
        self.generation_active = False

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
            on_generation_finished=self._generation_finished,
        )

        try:
            self.root.mainloop()
        finally:
            self._shutdown()

    def _handle_prompt(self, prompt: str) -> bool:
        if self.stop_event.is_set() or self.gui is None:
            return False

        # Do not start a second generation while the current response is active.
        # The user may continue typing; Enter is accepted after the GUI has
        # finished displaying the previous response and its spacing.
        if self.generation_active:
            return False

        self.gui.add_user_message(prompt)
        self.gui.start_model_message()

        if not self.llm_manager.metrics.available:
            self.gui.show_model_error("Model unavailable")
            return True

        self._start_generation(prompt)
        return True

    def _start_generation(self, prompt: str) -> None:
        self.generation_active = True
        self.generation_thread = threading.Thread(
            target=self._generation_loop,
            args=(prompt,),
            name="ssai-generation-loop",
            daemon=True,
        )
        self.generation_thread.start()

    def _generation_loop(self, prompt: str) -> None:
        assert self.gui is not None
        generation_completed = False
        error_reported = False

        try:
            for chunk in self.llm_manager.stream_response(
                prompt,
                on_metrics_update=self._update_model_status,
            ):
                if self.stop_event.is_set():
                    return
                self.gui.queue_model_chunk(chunk)

            if not self.stop_event.is_set():
                self.gui.queue_model_complete()
                generation_completed = True

        except requests.RequestException:
            if not self.stop_event.is_set():
                self.gui.queue_model_error("Model error")
                error_reported = True
            self._update_model_status(self.llm_manager.metrics)
        finally:
            if not generation_completed and not error_reported and not self.stop_event.is_set():
                self.gui.queue_model_error("Model error")
                self.generation_active = False

    def _generation_finished(self) -> None:
        # Called by the GUI only after the final model event and spacing have
        # been rendered, preventing prompt ordering races.
        self.generation_active = False

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
        if self.root is not None and self.root.winfo_exists():
            self.root.quit()

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

        if self.generation_thread and self.generation_thread.is_alive():
            self.generation_thread.join(timeout=config.GENERATION_SHUTDOWN_TIMEOUT)

        self.status_store.clear()

        if self.root is not None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass


def main() -> None:
    SSAIApplication().run()


if __name__ == "__main__":
    main()
