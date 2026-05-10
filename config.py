import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import yaml


CONFIG_PATH = Path(__file__).parent / "config.yaml"

AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large"]


@dataclass
class HotkeyConfig:
    push_to_talk: str = "ctrl+`"
    switch_model: str = "ctrl+shift+m"
    switch_mode: str = "ctrl+shift+v"
    switch_device: str = "ctrl+shift+d"
    quit: str = "ctrl+shift+q"


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    device: Optional[int] = None
    beep_volume: float = 0.3  # 0.0 to 1.0


@dataclass
class VADConfig:
    speech_threshold: float = (
        2.0  # RMS threshold for speech detection (lower = more sensitive)
    )
    silence_duration: float = 1.0  # Seconds of silence before stopping


@dataclass
class TextProcessingConfig:
    enabled: bool = True
    remove_fillers: bool = True  # Remove um, uh, etc.
    punctuation_commands: bool = True  # "period" -> "."
    newline_commands: bool = True  # "new line" -> \n
    informal_to_formal: bool = False  # "gonna" -> "going to"
    fix_capitalization: bool = True  # Capitalize sentences
    ensure_sentence_spacing: bool = True  # Force space after . ! ? before letter/digit
    add_trailing_space: bool = True  # Append a trailing space so next dictation is separated
    collapse_repeated_words: bool = False  # "the the" -> "the"


@dataclass
class Config:
    model: str = "medium"
    language: Optional[str] = "en"
    mode: str = "push_to_talk"  # "push_to_talk" or "voice_activation"
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    text_processing: TextProcessingConfig = field(default_factory=TextProcessingConfig)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            config = cls()
            config.save(path)
            return config

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        hotkeys = HotkeyConfig(**data.get("hotkeys", {}))
        audio = AudioConfig(**data.get("audio", {}))
        vad = VADConfig(**data.get("vad", {}))
        text_processing = TextProcessingConfig(**data.get("text_processing", {}))

        return cls(
            model=data.get("model", "small"),
            language=data.get("language", "en"),
            mode=data.get("mode", "push_to_talk"),
            hotkeys=hotkeys,
            audio=audio,
            vad=vad,
            text_processing=text_processing,
        )

    def save(self, path: Path = CONFIG_PATH):
        data = {
            "model": self.model,
            "language": self.language,
            "mode": self.mode,
            "hotkeys": {
                "push_to_talk": self.hotkeys.push_to_talk,
                "switch_model": self.hotkeys.switch_model,
                "switch_mode": self.hotkeys.switch_mode,
                "switch_device": self.hotkeys.switch_device,
                "quit": self.hotkeys.quit,
            },
            "audio": {
                "sample_rate": self.audio.sample_rate,
                "device": self.audio.device,
                "beep_volume": self.audio.beep_volume,
            },
            "vad": {
                "speech_threshold": self.vad.speech_threshold,
                "silence_duration": self.vad.silence_duration,
            },
            "text_processing": {
                "enabled": self.text_processing.enabled,
                "remove_fillers": self.text_processing.remove_fillers,
                "punctuation_commands": self.text_processing.punctuation_commands,
                "newline_commands": self.text_processing.newline_commands,
                "informal_to_formal": self.text_processing.informal_to_formal,
                "fix_capitalization": self.text_processing.fix_capitalization,
                "ensure_sentence_spacing": self.text_processing.ensure_sentence_spacing,
                "add_trailing_space": self.text_processing.add_trailing_space,
                "collapse_repeated_words": self.text_processing.collapse_repeated_words,
            },
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    def next_model(self) -> str:
        """Cycle to the next model in the list."""
        try:
            idx = AVAILABLE_MODELS.index(self.model)
            self.model = AVAILABLE_MODELS[(idx + 1) % len(AVAILABLE_MODELS)]
        except ValueError:
            self.model = AVAILABLE_MODELS[0]
        return self.model

    def toggle_mode(self) -> str:
        """Cycle through push_to_talk, toggle_to_talk, and voice_activation modes."""
        modes = ["push_to_talk", "toggle_to_talk", "voice_activation"]
        try:
            idx = modes.index(self.mode)
            self.mode = modes[(idx + 1) % len(modes)]
        except ValueError:
            self.mode = modes[0]
        return self.mode
