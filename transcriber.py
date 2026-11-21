import time
from typing import Optional
import numpy as np
# Keep this import. The code only calls torch.cuda.is_available(), but importing
# torch also puts torch\lib on the DLL search path, and that folder holds the
# cuBLAS and cuDNN DLLs CTranslate2 needs for the GPU. Unless those come from
# somewhere else (a CUDA toolkit on PATH, or the nvidia-*-cu12 pip packages),
# removing this line breaks GPU transcription.
import torch
from faster_whisper import WhisperModel

from word_list_check import hotwords_text, same_words, word_list_leak


class Transcriber:
    def __init__(
        self,
        model_size: str = "small",
        device: str = "cuda",
        compute_type: str = "float16",
        language: Optional[str] = "en",
        vocabulary: Optional[list[str]] = None,
    ):
        self.model_size = model_size
        self.vocabulary = list(vocabulary or [])
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
        # The word list goes in as hotwords, which are added to every 30-second
        # window, so they also cover long clips. Tested 2026-11-01 on medium:
        # "MWIC" became AMWIC and "Amrak" became AMRAC. But Whisper sometimes
        # writes the list back in place of real speech (10 of 110 clips of
        # Chris's own mic, 2026-11-21), so a result that looks like the list
        # is run again without it. See word_list_check.py. The same test found
        # the list sometimes makes Whisper return nothing for clear speech
        # (2 of 166 clips) that it hears fine without the list, so an empty
        # result is also run again when the speech detector kept 2 seconds or
        # more (its padding alone is 0.8 s, so an "um" or a cough stays out).
        # The log line says when this happens, never what was said.
        hotwords = hotwords_text(self.vocabulary)
        text, heard = self._decode(audio, hotwords)
        if hotwords:
            leak = word_list_leak(text, self.vocabulary)
            if leak or (not text and heard >= 2.0):
                started = time.perf_counter()
                plain, _ = self._decode(audio, None)
                took = time.perf_counter() - started
                if not leak:
                    print(f"  word list check: nothing came back from {heard:.1f}s of speech; "
                          f"ran again without the list ({took:.2f}s)")
                    text = plain
                elif leak == "whole" and same_words(text, plain):
                    print(f"  word list check: ran again without the list ({took:.2f}s); "
                          "same words, so the list spelling stays")
                else:
                    print(f"  word list check: Whisper wrote the list back ({leak}); "
                          f"ran again without it ({took:.2f}s) and pasting that")
                    text = plain
        return text

    def _decode(self, audio: np.ndarray, hotwords: Optional[str]) -> tuple[str, float]:
        """One Whisper pass. Returns all segments joined into one string, and
        the seconds of audio the speech detector kept."""
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            vad_filter=True,
            hotwords=hotwords,
        )
        text = " ".join(segment.text for segment in segments).strip()
        return text, info.duration_after_vad

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
