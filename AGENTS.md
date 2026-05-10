# AGENTS.md

This repository is a Windows-first, local speech-to-text (Whisper) tool.
It uses `sounddevice` for audio capture, `keyboard` for hotkeys, and
`faster-whisper` + `torch` for transcription.

## Build / Run / Lint / Test

### Setup (recommended)

- Create venv + install deps (CPU/CUDA as scripted):
  - `setup.bat`
  - What it does: `python -m venv venv`, installs PyTorch CUDA wheels, then installs the other deps.

- Minimal/manual (CPU) setup:
  - `python -m venv venv`
  - `venv\Scripts\activate.bat`
  - `python -m pip install -r requirements.txt`

Notes:
- The GUI/tray path (`main_gui.py`) additionally uses `customtkinter`, `pystray`, and `Pillow` (PIL).
  These are not pinned in `requirements.txt` today; on some machines they may already exist in `venv_cuda`.

### Run

- CLI app:
  - `run.bat`
  - or: `venv\Scripts\activate.bat` then `python main.py`

- CUDA venv runs (if `venv_cuda` exists on this machine):
  - `run_cuda.bat` (runs `python main.py` in `venv_cuda`)
  - `run_gui.bat` (runs `python main_gui.py` in `venv_cuda`)

### “Build” (there is no packaging/build system)

- Sanity checks that work without extra tools:
  - `python -m compileall .`
  - `python -m pip check`

### Lint / Format / Typecheck

- There is no repo-pinned linter/formatter/typechecker (`pyproject.toml` is not present).
- Optional local tooling (not pinned here):
  - `python -m ruff check .`
  - `python -m black .`
  - `python -m mypy .`

### Tests

- There is no automated unit test suite at the moment.
- Manual / smoke tests are script-based:
  - `python test_mic.py` (device listing + 3s recording)
  - `python test_ptt.py` (hold Space to record)

#### Running a single test

- “Single test” in this repo usually means running one test script:
  - `python test_mic.py` or `python test_ptt.py`

## Agent Rules (Cursor / Copilot)

- No Cursor rules found in `.cursor/rules/` or `.cursorrules`.
- No Copilot instructions found in `.github/copilot-instructions.md`.

## Code Style Guidelines

### General Python

- Target runtime: Windows; avoid Linux-only assumptions.
- Keep changes compatible with Python 3.12+ (repo currently contains venvs for 3.12 and 3.14).
- Prefer small, testable helpers over long methods; keep UI/audio/hotkey glue readable.

### Imports

- Order imports as:
  1) standard library
  2) third-party
  3) local modules
- One import per line; avoid wildcard imports.
- Avoid importing heavy modules inside tight loops.
- Local pattern already used:
  - `from typing import Optional` (and builtin generics like `list[np.ndarray]`).

### Formatting

- Use 4 spaces; no tabs.
- Prefer f-strings.
- Keep lines reasonably short (~100 chars). Break long function calls with trailing commas.
- Use blank lines to separate logical sections (imports, constants, classes, functions).

### Typing

- Add type hints on public functions/methods and any non-trivial internal helpers.
- Use builtin generics (`list[...]`, `dict[...]`, `tuple[...]`) to match existing code.
- Use `Optional[T]` consistently if you touch surrounding code that already does.
- Avoid `Any` unless it is truly required (e.g., third-party callbacks).

### Naming

- Modules/files: `snake_case.py`.
- Classes: `PascalCase`.
- Functions/methods/vars: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- “Private” state: prefix with `_` (e.g., `_stream`, `_running`).

### Error Handling

- Avoid bare `except:`.
  - Catch specific exceptions when possible.
  - If you intentionally ignore failures (e.g., notification/beep/clipboard restore), catch `Exception` and add a short rationale.
- Always release resources in `finally` blocks:
  - audio streams (`stop()`, `close()`)
  - hotkey hooks (`keyboard.unhook_all()` is used today; be careful not to break other hooks)
- When printing errors, include enough context to debug (“what operation failed”).

### Logging / Console Output

- The project primarily uses `print()`; do not spam output from audio callbacks.
- Avoid long blocking work inside real-time callbacks.
  - If you add heavier processing, push audio chunks to a queue and handle them in a worker thread.

### Concurrency / Real-time Audio

- Audio callbacks must be fast and allocation-light; copy buffers only when necessary.
- Protect shared buffers that are touched by multiple threads (use a `threading.Lock`).
- Prefer explicit state transitions (`_recording`, `_processing`, `_vad_speaking`) over implicit coupling.

### Configuration (`config.yaml`)

- Treat `config.yaml` as user data.
  - Keep backwards compatibility (default missing keys).
  - Use safe parsing (`yaml.safe_load`).
- If you add new config fields:
  - add them to the dataclasses in `config.py`
  - include defaults
  - write them in `Config.save()`

### UI / Tray

- Keep GUI dependencies optional; avoid importing GUI modules from the CLI path.
- UI actions that might block should run off the tray/UI thread.

### External Side Effects

- Typing/pasting affects the active application.
  - Keep delays minimal but reliable; do not remove clipboard restore behavior unless you replace it with something safer.
- Hotkey registration should be centralized and always cleaned up on exit.

### What Not To Touch

- Do not edit `venv/` or `venv_cuda/` contents; treat them as generated.
- Ignore `__pycache__/` and `output.log`.
