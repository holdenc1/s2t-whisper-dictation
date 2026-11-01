"""Main window: live status, level meter, full config editor with hover tooltips."""

import time
import tkinter as tk
from copy import deepcopy
from tkinter import ttk
from typing import Callable, Optional

import customtkinter as ctk
import sounddevice as sd

from audio import list_audio_devices
from config import Config, AVAILABLE_MODELS

LANGUAGES = ["auto", "en", "es", "fr", "de", "it", "pt", "nl", "ja", "zh", "ko", "ru", "ar", "hi"]
MODES = ["push_to_talk", "toggle_to_talk", "voice_activation"]
PTT_HOTKEYS = [
    "alt+`",
    "ctrl+`",
    "ctrl+space",
    "scroll lock",
    "pause",
    "caps lock",
    "f13",
    "f14",
    "f15",
    "f16",
    "f17",
    "f18",
    "f19",
    "f20",
]

STATUS_COLORS = {
    "idle": "#4CAF50",
    "recording": "#F44336",
    "processing": "#FF9800",
}


class Tooltip:
    """Lightweight hover tooltip — appears after a short delay, follows the widget."""

    def __init__(self, widget, text: str, delay_ms: int = 500):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            background="#2b2b2b",
            foreground="#e6e6e6",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            wraplength=360,
            font=("Segoe UI", 9),
        )
        label.pack()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def add_tooltip(widget, text: str):
    Tooltip(widget, text)


class SplashScreen(tk.Toplevel):
    """Borderless splash window shown during model load. Lightweight tkinter
    so it's instantly visible before any CTk theming is initialized."""

    BG = "#1e1e1e"
    ACCENT = "#1f6aa5"
    FG_TITLE = "#e6e6e6"
    FG_DIM = "#888888"
    FG_STATUS = "#9bb6c5"
    FG_ERROR = "#e57373"

    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=self.ACCENT)

        w, h = 440, 210
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        inner = tk.Frame(self, bg=self.BG)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        tk.Label(inner, text="Speech-to-Text", bg=self.BG, fg=self.FG_TITLE,
                 font=("Segoe UI", 20, "bold")).pack(pady=(35, 0))
        tk.Label(inner, text="Local Whisper Dictation", bg=self.BG, fg=self.FG_DIM,
                 font=("Segoe UI", 9)).pack(pady=(0, 18))

        self.status_label = tk.Label(inner, text="Starting…", bg=self.BG,
                                      fg=self.FG_STATUS, font=("Segoe UI", 10))
        self.status_label.pack()

        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure("Splash.Horizontal.TProgressbar",
                        troughcolor=self.BG, background=self.ACCENT,
                        bordercolor=self.BG, lightcolor=self.ACCENT,
                        darkcolor=self.ACCENT)
        self.progress = ttk.Progressbar(inner, mode="indeterminate", length=340,
                                         style="Splash.Horizontal.TProgressbar")
        self.progress.pack(pady=(15, 10))
        self.progress.start(12)

        self.update_idletasks()

    def set_status(self, text: str):
        try:
            self.status_label.config(text=text, fg=self.FG_STATUS)
            self.update_idletasks()
        except Exception:
            pass

    def show_error(self, message: str):
        try:
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)
            self.status_label.config(text=message, fg=self.FG_ERROR)
            self.update_idletasks()
        except Exception:
            pass

    def close(self):
        try:
            self.progress.stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


class MainWindow(ctk.CTk):
    """Single-window UI: live status + level meter + tabbed config editor."""

    def __init__(
        self,
        config: Config,
        get_status: Callable[[], str],
        get_level: Callable[[], float],
        on_apply: Callable[[Config], None],
        on_quit: Callable[[], None],
        ptt_tick: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config = config
        self.get_status = get_status
        self.get_level = get_level
        self.on_apply = on_apply
        self.on_quit = on_quit
        self.ptt_tick = ptt_tick

        self._displayed_level = 0.0
        self._device_options: list[tuple[str, Optional[int]]] = []

        self.title("Speech-to-Text")
        self.geometry("640x820")
        self.minsize(580, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_level_meter()
        self._build_transcript_log()
        self._build_tabs()
        self._build_buttons()

        self._tick()

    # ---------------- Header ----------------

    def _build_header(self):
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=10, pady=(10, 5))

        self.status_pill = ctk.CTkLabel(
            header,
            text="● idle",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=STATUS_COLORS["idle"],
            width=140,
        )
        self.status_pill.pack(side="left", padx=10, pady=10)
        add_tooltip(self.status_pill, "Live recording state.\n"
                                       "Green = idle, Red = recording, Orange = transcribing.")

        info_frame = ctk.CTkFrame(header, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=10)

        self.mode_label = ctk.CTkLabel(info_frame, text="Mode: —", anchor="w")
        self.mode_label.pack(fill="x")
        self.model_label = ctk.CTkLabel(info_frame, text="Model: —", anchor="w")
        self.model_label.pack(fill="x")
        self.device_label = ctk.CTkLabel(info_frame, text="Device: —", anchor="w")
        self.device_label.pack(fill="x")

    # ---------------- Level meter ----------------

    def _build_level_meter(self):
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=10, pady=5)
        label = ctk.CTkLabel(frame, text="Mic Level")
        label.pack(anchor="w", padx=10, pady=(8, 2))
        self.level_bar = ctk.CTkProgressBar(frame, height=18)
        self.level_bar.set(0)
        self.level_bar.pack(fill="x", padx=10, pady=(0, 10))
        add_tooltip(self.level_bar,
                    "Real-time microphone input level (RMS).\n"
                    "If this stays at zero while you speak, your input device is wrong "
                    "or your mic is muted.")

    # ---------------- Transcript log ----------------

    def _build_transcript_log(self):
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=10, pady=5)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(header, text="Recent Transcriptions",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        clear_btn = ctk.CTkButton(header, text="Clear", width=60, height=24,
                                  fg_color="gray", command=self.clear_transcripts)
        clear_btn.pack(side="right")
        add_tooltip(clear_btn, "Clear the transcription log (does not affect what was already typed).")

        self.transcript_log = ctk.CTkTextbox(frame, height=140, wrap="word")
        self.transcript_log.pack(fill="x", padx=10, pady=(0, 10))
        self.transcript_log.configure(state="disabled")
        add_tooltip(self.transcript_log,
                    "Log of recent transcriptions in chronological order.\n"
                    "Useful for verifying what was actually pasted, especially\n"
                    "when the paste landed in the wrong window.")

    def add_transcription(self, text: str):
        """Append a transcription to the log. Call via window.after(0, ...) from worker threads."""
        if not text:
            return
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}]  {text.strip()}\n"
        try:
            self.transcript_log.configure(state="normal")
            self.transcript_log.insert("end", line)
            # Cap at ~200 lines to keep the widget responsive
            content = self.transcript_log.get("1.0", "end")
            lines = content.splitlines()
            if len(lines) > 200:
                self.transcript_log.delete("1.0", f"{len(lines) - 200}.0")
            self.transcript_log.see("end")
            self.transcript_log.configure(state="disabled")
        except Exception as e:
            print(f"Transcript log error: {e}")

    def clear_transcripts(self):
        try:
            self.transcript_log.configure(state="normal")
            self.transcript_log.delete("1.0", "end")
            self.transcript_log.configure(state="disabled")
        except Exception:
            pass

    # ---------------- Tabs ----------------

    def _build_tabs(self):
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=5)
        for name in ("Model", "Audio", "Mode & VAD", "Text"):
            tabs.add(name)

        self._build_model_tab(tabs.tab("Model"))
        self._build_audio_tab(tabs.tab("Audio"))
        self._build_mode_tab(tabs.tab("Mode & VAD"))
        self._build_text_tab(tabs.tab("Text"))

    # ---- Model ----

    def _build_model_tab(self, parent):
        row = self._row(parent, "Whisper Model:")
        self.model_var = ctk.StringVar(value=self.config.model)
        menu = ctk.CTkOptionMenu(row, variable=self.model_var, values=AVAILABLE_MODELS, width=180)
        menu.pack(side="left", padx=5)
        add_tooltip(menu,
                    "Whisper model size. Larger = more accurate, slower, more VRAM/RAM.\n"
                    "  tiny   ~75 MB,  fastest, lowest accuracy\n"
                    "  base   ~140 MB\n"
                    "  small  ~460 MB,  good speed/accuracy balance\n"
                    "  medium ~1.5 GB\n"
                    "  large  ~3 GB,    most accurate, slowest")

        row = self._row(parent, "Language:")
        lang = self.config.language or "auto"
        if lang not in LANGUAGES:
            lang = "auto"
        self.lang_var = ctk.StringVar(value=lang)
        menu = ctk.CTkOptionMenu(row, variable=self.lang_var, values=LANGUAGES, width=180)
        menu.pack(side="left", padx=5)
        add_tooltip(menu,
                    "Language hint for Whisper.\n"
                    "  auto = let Whisper detect (slower, less reliable)\n"
                    "  en/es/fr/... = ISO 639-1 code\n"
                    "Pinning the language is faster and more accurate when you "
                    "always speak the same language.")

        row = self._row(parent, "Word List:")
        self.vocab_var = ctk.StringVar(value=", ".join(self.config.vocabulary))
        entry = ctk.CTkEntry(row, textvariable=self.vocab_var, width=380)
        entry.pack(side="left", padx=5)
        add_tooltip(entry,
                    "Names and terms Whisper should expect, separated by commas,\n"
                    "spelled the way you want them pasted. Example:\n"
                    "  WBTO, AMWIC, AMRAC, Clackamas\n"
                    "Helps with acronyms and names Whisper does not know.\n"
                    "Keep it to a few dozen words.")

    # ---- Audio ----

    def _build_audio_tab(self, parent):
        self._device_options = [("Default (system)", None)]
        try:
            for idx, dev in list_audio_devices():
                self._device_options.append((f"[{idx}] {dev['name']}", idx))
        except Exception as e:
            print(f"Could not enumerate audio devices: {e}")

        row = self._row(parent, "Microphone:")
        labels = [label for label, _ in self._device_options]
        current_label = next(
            (label for label, idx in self._device_options if idx == self.config.audio.device),
            labels[0],
        )
        self.device_var = ctk.StringVar(value=current_label)
        menu = ctk.CTkOptionMenu(row, variable=self.device_var, values=labels, width=380)
        menu.pack(side="left", padx=5)
        add_tooltip(menu,
                    "Microphone to capture from. 'Default (system)' follows your\n"
                    "Windows default input. Pick a specific device if your default\n"
                    "is wrong or to lock to a particular mic.")

        row = self._row(parent, "Beep Volume:")
        self.beep_var = ctk.DoubleVar(value=self.config.audio.beep_volume)
        slider = ctk.CTkSlider(row, from_=0, to=1, variable=self.beep_var, width=240)
        slider.pack(side="left", padx=5)
        add_tooltip(slider,
                    "Volume of the start/stop beep cues.\n"
                    "Set to 0 to disable beeps entirely.")

    # ---- Mode & VAD ----

    def _build_mode_tab(self, parent):
        row = self._row(parent, "Recording Mode:")
        self.mode_var = ctk.StringVar(value=self.config.mode)
        menu = ctk.CTkOptionMenu(row, variable=self.mode_var, values=MODES, width=200)
        menu.pack(side="left", padx=5)
        add_tooltip(menu,
                    "How recording is triggered:\n"
                    "  push_to_talk    — hold the PTT key while speaking\n"
                    "  toggle_to_talk  — press once to start, again to stop\n"
                    "  voice_activation — auto-record whenever speech is detected")

        ptt_values = list(PTT_HOTKEYS)
        current_ptt = self.config.hotkeys.push_to_talk
        if current_ptt not in ptt_values:
            ptt_values.insert(0, current_ptt)
        row = self._row(parent, "PTT Hotkey:")
        self.ptt_hotkey_var = ctk.StringVar(value=current_ptt)
        ptt_menu = ctk.CTkOptionMenu(row, variable=self.ptt_hotkey_var, values=ptt_values, width=200)
        ptt_menu.pack(side="left", padx=5)
        add_tooltip(ptt_menu,
                    "Key (or combo) used for push-to-talk / toggle-to-talk.\n"
                    "F13–F20 are ideal — they have no OS side-effects.\n"
                    "Scroll Lock and Pause also work well.\n"
                    "Modifier combos (alt+`, ctrl+space) work but may\n"
                    "conflict with other apps.")

        ctk.CTkLabel(parent, text="Voice Activation",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(15, 5))

        row = self._row(parent, "Speech Threshold:")
        self.vad_threshold_var = ctk.DoubleVar(value=self.config.vad.speech_threshold)
        slider = ctk.CTkSlider(row, from_=0.5, to=10.0, variable=self.vad_threshold_var, width=200)
        slider.pack(side="left", padx=5)
        self.vad_threshold_label = ctk.CTkLabel(row, text=f"{self.vad_threshold_var.get():.1f}", width=40)
        self.vad_threshold_label.pack(side="left")
        self.vad_threshold_var.trace_add(
            "write",
            lambda *_: self.vad_threshold_label.configure(text=f"{self.vad_threshold_var.get():.1f}"),
        )
        add_tooltip(slider,
                    "How loud a sound needs to be to count as speech (RMS × 100).\n"
                    "Lower = more sensitive (may trigger on background noise).\n"
                    "Higher = needs louder/clearer speech to start recording.\n"
                    "Watch the Mic Level bar above to calibrate.")

        row = self._row(parent, "Silence Duration:")
        self.vad_silence_var = ctk.DoubleVar(value=self.config.vad.silence_duration)
        slider = ctk.CTkSlider(row, from_=0.2, to=5.0, variable=self.vad_silence_var, width=200)
        slider.pack(side="left", padx=5)
        self.vad_silence_label = ctk.CTkLabel(row, text=f"{self.vad_silence_var.get():.1f}", width=40)
        self.vad_silence_label.pack(side="left")
        self.vad_silence_var.trace_add(
            "write",
            lambda *_: self.vad_silence_label.configure(text=f"{self.vad_silence_var.get():.1f}"),
        )
        add_tooltip(slider,
                    "Seconds of silence required to end a VAD utterance.\n"
                    "Shorter = transcribes faster but may cut off pauses.\n"
                    "Longer = waits through pauses but feels laggy.")

    # ---- Text ----

    def _build_text_tab(self, parent):
        self.tp_enabled_var = ctk.BooleanVar(value=self.config.text_processing.enabled)
        cb = ctk.CTkCheckBox(parent, text="Enable text processing", variable=self.tp_enabled_var)
        cb.pack(anchor="w", padx=15, pady=(10, 5))
        add_tooltip(cb,
                    "Master switch. When off, transcription text is pasted exactly\n"
                    "as Whisper produces it (including filler words, no spacing fixes).")

        opts = [
            (self.config.text_processing.remove_fillers, "remove_fillers",
             "Remove filler words (um, uh, etc.)",
             "Strips hesitation sounds: um, uh, er, erm, ah.\n"
             "Real words such as 'actually' and 'you know' are kept, and so are\n"
             "acronyms like ER."),
            (self.config.text_processing.punctuation_commands, "punctuation_commands",
             "Punctuation commands (\"period\" → \".\")",
             "Spoken commands become punctuation:\n"
             "  'period' → .   'comma' → ,   'question mark' → ?\n"
             "  'colon' → :    'semicolon' → ;   'dash' → -\n"
             "  'open quote' / 'close quote' → \"\n"
             "  'open paren' / 'close paren' → ( )"),
            (self.config.text_processing.newline_commands, "newline_commands",
             "Newline commands (\"new line\" / \"new paragraph\")",
             "'new line', 'newline', 'new paragraph', 'paragraph break',\n"
             "'line break' all insert a newline."),
            (self.config.text_processing.informal_to_formal, "informal_to_formal",
             "Informal → Formal (\"gonna\" → \"going to\")",
             "Expands contractions: gonna→going to, wanna→want to, gotta→got to,\n"
             "kinda→kind of, dunno→don't know, lemme→let me, gimme→give me, y'all→you all."),
            (self.config.text_processing.fix_capitalization, "fix_capitalization",
             "Fix capitalization",
             "Capitalizes the first letter of each sentence and standalone 'i' → 'I'."),
            (self.config.text_processing.ensure_sentence_spacing, "ensure_sentence_spacing",
             "Ensure space after . ! ?",
             "Adds a missing space between two sentences: 'word.Next' → 'word. Next'.\n"
             "Numbers (3.5, $1.50), web addresses (wbto.partners) and\n"
             "abbreviations (a.m., e.g.) are left alone."),
            (self.config.text_processing.add_trailing_space, "add_trailing_space",
             "Add trailing space (separates consecutive dictations)",
             "Appends a space at the end of every transcription so that the next\n"
             "dictation doesn't run into the previous one. Recommended ON.\n"
             "Without this, two utterances paste as 'First.Second.'"),
            (self.config.text_processing.collapse_repeated_words, "collapse_repeated_words",
             "Collapse repeated words (\"the the\" → \"the\")",
             "Removes immediate word repetitions. Useful if you stutter or restart.\n"
             "Off by default — can mangle intentional repeats like 'very very'."),
        ]
        self._tp_vars: dict[str, ctk.BooleanVar] = {}
        for value, key, label, tip in opts:
            var = ctk.BooleanVar(value=value)
            self._tp_vars[key] = var
            cb = ctk.CTkCheckBox(parent, text=label, variable=var)
            cb.pack(anchor="w", padx=35, pady=2)
            add_tooltip(cb, tip)

    # ---------------- Buttons ----------------

    def _build_buttons(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=10)

        save = ctk.CTkButton(frame, text="Save & Apply", command=self._on_save, width=140)
        save.pack(side="right", padx=5)
        add_tooltip(save, "Save the form values to config.yaml and apply them live.\n"
                          "Model swap, device change, hotkey re-bind all happen immediately.")

        reload_btn = ctk.CTkButton(frame, text="Reload", command=self._reload_from_config,
                                   fg_color="gray", width=100)
        reload_btn.pack(side="right", padx=5)
        add_tooltip(reload_btn, "Discard unsaved form changes and re-populate from\n"
                                "the currently applied config.")

        quit_btn = ctk.CTkButton(frame, text="Quit", command=self._on_quit_clicked,
                                 fg_color="#7a2222", hover_color="#5a1818", width=80)
        quit_btn.pack(side="left", padx=5)
        add_tooltip(quit_btn, "Quit the app entirely. Closes the tray icon and "
                              "unhooks all hotkeys.\n"
                              "(The X button in the title bar only hides to tray.)")

    # ---------------- Helpers ----------------

    def _row(self, parent, label: str) -> ctk.CTkFrame:
        """Create a label + horizontal slot. Caller fills the returned frame."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(frame, text=label, width=140, anchor="w").pack(side="left")
        return frame

    def _selected_device(self) -> Optional[int]:
        label = self.device_var.get()
        for lbl, idx in self._device_options:
            if lbl == label:
                return idx
        return None

    def _device_name(self, idx: Optional[int]) -> str:
        if idx is None:
            try:
                default_idx = sd.default.device[0]
                if default_idx is not None and default_idx >= 0:
                    return f"Default ({sd.query_devices(default_idx)['name']})"
            except Exception:
                pass
            return "Default"
        try:
            return sd.query_devices(idx)["name"]
        except Exception:
            return f"[{idx}]"

    # ---------------- Save / Reload ----------------

    def _build_config_from_form(self) -> Config:
        new = deepcopy(self.config)
        new.model = self.model_var.get()
        lang = self.lang_var.get()
        new.language = None if lang == "auto" else lang
        new.vocabulary = [w.strip() for w in self.vocab_var.get().split(",") if w.strip()]
        new.mode = self.mode_var.get()
        new.audio.device = self._selected_device()
        new.audio.beep_volume = float(self.beep_var.get())
        new.vad.speech_threshold = float(self.vad_threshold_var.get())
        new.vad.silence_duration = float(self.vad_silence_var.get())
        new.hotkeys.push_to_talk = self.ptt_hotkey_var.get()
        new.text_processing.enabled = self.tp_enabled_var.get()
        new.text_processing.remove_fillers = self._tp_vars["remove_fillers"].get()
        new.text_processing.punctuation_commands = self._tp_vars["punctuation_commands"].get()
        new.text_processing.newline_commands = self._tp_vars["newline_commands"].get()
        new.text_processing.informal_to_formal = self._tp_vars["informal_to_formal"].get()
        new.text_processing.fix_capitalization = self._tp_vars["fix_capitalization"].get()
        new.text_processing.ensure_sentence_spacing = self._tp_vars["ensure_sentence_spacing"].get()
        new.text_processing.add_trailing_space = self._tp_vars["add_trailing_space"].get()
        new.text_processing.collapse_repeated_words = self._tp_vars["collapse_repeated_words"].get()
        return new

    def _on_save(self):
        new_config = self._build_config_from_form()
        try:
            self.on_apply(new_config)
        except Exception as e:
            print(f"Error applying config: {e}")
            return
        self.config = new_config
        # on_apply keeps the old mic if the new one would not open; show what
        # is really in use rather than the pick that failed.
        self._reload_from_config()

    def _reload_from_config(self):
        self.model_var.set(self.config.model)
        self.lang_var.set(self.config.language or "auto")
        self.vocab_var.set(", ".join(self.config.vocabulary))
        self.mode_var.set(self.config.mode)
        current_label = next(
            (label for label, idx in self._device_options if idx == self.config.audio.device),
            self._device_options[0][0],
        )
        self.device_var.set(current_label)
        self.beep_var.set(self.config.audio.beep_volume)
        ptt_values = list(PTT_HOTKEYS)
        current_ptt = self.config.hotkeys.push_to_talk
        if current_ptt not in ptt_values:
            ptt_values.insert(0, current_ptt)
        self.ptt_hotkey_var.set(current_ptt)
        self.vad_threshold_var.set(self.config.vad.speech_threshold)
        self.vad_silence_var.set(self.config.vad.silence_duration)
        self.tp_enabled_var.set(self.config.text_processing.enabled)
        self._tp_vars["remove_fillers"].set(self.config.text_processing.remove_fillers)
        self._tp_vars["punctuation_commands"].set(self.config.text_processing.punctuation_commands)
        self._tp_vars["newline_commands"].set(self.config.text_processing.newline_commands)
        self._tp_vars["informal_to_formal"].set(self.config.text_processing.informal_to_formal)
        self._tp_vars["fix_capitalization"].set(self.config.text_processing.fix_capitalization)
        self._tp_vars["ensure_sentence_spacing"].set(self.config.text_processing.ensure_sentence_spacing)
        self._tp_vars["add_trailing_space"].set(self.config.text_processing.add_trailing_space)
        self._tp_vars["collapse_repeated_words"].set(self.config.text_processing.collapse_repeated_words)

    # ---------------- Window state ----------------

    def _on_close(self):
        self.withdraw()

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self):
        self.withdraw()

    def _on_quit_clicked(self):
        try:
            self.on_quit()
        finally:
            self.destroy()

    # ---------------- Tick ----------------

    def _tick(self):
        try:
            status = self.get_status()
            color = STATUS_COLORS.get(status, STATUS_COLORS["idle"])
            self.status_pill.configure(text=f"● {status}", text_color=color)

            self.mode_label.configure(text=f"Mode: {self.config.mode}")
            self.model_label.configure(text=f"Model: {self.config.model}")
            self.device_label.configure(text=f"Device: {self._device_name(self.config.audio.device)}")

            raw = self.get_level()
            self._displayed_level = 0.7 * self._displayed_level + 0.3 * raw
            scaled = min(1.0, self._displayed_level * 4.0)
            self.level_bar.set(scaled)

            if self.ptt_tick:
                self.ptt_tick()
        except Exception as e:
            print(f"Tick error: {e}")
        finally:
            self.after(33, self._tick)
