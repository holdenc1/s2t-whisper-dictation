import time
from typing import Callable, Optional
import numpy as np
import torch

# Silero VAD model
_vad_model = None
_vad_utils = None


def load_silero_vad():
    """Load Silero VAD model."""
    global _vad_model, _vad_utils
    if _vad_model is None:
        print("Loading Silero VAD model...")
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )
        _vad_model = model
        _vad_utils = utils
        print("Silero VAD loaded.")
    return _vad_model, _vad_utils


class VoiceActivityDetector:
    def __init__(
        self,
        sample_rate: int = 16000,
        speech_threshold: float = 0.5,
        silence_duration: float = 1.0,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.speech_threshold = speech_threshold
        self.silence_duration = silence_duration
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end

        self._model, self._utils = load_silero_vad()
        self._is_speaking = False
        self._silence_start: Optional[float] = None
        self._audio_buffer: list[np.ndarray] = []
        self._window_size = 512  # Silero VAD expects 512 samples at 16kHz

    def reset(self):
        """Reset the VAD state."""
        self._model.reset_states()
        self._is_speaking = False
        self._silence_start = None
        self._audio_buffer = []

    def process_audio(self, audio_chunk: np.ndarray):
        """Process an audio chunk and detect speech."""
        # Ensure correct dtype
        if audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)

        # Convert to tensor
        audio_tensor = torch.from_numpy(audio_chunk)

        # Process in windows
        for i in range(0, len(audio_tensor), self._window_size):
            window = audio_tensor[i : i + self._window_size]
            if len(window) < self._window_size:
                # Pad if necessary
                window = torch.nn.functional.pad(
                    window, (0, self._window_size - len(window))
                )

            # Get speech probability
            speech_prob = self._model(window, self.sample_rate).item()

            if speech_prob >= self.speech_threshold:
                # Speech detected
                if not self._is_speaking:
                    self._is_speaking = True
                    self._silence_start = None
                    if self.on_speech_start:
                        self.on_speech_start()

                self._audio_buffer.append(audio_chunk)

            else:
                # Silence detected
                if self._is_speaking:
                    self._audio_buffer.append(audio_chunk)

                    if self._silence_start is None:
                        self._silence_start = time.time()
                    elif time.time() - self._silence_start >= self.silence_duration:
                        # End of speech
                        self._is_speaking = False
                        if self.on_speech_end and self._audio_buffer:
                            full_audio = np.concatenate(self._audio_buffer)
                            self.on_speech_end(full_audio)
                        self._audio_buffer = []
                        self._silence_start = None

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking


class SimpleVAD:
    """Simple energy-based VAD as fallback."""

    def __init__(
        self,
        threshold: float = 0.01,
        silence_duration: float = 1.0,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self.threshold = threshold
        self.silence_duration = silence_duration
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end

        self._is_speaking = False
        self._silence_start: Optional[float] = None
        self._audio_buffer: list[np.ndarray] = []

    def reset(self):
        self._is_speaking = False
        self._silence_start = None
        self._audio_buffer = []

    def process_audio(self, audio_chunk: np.ndarray):
        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio_chunk**2))

        if rms >= self.threshold:
            if not self._is_speaking:
                self._is_speaking = True
                self._silence_start = None
                if self.on_speech_start:
                    self.on_speech_start()
            self._audio_buffer.append(audio_chunk)
        else:
            if self._is_speaking:
                self._audio_buffer.append(audio_chunk)
                if self._silence_start is None:
                    self._silence_start = time.time()
                elif time.time() - self._silence_start >= self.silence_duration:
                    self._is_speaking = False
                    if self.on_speech_end and self._audio_buffer:
                        full_audio = np.concatenate(self._audio_buffer)
                        self.on_speech_end(full_audio)
                    self._audio_buffer = []
                    self._silence_start = None

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking
