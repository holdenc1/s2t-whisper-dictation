#!/usr/bin/env python3
"""
Speech-to-Text Local Transcription Tool

A local speech-to-text tool using OpenAI's Whisper model.
Supports push-to-talk and voice activation modes.
"""

import sys
import time
import threading
import winsound
from typing import Optional
import numpy as np
import sounddevice as sd
import keyboard

from config import Config, AVAILABLE_MODELS
from transcriber import Transcriber
from typer import TextTyper
from text_processor import process_text
from audio import select_audio_device, select_audio_device_runtime, wasapi_extra_settings
from keystate import is_combo_pressed, release_modifiers


class SpeechToText:
    def __init__(self):
        self.config = Config.load()
        self.transcriber = Transcriber(
            model_size=self.config.model,
            device="cuda",
            compute_type="float16",
            language=self.config.language,
            vocabulary=self.config.vocabulary,
        )
        self.typer = TextTyper()

        # Audio state
        self._audio_buffer = []
        self._recording = False
        self._stream: Optional[sd.InputStream] = None

        # App state
        self._running = False
        self._processing = False
        self._ptt_held = False
        self._toggle_recording = False
        self._vad_active = False
        self._vad_speaking = False
        self._vad_silence_start = None


    def _beep(self, frequency: int, duration_ms: int = 60):
        """Play a beep on a daemon thread so the caller never blocks."""
        if self.config.audio.beep_volume <= 0:
            return
        def _play():
            try:
                winsound.Beep(frequency, duration_ms)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio input callback."""
        if status:
            print(f"\rAudio status: {status}", flush=True)

        if self._recording:
            self._audio_buffer.append(indata.copy())

        # VAD mode processing
        if self._vad_active and not self._processing:
            self._process_vad_audio(indata.copy())

    def _start_audio_stream(self):
        """Start the audio input stream."""
        self._stream = sd.InputStream(
            samplerate=self.config.audio.sample_rate,
            device=self.config.audio.device,
            channels=1,
            dtype=np.float32,
            callback=self._audio_callback,
            extra_settings=wasapi_extra_settings(self.config.audio.device),
        )
        self._stream.start()

    def _stop_audio_stream(self):
        """Stop the audio input stream."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _start_recording(self):
        """Start recording audio."""
        # Beep BEFORE flipping _recording so the mic doesn't capture the cue.
        self._beep(880, 80)
        self._audio_buffer = []
        self._recording = True
        print("\r[Recording...] ", end="", flush=True)

    def _stop_recording(self) -> np.ndarray:
        """Stop recording and return audio."""
        self._recording = False
        self._beep(440, 80)
        if self._audio_buffer:
            audio = np.concatenate(self._audio_buffer, axis=0).flatten()
            self._audio_buffer = []
            return audio
        return np.array([], dtype=np.float32)

    def _process_audio(self, audio: np.ndarray):
        """Process recorded audio and type the transcription."""
        self._processing = True

        duration = len(audio) / self.config.audio.sample_rate
        max_amp = np.abs(audio).max()
        print(f"\r[Transcribing {duration:.1f}s, amp={max_amp:.3f}...] ", end="", flush=True)

        try:
            text = self.transcriber.transcribe(
                audio, sample_rate=self.config.audio.sample_rate
            )

            if text.strip():
                # Apply text post-processing if enabled
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
                # Show full text in console
                print(f"\r[Typing: {text}]")
                # Release any stuck modifier keys before pasting
                release_modifiers()
                time.sleep(0.05)
                # Centralized, target-aware paste
                self.typer.paste(text)
            else:
                print("\r[No speech detected]          ", flush=True)

        except Exception as e:
            print(f"\r[Error: {e}]")
        finally:
            self._processing = False

    def _is_ptt_pressed(self) -> bool:
        """Check if the push-to-talk hotkey is pressed (via Win32 API, no hooks)."""
        return is_combo_pressed(self.config.hotkeys.push_to_talk)

    def _switch_model(self):
        """Switch to the next Whisper model."""
        new_model = self.config.next_model()
        self.transcriber.switch_model(new_model)
        self.config.save()
        print(f"\n[Model switched to: {new_model}]")

    def _switch_mode(self):
        """Cycle through push-to-talk, toggle-to-talk, and voice activation."""
        # Clean up current mode state
        self._vad_active = False
        self._vad_speaking = False
        self._toggle_recording = False
        keyboard.unhook_all()

        new_mode = self.config.toggle_mode()
        self.config.save()

        # Re-register utility hotkeys
        keyboard.add_hotkey(
            self.config.hotkeys.switch_model, self._switch_model
        )
        keyboard.add_hotkey(
            self.config.hotkeys.switch_mode, self._switch_mode
        )
        keyboard.add_hotkey(
            self.config.hotkeys.switch_device, self._switch_device
        )

        if new_mode == "voice_activation":
            self._vad_active = True
            self._vad_silence_start = None
            self._audio_buffer = []
            print(f"\n[Mode: VOICE ACTIVATION - speak to transcribe]")
        elif new_mode == "toggle_to_talk":
            keyboard.add_hotkey(
                self.config.hotkeys.push_to_talk, self._toggle_record
            )
            print(f"\n[Mode: TOGGLE-TO-TALK - press {self.config.hotkeys.push_to_talk} to start/stop]")
        else:
            print(f"\n[Mode: PUSH-TO-TALK - hold {self.config.hotkeys.push_to_talk}]")

    def _switch_device(self):
        """Switch audio input device during runtime."""
        # Stop current stream
        self._stop_audio_stream()

        # Select new device
        new_device = select_audio_device_runtime(self.config.audio.device)

        # Update config if device changed
        if new_device != self.config.audio.device:
            self.config.audio.device = new_device
            self.config.save()

        # Restart stream with new device
        self._start_audio_stream()
        print(f"[Audio stream restarted]")

    def _process_vad_audio(self, audio_chunk: np.ndarray):
        """Process audio chunk for voice activity detection."""
        # Calculate RMS volume
        rms = np.sqrt(np.mean(audio_chunk ** 2))
        threshold = self.config.vad.speech_threshold / 100  # Scale threshold (lower = more sensitive)

        if rms >= threshold:
            # Speech detected
            if not self._vad_speaking:
                self._vad_speaking = True
                self._audio_buffer = []
                print("\r[VAD: Listening...] ", end="", flush=True)

            self._audio_buffer.append(audio_chunk)
            self._vad_silence_start = None  # Reset silence timer when speech detected

        else:
            # Silence
            if self._vad_speaking:
                # Keep buffering during silence (to capture pauses in speech)
                self._audio_buffer.append(audio_chunk)

                if self._vad_silence_start is None:
                    self._vad_silence_start = time.time()
                else:
                    silence_elapsed = time.time() - self._vad_silence_start
                    # Only stop after sustained silence
                    if silence_elapsed >= self.config.vad.silence_duration:
                        # End of speech
                        self._vad_speaking = False
                        self._vad_silence_start = None

                        if self._audio_buffer:
                            audio = np.concatenate(self._audio_buffer, axis=0).flatten()
                            self._audio_buffer = []
                            # Only process if we have enough audio (at least 0.5 seconds)
                            min_samples = int(0.5 * self.config.audio.sample_rate)
                            if len(audio) > min_samples:
                                self._process_audio(audio)
                            else:
                                print("\r[VAD: Too short, ignored]          ", flush=True)

    def _toggle_record(self):
        """Toggle recording on/off (for toggle-to-talk mode)."""
        if self._processing:
            return
        if not self._toggle_recording:
            self._toggle_recording = True
            self._start_recording()
        else:
            self._toggle_recording = False
            audio = self._stop_recording()
            if len(audio) > 0:
                self._process_audio(audio)
            else:
                print("\r[No audio captured]          ", flush=True)

    def _main_loop(self):
        """Main polling loop for both PTT and VAD modes."""
        while self._running:
            # PTT mode: check for hotkey (hold to record)
            if self.config.mode == "push_to_talk":
                if self._is_ptt_pressed():
                    if not self._ptt_held and not self._processing:
                        self._ptt_held = True
                        self._start_recording()
                else:
                    if self._ptt_held:
                        self._ptt_held = False
                        audio = self._stop_recording()
                        if len(audio) > 0:
                            self._process_audio(audio)
                        else:
                            print("\r[No audio captured]          ", flush=True)

            # Toggle mode and VAD mode are event-driven (handled by hotkey callbacks)

            time.sleep(0.01)  # 10ms polling interval

    def run(self):
        """Run the main application loop."""
        print("=" * 50)
        print("Speech-to-Text Local Transcription Tool")
        print("=" * 50)
        print(f"Model: {self.config.model}")
        print(f"Mode: {self.config.mode}")
        print(f"Language: {self.config.language or 'auto'}")
        print("-" * 50)
        print(f"Push-to-talk:   {self.config.hotkeys.push_to_talk}")
        print(f"Switch model:   {self.config.hotkeys.switch_model}")
        print(f"Switch mode:    {self.config.hotkeys.switch_mode}")
        print(f"Switch device:  {self.config.hotkeys.switch_device}")
        print(f"Quit:           {self.config.hotkeys.quit}")
        print("=" * 50)

        # Select audio device
        selected_device = select_audio_device(self.config)
        if selected_device != self.config.audio.device:
            self.config.audio.device = selected_device
            self.config.save()

        # Pre-load the model
        print("\nLoading model (first time may take a while)...")
        self.transcriber._load_model()

        # Start audio stream
        print("Starting audio stream...")
        self._start_audio_stream()

        # Set up utility hotkeys (suppress=False to avoid stuck modifier keys)
        keyboard.add_hotkey(
            self.config.hotkeys.switch_model, self._switch_model
        )
        keyboard.add_hotkey(
            self.config.hotkeys.switch_mode, self._switch_mode
        )
        keyboard.add_hotkey(
            self.config.hotkeys.switch_device, self._switch_device
        )

        # Register toggle-to-talk hotkey if in toggle mode
        if self.config.mode == "toggle_to_talk":
            keyboard.add_hotkey(
                self.config.hotkeys.push_to_talk, self._toggle_record
            )

        self._running = True

        # Set initial mode
        if self.config.mode == "voice_activation":
            self._vad_active = True
            print(f"\n[Ready - VOICE ACTIVATION mode, speak to transcribe]")
        elif self.config.mode == "toggle_to_talk":
            print(f"\n[Ready - Press {self.config.hotkeys.push_to_talk} to start/stop recording]")
        else:
            print(f"\n[Ready - Hold {self.config.hotkeys.push_to_talk} to record]")

        print("[Press Ctrl+C to quit]\n")

        # Main loop
        try:
            self._main_loop()
        except KeyboardInterrupt:
            print("\n[Interrupted]")
        finally:
            self._cleanup()

    def _cleanup(self):
        """Clean up resources."""
        self._running = False
        keyboard.unhook_all()
        self._stop_audio_stream()
        print("[Goodbye!]")


def main():
    app = SpeechToText()
    app.run()


if __name__ == "__main__":
    main()
