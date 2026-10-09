from __future__ import annotations

import queue
import re
import time
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
        on_response_ready: Callable[[bool, int], None],
        on_toggle_context: Callable[[], bool],
        context_enabled: bool,
        on_restart: Callable[[], None],
    ):
        self.root = root
        self.on_submit = on_submit
        self.on_exit = on_exit
        self.on_response_ready = on_response_ready
        self.on_toggle_context = on_toggle_context
        self.context_enabled = context_enabled
        self.on_restart = on_restart
        self.restart_confirmation_after: str | None = None
        self.restart_confirmation_deadline: float | None = None
        self.restart_key_down = False
        self.response_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.follow_output = True
        self.turn_padding_active = False
        self.current_turn_id = 0
        self.progression_id = 0
        self.progress_turn_id: int | None = None
        self.progress_after_id: str | None = None
        self.progress_chunks: list[str] = []
        self.progress_due_seconds: list[float] = []
        self.progress_next_chunk = 0
        self.progress_started_at = 0.0
        self.input_enabled = True

        self._configure_window()
        self._build_widgets()
        self._disable_mouse_interaction()
        self._bind_keys()
        self.root.after_idle(self._focus_input)
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
            pady=max(1, config.DISPLAY_MARGIN // 2),
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
        self.context_label = tk.Label(
            transcript_frame,
            text="CTX" if self.context_enabled else "-----",
            bg=config.TEXT_BACKGROUND,
            fg=config.TEXT_FOREGROUND,
            font=(config.CHAT_FONT_FAMILY, max(1, config.CHAT_FONT_SIZE // 2)),
            takefocus=False,
        )
        self.context_label.place(
            relx=1.0,
            x=-config.DISPLAY_MARGIN,
            y=config.DISPLAY_MARGIN + config.CHAT_FONT_SIZE,
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

    def _disable_mouse_interaction(self) -> None:
        blocker_tag = "SSAI_MOUSE_BLOCKER"
        for sequence in (
            "<Motion>",
            "<Enter>",
            "<Leave>",
            "<ButtonPress>",
            "<ButtonRelease>",
            "<MouseWheel>",
        ):
            self.root.bind_class(blocker_tag, sequence, self._ignore_mouse_event)

        def disable_widget(widget: tk.Misc) -> None:
            widget.bindtags((blocker_tag, *widget.bindtags()))
            widget.configure(cursor="none")
            for child in widget.winfo_children():
                disable_widget(child)

        disable_widget(self.root)

    def _focus_input(self) -> None:
        if self.input_enabled:
            self.input_entry.focus_force()

    @staticmethod
    def _ignore_mouse_event(_event=None):
        return "break"

    def _bind_keys(self) -> None:
        self.input_entry.bind("<Return>", self._submit_from_entry)
        self.root.bind_all("<Up>", self._scroll_up)
        self.root.bind_all("<Down>", self._scroll_down)
        self.root.bind_all("<F1>", self._toggle_context)
        self.root.bind_all("<KeyPress-F4>", self._restart_key_pressed)
        self.root.bind_all("<KeyRelease-F4>", self._restart_key_released)

        if config.TECHNICIAN_EXIT_SHORTCUT:
            self.root.bind_all(config.TECHNICIAN_EXIT_SHORTCUT, self._technician_exit)

    def _toggle_context(self, _event=None):
        self.context_enabled = self.on_toggle_context()
        self.context_label.configure(
            text="CTX" if self.context_enabled else "-----"
        )
        return "break"

    def _restart_key_pressed(self, _event=None):
        if self.restart_key_down:
            return "break"
        self.restart_key_down = True

        if self.restart_confirmation_deadline is None:
            self._arm_restart_confirmation()
        else:
            deadline = self.restart_confirmation_deadline
            if self.restart_confirmation_after is not None:
                self.root.after_cancel(self.restart_confirmation_after)
            self.restart_confirmation_after = None
            self.restart_confirmation_deadline = None
            if time.monotonic() <= deadline:
                self.cancel_progressive_response()
                self.on_restart()
            else:
                self._arm_restart_confirmation()
        return "break"

    def _restart_key_released(self, _event=None):
        self.restart_key_down = False
        return "break"

    def _cancel_restart_confirmation(self) -> None:
        self.restart_confirmation_after = None
        self.restart_confirmation_deadline = None

    def _arm_restart_confirmation(self) -> None:
        self.restart_confirmation_deadline = (
            time.monotonic() + config.RESTART_CONFIRM_WINDOW_SEC
        )
        self.restart_confirmation_after = self.root.after(
            int(config.RESTART_CONFIRM_WINDOW_SEC * 1000),
            self._cancel_restart_confirmation,
        )

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
            self.root.after_idle(self._focus_input)
        else:
            self.input_entry.delete(0, "end")
            self.input_entry.configure(state="disabled")

    def add_user_message(self, text: str, turn_id: int) -> None:
        self.cancel_progressive_response()
        self.current_turn_id = turn_id
        self._remove_turn_position_padding()
        self.follow_output = True
        self.transcript.configure(state="normal")
        turn_start = self.transcript.index("end-1c")
        self.transcript.insert("end", f"{config.USER_PREFIX}{text}\n")
        padding_start = self.transcript.index("end-1c")
        line_height = int(
            self.transcript.tk.call(
                "font", "metrics", self.transcript.cget("font"), "-linespace"
            )
        )
        padding_lines = max(
            1,
            (self.transcript.winfo_height() + line_height - 1) // line_height,
        )
        self.transcript.insert("end", "\n" * padding_lines)
        self.transcript.mark_set("turn_position_padding", padding_start)
        self.turn_padding_active = True
        self.transcript.configure(state="disabled")
        self.transcript.yview(turn_start)
        self._update_scroll_indicator()

    def queue_model_response(
        self,
        text: str,
        audio_duration: float | None,
        tts_error: str | None,
        turn_id: int,
    ) -> None:
        self.response_queue.put(
            ("response", (turn_id, text, audio_duration, tts_error))
        )

    def queue_model_error(self, turn_id: int) -> None:
        self.response_queue.put(("error", turn_id))

    def clear_conversation(self) -> None:
        self.cancel_progressive_response()
        self._remove_turn_position_padding()
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
                    turn_id = payload
                    if turn_id == self.current_turn_id:
                        self.on_response_ready(False, turn_id)
                elif event_type == "response":
                    turn_id, text, audio_duration, tts_error = payload
                    if turn_id != self.current_turn_id:
                        continue
                    if tts_error is not None or audio_duration is None:
                        self.cancel_progressive_response()
                        self._append_transcript(f"{config.MODEL_PREFIX}{text}")
                        self._finish_model_spacing()
                        self.on_response_ready(False, turn_id)
                    else:
                        self._start_progressive_response(
                            text,
                            audio_duration,
                            turn_id,
                        )
                        self.on_response_ready(True, turn_id)

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
        self._remove_turn_position_padding()
        self.transcript.configure(state="normal")
        self.transcript.insert("end", text)
        self.transcript.configure(state="disabled")

        if self.follow_output:
            self.transcript.see("end")
        self._update_scroll_indicator()

    def _start_progressive_response(
        self,
        text: str,
        audio_duration: float,
        turn_id: int,
    ) -> None:
        self.cancel_progressive_response()
        self.progress_turn_id = turn_id
        self.progress_started_at = time.perf_counter()
        self.progress_chunks, self.progress_due_seconds = self._make_progress_chunks(
            text,
            audio_duration,
        )

        if not self.progress_chunks:
            self._append_transcript(config.MODEL_PREFIX)
            return

        self._append_transcript(
            f"{config.MODEL_PREFIX}{self.progress_chunks[0]}"
        )
        self.progress_next_chunk = 1
        self._schedule_progress_chunk(turn_id, self.progression_id)

    @staticmethod
    def _make_progress_chunks(
        text: str,
        audio_duration: float,
    ) -> tuple[list[str], list[float]]:
        words = re.findall(r"\S+\s*", text)
        if not words:
            return [], []

        group_size = max(1, config.TEXT_AUDIO_WORDS_PER_GROUP)
        chunks = [
            "".join(words[index:index + group_size])
            for index in range(0, len(words), group_size)
        ]
        weights = []
        for chunk in chunks:
            weight = 0.0
            for word in re.findall(r"\S+", chunk):
                weight += max(1, len(word))
                if word.endswith((".", "!", "?")):
                    weight += 4
                elif word.endswith((",", ";", ":")):
                    weight += 2
            weights.append(weight)

        total_weight = sum(weights)
        cumulative_weight = 0.0
        due_seconds = []
        for weight in weights:
            cumulative_weight += weight
            due_seconds.append(audio_duration * cumulative_weight / total_weight)
        return chunks, due_seconds

    def _schedule_progress_chunk(self, turn_id: int, progression_id: int) -> None:
        if (
            self.progress_turn_id != turn_id
            or self.progression_id != progression_id
            or self.progress_next_chunk >= len(self.progress_chunks)
        ):
            return

        lead_seconds = config.TEXT_AUDIO_LEAD_MS / 1000
        target = (
            self.progress_started_at
            + self.progress_due_seconds[self.progress_next_chunk]
            - lead_seconds
        )
        delay_ms = max(0, round((target - time.perf_counter()) * 1000))
        self.progress_after_id = self.root.after(
            delay_ms,
            lambda: self._reveal_progress_chunk(turn_id, progression_id),
        )

    def _reveal_progress_chunk(self, turn_id: int, progression_id: int) -> None:
        self.progress_after_id = None
        if (
            self.progress_turn_id != turn_id
            or self.current_turn_id != turn_id
            or self.progression_id != progression_id
            or self.progress_next_chunk >= len(self.progress_chunks)
        ):
            return

        chunk = self.progress_chunks[self.progress_next_chunk]
        self.progress_next_chunk += 1
        self._append_transcript(chunk)
        self._schedule_progress_chunk(turn_id, progression_id)

    def finish_progressive_response(self, turn_id: int) -> None:
        if (
            turn_id != self.current_turn_id
            or self.progress_turn_id != turn_id
        ):
            return

        remaining = self.progress_chunks[self.progress_next_chunk:]
        self.cancel_progressive_response()
        for chunk in remaining:
            self._append_transcript(chunk)
        self._finish_model_spacing()

    def cancel_progressive_response(self) -> None:
        self.progression_id += 1
        if self.progress_after_id is not None:
            try:
                self.root.after_cancel(self.progress_after_id)
            except tk.TclError:
                pass
        self.progress_after_id = None
        self.progress_turn_id = None
        self.progress_chunks = []
        self.progress_due_seconds = []
        self.progress_next_chunk = 0

    def _remove_turn_position_padding(self) -> None:
        if not self.turn_padding_active:
            return

        self.transcript.configure(state="normal")
        self.transcript.delete("turn_position_padding", "end-1c")
        self.transcript.mark_unset("turn_position_padding")
        self.transcript.configure(state="disabled")
        self.turn_padding_active = False

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
