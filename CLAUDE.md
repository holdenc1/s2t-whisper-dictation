# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Windows-first, local speech-to-text tool using OpenAI's Whisper model. Uses `sounddevice` for audio capture, `keyboard` for hotkeys, and `faster-whisper` + `torch` for transcription. Supports both CLI and GUI (system tray) modes.

## Build / Run Commands

### Setup
- Full setup with CUDA: `setup.bat`
- Manual CPU setup: `python -m venv venv && venv\Scripts\activate.bat && pip install -r requirements.txt`

### Run
- CLI: `run.bat` or `python main.py`
- GUI (CUDA): `run_gui.bat` or `python main_gui.py`
- CUDA CLI: `run_cuda.bat`

### Sanity Checks
- `python -m compileall .`
- `python -m pip check`

### Tests (Automated)
- `python -m unittest discover tests` (text cleanup rules). Keep automated tests in `tests/`: the root `test_*.py` scripts record from the mic as soon as they are imported.

### Tests (Manual/Smoke)
- `python test_mic.py` (device listing + 3s recording)
- `python test_ptt.py` (hold Space to record)

### Optional Linting (not repo-pinned)
- `python -m ruff check .`
- `python -m black .`
- `python -m mypy .`

## Architecture

### Entry Points
- `main.py` - CLI application with `SpeechToText` class
- `main_gui.py` - GUI version with `SpeechToTextGUI` class, adds tray icon and settings window

### Core Modules
- `transcriber.py` - `Transcriber` class wraps `faster-whisper.WhisperModel`, handles lazy loading and model switching
- `audio.py` - `AudioRecorder` and `ContinuousAudioRecorder` classes for sounddevice streams; device selection helpers
- `config.py` - Dataclass-based configuration with YAML persistence (`config.yaml`); contains `HotkeyConfig`, `AudioConfig`, `VADConfig`, `TextProcessingConfig`

### Input/Output
- `hotkeys.py` - `HotkeyHandler` and `HotkeyManager` for keyboard hook management
- `typer.py` - `TextTyper` for keyboard simulation via pyautogui; clipboard paste via pyperclip
- `text_processor.py` - Rule-based post-processing (filler removal, punctuation commands, capitalization)

### Voice Activity Detection
- `vad.py` - `VoiceActivityDetector` (Silero VAD via torch.hub) and `SimpleVAD` (energy-based fallback)

### GUI Components (optional deps: customtkinter, pystray, Pillow)
- `tray_icon.py` - `TrayIcon` class for system tray with status colors (green/red/orange)
- `settings_window.py` - `SettingsWindow` using CustomTkinter

## Key Patterns

### Audio Handling
- Audio callbacks must be fast and allocation-light
- Shared buffers between threads require `threading.Lock`
- State transitions use explicit flags: `_recording`, `_processing`, `_vad_speaking`

### Configuration
- `config.yaml` is user data; always use `yaml.safe_load`
- New config fields: add to dataclass, include defaults, update `Config.save()`

### Hotkeys
- **Never use `suppress=True`** with `keyboard.add_hotkey()` or `keyboard.on_press_key()` — it causes modifier keys (especially Ctrl) to get stuck in the OS key state, interfering with other applications
- Always release modifier keys (`pyautogui.keyUp()`) before simulating key combos like Ctrl+V
- Three recording modes: `push_to_talk` (hold key), `toggle_to_talk` (press to start/stop), `voice_activation` (auto-detect speech). Cycle with switch-mode hotkey.
- Prefer non-modifier hotkeys (e.g., `scroll lock`, `pause`, `f13`) to avoid stuck-key issues

### Side Effects
- Typing/pasting affects the active application window
- Hotkey registration via `keyboard` module must be cleaned up on exit (`keyboard.unhook_all()`)
- Keep GUI dependencies optional; don't import GUI modules from CLI path

## Code Style

- Target Windows; Python 3.12+
- 4 spaces, ~100 char lines, f-strings
- Imports: stdlib → third-party → local; one per line
- Type hints on public functions; use builtin generics (`list[...]`, `dict[...]`)
- Naming: `snake_case` files/functions/vars, `PascalCase` classes, `UPPER_SNAKE_CASE` constants, `_` prefix for private

## What Not To Touch

- `venv/`, `venv_cuda/` - generated virtualenvs
- `__pycache__/`, `output.log` - generated artifacts
