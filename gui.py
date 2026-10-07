from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable

import config


class ConversationGUI:
    """Simple full-screen conversation interface for the local Pi display."""

    def __init__(
        self,
        root: tk.Tk,
        on_submit: Callable[[str], bool],
        on_exit: Callable[[], None],
        on_response_ready: Callable[[bool], None],
    ):
        self.root = root
        self.on_submit = on_submit
        self.on_exit = on_exit
        self.on_response_ready = on_response_ready
        self.response_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.follow_output = True
        self.input_enabled = True

        self._configure_window()
        self._build_widgets()
        self._bind_keys()
        self.root.after(config.GUI_STREAM_POLL_MS, self._process_response_queue)

    def _configure_window(self) -> None:
        self.root.title(config.PROGRAM_NAME)
        self.root.configure(bg=config.WINDOW_BACKGROUND)

        if config.FULLSCREEN:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry(f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")

        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def _build_widgets(self) -> None:
        font = (config.CHAT_FONT_FAMILY, config.CHAT_FONT_SIZE)

        input_frame = tk.Frame(self.root, bg=config.INPUT_BACKGROUND)
        input_frame.pack(fill="x", side="bottom")

        transcript_frame = tk.Frame(self.root, bg=config.TEXT_BACKGROUND)
        transcript_frame.pack(fill="both", expand=True)

        self.transcript = tk.Text(
            transcript_frame,
            wrap="word",
            bg=config.TEXT_BACKGROUND,
            fg=config.TEXT_FOREGROUND,
            insertbackground=config.TEXT_FOREGROUND,
            font=font,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=config.DISPLAY_MARGIN,
            pady=config.DISPLAY_MARGIN,
            state="disabled",
            takefocus=False,
        )
        self.scroll_indicator = tk.Canvas(
            transcript_frame,
            width=8,
            bg=config.TEXT_BACKGROUND,
            highlightthickness=0,
            borderwidth=0,
            takefocus=False,
        )

        self.scroll_indicator.pack(fill="y", side="right")
        self.transcript.pack(fill="both", expand=True)
        self.scroll_indicator.bind("<Configure>", self._update_scroll_indicator)
        self.state_label = tk.Label(
            transcript_frame,
            text="RDY",
            bg=config.TEXT_BACKGROUND,
            fg=config.TEXT_FOREGROUND,
            font=font,
            takefocus=False,
        )
        self.state_label.place(
            relx=1.0,
            x=-config.DISPLAY_MARGIN,
            y=config.DISPLAY_MARGIN,
            anchor="ne",
        )

        self.input_prefix = tk.Label(
            input_frame,
            text=config.USER_PREFIX,
            bg=config.INPUT_BACKGROUND,
            fg=config.INPUT_FOREGROUND,
            font=font,
            padx=config.DISPLAY_MARGIN,
            pady=4,
        )
        self.input_prefix.pack(side="left")

        self.input_entry = tk.Entry(
            input_frame,
            bg=config.INPUT_BACKGROUND,
            fg=config.INPUT_FOREGROUND,
            insertbackground=config.INPUT_FOREGROUND,
            font=font,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, config.DISPLAY_MARGIN), pady=4)
        self.input_entry.focus_set()

    def _bind_keys(self) -> None:
        self.input_entry.bind("<Return>", self._submit_from_entry)
        self.root.bind_all("<Up>", self._scroll_up)
        self.root.bind_all("<Down>", self._scroll_down)

        if config.TECHNICIAN_EXIT_SHORTCUT:
            self.root.bind_all(config.TECHNICIAN_EXIT_SHORTCUT, self._technician_exit)

    def _submit_from_entry(self, _event=None):
        if not self.input_enabled:
            self.input_entry.delete(0, "end")
            return "break"

        prompt = self.input_entry.get().strip()
        if not prompt:
            return "break"

        accepted = self.on_submit(prompt)
        if accepted or not self.input_enabled:
            self.input_entry.delete(0, "end")
        return "break"

    def set_system_state(self, state: str) -> None:
        self.state_label.configure(text=state)
        self.input_enabled = state == "RDY"
        if self.input_enabled:
            self.input_entry.configure(state="normal")
            self.input_entry.focus_set()
        else:
            self.input_entry.delete(0, "end")
            self.input_entry.configure(state="disabled")

    def add_user_message(self, text: str) -> None:
        self._append_transcript(f"{config.USER_PREFIX}{text}\n")

    def queue_model_response(self, text: str, tts_error: str | None = None) -> None:
        self.response_queue.put(("response", (text, tts_error)))

    def queue_model_error(self) -> None:
        self.response_queue.put(("error", None))

    def clear_conversation(self) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.follow_output = True
        self._update_scroll_indicator()

    def _process_response_queue(self) -> None:
        try:
            while True:
                event_type, payload = self.response_queue.get_nowait()

                if event_type == "error":
                    self.on_response_ready(False)
                elif event_type == "response":
                    text, tts_error = payload
                    self._append_transcript(f"{config.MODEL_PREFIX}{text}")
                    self._finish_model_spacing()
                    self.on_response_ready(tts_error is None)

        except queue.Empty:
            pass

        if self.root.winfo_exists():
            self.root.after(config.GUI_STREAM_POLL_MS, self._process_response_queue)

    def show_voice_result(self, text: str) -> None:
        self._append_transcript(f"VOICE: {text or '(no speech recognized)'}\n")

    def _finish_model_spacing(self) -> None:
        # N blank lines between the model response and the next YOU line require
        # N + 1 newline characters after the response text.
        newline_count = config.BLANK_LINES_AFTER_MODEL + 1
        self._append_transcript(
            f"\n{config.CONVERSATION_SEPARATOR}\n" + "\n" * newline_count
        )

    def _append_transcript(self, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", text)
        self.transcript.configure(state="disabled")

        if self.follow_output:
            self.transcript.see("end")
        self._update_scroll_indicator()

    def _update_scroll_indicator(self, _event=None) -> None:
        top, bottom = self.transcript.yview()
        position = (top + bottom) / 2
        height = self.scroll_indicator.winfo_height()
        radius = 3
        margin = radius
        center_y = margin + position * max(height - 2 * margin, 0)
        center_y = max(radius, min(center_y, max(height - radius, radius)))

        self.scroll_indicator.delete("all")
        self.scroll_indicator.create_oval(
            4 - radius,
            center_y - radius,
            4 + radius,
            center_y + radius,
            fill="white",
            outline="white",
        )

    def _scroll_up(self, _event=None):
        self.follow_output = False
        self.transcript.yview_scroll(-config.SCROLL_LINES_PER_KEYPRESS, "units")
        self._update_scroll_indicator()
        return "break"

    def _scroll_down(self, _event=None):
        self.transcript.yview_scroll(config.SCROLL_LINES_PER_KEYPRESS, "units")
        self.root.update_idletasks()
        _, bottom = self.transcript.yview()
        if bottom >= 0.999:
            self.follow_output = True
            self.transcript.see("end")
        self._update_scroll_indicator()
        return "break"

    def _technician_exit(self, _event=None):
        self.on_exit()
        return "break"
