from typing import Optional
import numpy as np
# Keep this import. The code only calls torch.cuda.is_available(), but importing
# torch also puts torch\lib on the DLL search path, and that folder holds the
# cuBLAS and cuDNN DLLs CTranslate2 needs for the GPU. Unless those come from
# somewhere else (a CUDA toolkit on PATH, or the nvidia-*-cu12 pip packages),
# removing this line breaks GPU transcription.
import torch
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(
        self,
        model_size: str = "small",
        device: str = "cuda",
        compute_type: str = "float16",
        language: Optional[str] = "en",
    ):
        self.model_size = model_size
        self.device = device if torch.cuda.is_available() else "cpu"
        # Adjust compute type for CPU - float16 is not efficiently supported
        if self.device == "cpu" and compute_type == "float16":
            self.compute_type = "int8"
        else:
            self.compute_type = compute_type
        self.language = language
        self._model = None

    def _load_model(self):
        """Lazy load the model."""
        if self._model is None:
            print(f"Loading Whisper model: {self.model_size}...")
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            print(f"Model {self.model_size} loaded on {self.device}.")

    def switch_model(self, model_size: str):
        """Switch to a different model size."""
        if model_size != self.model_size:
            self.model_size = model_size
            self._model = None  # Force reload on next transcription
            print(f"Will load model {model_size} on next transcription.")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio to text."""
        self._load_model()

        if len(audio) == 0:
            return ""

        # Ensure audio is float32 and normalized
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Normalize audio to [-1, 1] range if needed
        max_val = np.abs(audio).max()
        if max_val > 1.0:
            audio = audio / max_val

        # faster-whisper transcribe returns segments. vad_filter (off by default)
        # runs the bundled Silero speech detector first: without it, a tap of
        # near-silence comes back as invented text ("Thank you.", "Thanks for
        # watching!" from 4 of 5 sub-second clips, Oct 2026 log) that then gets
        # pasted. With no speech found, no segments come back.
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            vad_filter=True,
        )

        # Combine all segments into a single text
        text = " ".join(segment.text for segment in segments)
        return text.strip()

    def transcribe_with_info(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> tuple[str, dict]:
        """Transcribe and return additional info."""
        self._load_model()

        if len(audio) == 0:
            return "", {}

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        max_val = np.abs(audio).max()
        if max_val > 1.0:
            audio = audio / max_val

        segments, info = self._model.transcribe(
            audio,
            language=self.language,
        )

        # Combine all segments into a single text
        text = " ".join(segment.text for segment in segments)

        return text.strip(), {
            "language": info.language,
        }
