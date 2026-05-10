#!/usr/bin/env python3
"""
Speech-to-Text Local Transcription Tool (GUI Version)

Main window + system-tray. Supports push-to-talk, toggle-to-talk, and voice activation.
"""

import ctypes
import os
import queue
import sys
import threading
import time
import traceback
import winsound
from typing import Optional


def _setup_logging():
    """Redirect stdout/stderr to startup.log when there is no real console
    (e.g. pythonw.exe). Modern Python wraps stdout/stderr in a no-op
    TextIOWrapper rather than setting them to None, so we can't rely on
    'is None' — check Windows for an attached console window instead.

    Also installs an excepthook so any unhandled exception is captured
    in the log instead of vanishing silently."""
    here = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(here, "startup.log")

    has_console = False
    try:
        has_console = bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        pass

    if not has_console:
        try:
            f = open(log_path, "w", buffering=1, encoding="utf-8")
            sys.stdout = f
            sys.stderr = f
            f.write(f"=== Started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        except Exception:
            pass

    def _excepthook(exc_type, exc, tb):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n=== UNHANDLED EXCEPTION ===\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
        except Exception:
            pass

    sys.excepthook = _excepthook


def _hide_console():
    """Hide the console window if we were launched via python.exe instead of pythonw.exe."""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


_setup_logging()
_hide_console()

import keyboard
import numpy as np
import sounddevice as sd

from audio import list_audio_devices
from config import Config
from keystate import is_combo_pressed, release_modifiers
from main_window import MainWindow, SplashScreen
from text_processor import process_text
from transcriber import Transcriber
from tray_icon import TrayIcon
from typer import TextTyper


class SpeechToTextGUI:
    def __init__(self):
        self.config = Config.load()
        self.transcriber = Transcriber(
            model_size=self.config.model,
            device="cuda",
            compute_type="float16",
            language=self.config.language,
        )
        self.typer = TextTyper()

        # Audio state
        self._audio_buffer: list[np.ndarray] = []
        self._recording = False
        self._stream: Optional[sd.InputStream] = None
        self._latest_level: float = 0.0

        # App state
        self._running = False
        self._processing = False
        self._status: str = "idle"
        self._ptt_held = False
        self._toggle_recording = False
        self._vad_active = False
        self._vad_speaking = False
        self._vad_silence_start: Optional[float] = None

        # Worker for transcription so the audio callback never blocks
        self._transcribe_queue: queue.Queue[Optional[np.ndarray]] = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None

        # GUI
        self.window: Optional[MainWindow] = None
        self._splash: Optional[SplashScreen] = None
        self.tray = TrayIcon(
            on_show=self._show_window,
            on_switch_model=self._switch_model,
            on_switch_device=self._switch_device_dialog,
            on_quit=self._quit,
        )

    # -------- Audio --------

    def _beep(self, frequency: int, duration_ms: int = 60):
        """Play a beep on a daemon thread so the caller never blocks. Running
        winsound.Beep on the UI thread can collide with the audio stream
        becoming active and cause the start cue to be inaudible."""
        if self.config.audio.beep_volume <= 0:
            return
        def _play():
            try:
                winsound.Beep(frequency, duration_ms)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def _audio_callback(self, indata, frames, time_info, status):
        # Always update level meter source
        try:
            self._latest_level = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        except Exception:
            self._latest_level = 0.0

        if self._recording:
            self._audio_buffer.append(indata.copy())

        if self._vad_active and not self._processing:
            self._process_vad_audio(indata.copy().flatten())

    def _start_audio_stream(self):
        self._stream = sd.InputStream(
            samplerate=self.config.audio.sample_rate,
            device=self.config.audio.device,
            channels=1,
            dtype=np.float32,
            callback=self._audio_callback,
        )
        self._stream.start()

    def _stop_audio_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"Error stopping stream: {e}")
            self._stream = None

    # -------- Recording state --------

    def _set_status(self, status: str):
        self._status = status
        self.tray.set_status(status)

    def _start_recording(self):
        # Beep BEFORE flipping _recording so the mic doesn't capture our own
        # cue tone, and so the cue isn't suppressed by the OS reacting to the
        # stream becoming active.
        self._beep(880, 80)
        self._audio_buffer = []
        self._recording = True
        self._set_status("recording")

    def _stop_recording(self) -> np.ndarray:
        self._recording = False
        self._beep(440, 80)
        if self._audio_buffer:
            audio = np.concatenate(self._audio_buffer, axis=0).flatten()
            self._audio_buffer = []
            return audio
        return np.array([], dtype=np.float32)

    # -------- Worker thread (Whisper inference + paste) --------

    def _worker_loop(self):
        while self._running:
            try:
                audio = self._transcribe_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if audio is None:
                break
            self._set_status("processing")
            self._processing = True
            try:
                duration = len(audio) / self.config.audio.sample_rate
                print(f"[Transcribing {duration:.1f}s...]")
                text = self.transcriber.transcribe(audio, sample_rate=self.config.audio.sample_rate)

                if text.strip():
                    if self.config.text_processing.enabled:
                        text = process_text(text, {
                            "remove_fillers": self.config.text_processing.remove_fillers,
                            "punctuation_commands": self.config.text_processing.punctuation_commands,
                            "newline_commands": self.config.text_processing.newline_commands,
                            "informal_to_formal": self.config.text_processing.informal_to_formal,
                            "fix_capitalization": self.config.text_processing.fix_capitalization,
                            "ensure_sentence_spacing": self.config.text_processing.ensure_sentence_spacing,
                            "add_trailing_space": self.config.text_processing.add_trailing_space,
                            "collapse_repeated_words": self.config.text_processing.collapse_repeated_words,
                        })
                    print(f"[Typing: {text}]")
                    release_modifiers()
                    time.sleep(0.05)
                    self.typer.paste(text)
                    self._post_transcript(text)
                else:
                    print("[No speech detected]")
            except Exception as e:
                print(f"Transcription error: {e}")
            finally:
                self._processing = False
                self._set_status("idle")

    def _enqueue(self, audio: np.ndarray):
        if len(audio) == 0:
            self._set_status("idle")
            return
        self._transcribe_queue.put(audio)

    def _post_transcript(self, text: str):
        """Marshal a transcription onto the Tk thread for display in the UI."""
        if not self.window:
            return
        try:
            self.window.after(0, lambda t=text: self.window.add_transcription(t))
        except Exception:
            pass

    # -------- VAD --------

    def _process_vad_audio(self, audio_chunk: np.ndarray):
        rms = float(np.sqrt(np.mean(audio_chunk ** 2)))
        threshold = self.config.vad.speech_threshold / 100.0

        if rms >= threshold:
            if not self._vad_speaking:
                self._vad_speaking = True
                self._audio_buffer = []
                self._set_status("recording")
            self._audio_buffer.append(audio_chunk)
            self._vad_silence_start = None
        else:
            if self._vad_speaking:
                self._audio_buffer.append(audio_chunk)
                if self._vad_silence_start is None:
                    self._vad_silence_start = time.time()
                elif time.time() - self._vad_silence_start >= self.config.vad.silence_duration:
                    self._vad_speaking = False
                    self._vad_silence_start = None
                    if self._audio_buffer:
                        audio = np.concatenate(self._audio_buffer, axis=0).flatten()
                        self._audio_buffer = []
                        min_samples = int(0.5 * self.config.audio.sample_rate)
                        if len(audio) > min_samples:
                            self._enqueue(audio)
                        else:
                            self._set_status("idle")

    # -------- Hotkey handlers --------

    def _toggle_record(self):
        if self._processing:
            return
        if not self._toggle_recording:
            self._toggle_recording = True
            self._start_recording()
        else:
            self._toggle_recording = False
            audio = self._stop_recording()
            self._enqueue(audio)

    def _switch_model(self):
        new_model = self.config.next_model()
        self.transcriber.switch_model(new_model)
        self.config.save()
        self.tray.set_model(new_model)
        print(f"[Model switched to: {new_model}]")

    def _switch_device_dialog(self):
        # Tray-triggered: pick the next device in the list (avoids opening a stdin prompt).
        devices = list_audio_devices()
        if not devices:
            return
        idxs = [None] + [idx for idx, _ in devices]
        try:
            current = idxs.index(self.config.audio.device)
        except ValueError:
            current = 0
        new_idx = idxs[(current + 1) % len(idxs)]
        self.config.audio.device = new_idx
        self.config.save()
        self._stop_audio_stream()
        self._start_audio_stream()
        name = "Default" if new_idx is None else sd.query_devices(new_idx)["name"]
        print(f"[Audio device: {name}]")

    def _show_window(self):
        if self.window:
            self.window.after(0, self.window.show)

    def _quit(self):
        self._running = False
        if self.window:
            try:
                self.window.after(0, self.window.destroy)
            except Exception:
                pass

    # -------- PTT polling (called from Tk tick) --------

    def _ptt_tick(self):
        if self.config.mode != "push_to_talk":
            return
        if is_combo_pressed(self.config.hotkeys.push_to_talk):
            if not self._ptt_held and not self._processing:
                self._ptt_held = True
                self._start_recording()
        else:
            if self._ptt_held:
                self._ptt_held = False
                audio = self._stop_recording()
                self._enqueue(audio)

    # -------- Hotkey registration --------

    def _register_hotkeys(self):
        keyboard.unhook_all()
        try:
            keyboard.add_hotkey(self.config.hotkeys.switch_model, self._switch_model)
            keyboard.add_hotkey(self.config.hotkeys.switch_device, self._switch_device_dialog)
            keyboard.add_hotkey(self.config.hotkeys.quit, self._quit)
            if self.config.mode == "toggle_to_talk":
                keyboard.add_hotkey(self.config.hotkeys.push_to_talk, self._toggle_record)
        except Exception as e:
            print(f"Error registering hotkeys: {e}")

    def _apply_mode(self):
        # Reset transient mode state
        self._vad_active = False
        self._vad_speaking = False
        self._vad_silence_start = None
        self._toggle_recording = False
        self._ptt_held = False
        self._audio_buffer = []
        if self.config.mode == "voice_activation":
            self._vad_active = True
            print("[Mode: VOICE ACTIVATION]")
        elif self.config.mode == "toggle_to_talk":
            print(f"[Mode: TOGGLE-TO-TALK ({self.config.hotkeys.push_to_talk})]")
        else:
            print(f"[Mode: PUSH-TO-TALK ({self.config.hotkeys.push_to_talk})]")

    # -------- Hot-apply config --------

    def apply_config(self, new: Config):
        old = self.config
        self.config = new
        new.save()

        if new.model != old.model:
            self.transcriber.switch_model(new.model)
            self.tray.set_model(new.model)
        if new.language != old.language:
            self.transcriber.language = new.language

        if (new.audio.device != old.audio.device
                or new.audio.sample_rate != old.audio.sample_rate):
            self._stop_audio_stream()
            self._start_audio_stream()

        hotkey_changed = (
            new.hotkeys.push_to_talk != old.hotkeys.push_to_talk
            or new.hotkeys.switch_model != old.hotkeys.switch_model
            or new.hotkeys.switch_mode != old.hotkeys.switch_mode
            or new.hotkeys.switch_device != old.hotkeys.switch_device
            or new.hotkeys.quit != old.hotkeys.quit
        )
        mode_changed = new.mode != old.mode

        if mode_changed or hotkey_changed:
            self._register_hotkeys()
        if mode_changed:
            self._apply_mode()

        print("[Config applied]")

    # -------- Lifecycle --------

    def run(self):
        print("[run] creating MainWindow")
        # Build the main window first (it owns the Tk root) but keep it hidden.
        self.window = MainWindow(
            config=self.config,
            get_status=lambda: self._status,
            get_level=lambda: self._latest_level,
            on_apply=self.apply_config,
            on_quit=self._quit,
            ptt_tick=self._ptt_tick,
        )
        # Position off-screen rather than withdraw — Tk needs the window to
        # be mapped at least once before deiconify reliably places it on
        # screen, and withdraw-before-map can leave it stuck off-screen.
        self.window.geometry("+-10000+-10000")
        self.window.update_idletasks()

        print("[run] creating SplashScreen")
        self._splash = SplashScreen(self.window)
        self._splash.set_status(f"Loading Whisper model ({self.config.model})…")
        self._splash.update_idletasks()

        # Kick heavy init onto a worker thread once the UI has painted.
        self.window.after(50, self._init_in_background)

        print("[run] entering mainloop")
        try:
            self.window.mainloop()
        finally:
            print("[run] mainloop exited, cleaning up")
            self._cleanup()

    # -------- Splash plumbing --------

    def _splash_status(self, text: str):
        if self._splash and self.window:
            try:
                self.window.after(0, lambda t=text: self._splash and self._splash.set_status(t))
            except Exception:
                pass

    def _splash_error(self, message: str):
        if self._splash and self.window:
            try:
                self.window.after(0, lambda m=message: self._splash and self._splash.show_error(m))
            except Exception:
                pass

    def _init_in_background(self):
        def worker():
            try:
                print("[init] loading model")
                self._splash_status(f"Loading Whisper model ({self.config.model})…")
                self.transcriber._load_model()

                print("[init] starting audio stream")
                self._splash_status("Starting audio stream…")
                self._start_audio_stream()

                print("[init] registering hotkeys")
                self._splash_status("Registering hotkeys…")
                self._running = True
                self._register_hotkeys()
                self._apply_mode()

                print("[init] starting transcription worker")
                self._splash_status("Starting transcription worker…")
                self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
                self._worker_thread.start()

                print("[init] starting tray icon")
                self._splash_status("Starting tray icon…")
                self.tray.set_model(self.config.model)
                self.tray.start()
                self._set_status("idle")

                print("[init] ready, scheduling finish_loading")
                self._splash_status("Ready!")
                self.window.after(250, self._finish_loading)
            except Exception as e:
                import traceback as _tb
                print(f"[init] FAILED: {e}")
                _tb.print_exc()
                self._splash_error(f"Startup failed: {e}")
                self.window.after(4000, self._abort_loading)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_loading(self):
        print("[finish_loading] closing splash, showing main window")
        if self._splash:
            try:
                self._splash.close()
            except Exception as e:
                print(f"[finish_loading] splash.close failed: {e}")
            self._splash = None
        if self.window:
            try:
                # Re-center on the primary screen — we positioned it off-screen
                # during loading.
                w, h = 640, 820
                sw = self.window.winfo_screenwidth()
                sh = self.window.winfo_screenheight()
                self.window.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
                self.window.deiconify()
                self.window.lift()
                self.window.focus_force()
                self.window.attributes("-topmost", True)
                self.window.after(200, lambda: self.window.attributes("-topmost", False))
                print("[finish_loading] window shown")
            except Exception as e:
                print(f"[finish_loading] failed: {e}")

    def _abort_loading(self):
        if self._splash:
            self._splash.close()
            self._splash = None
        if self.window:
            self.window.destroy()

    def _cleanup(self):
        self._running = False
        try:
            self._transcribe_queue.put(None)
        except Exception:
            pass
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self._stop_audio_stream()
        self.tray.stop()
        print("Goodbye!")


def main():
    SpeechToTextGUI().run()


if __name__ == "__main__":
    main()
