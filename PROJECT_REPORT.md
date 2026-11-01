# Speech-to-Text (S2T) — Project Report

A local, hotkey-driven dictation tool for Windows. Hold a key, talk, release — your speech is transcribed by OpenAI Whisper running on your own GPU and pasted into whatever app currently has focus (browser, terminal, IDE, chat, anywhere). No cloud, no API costs, no audio leaves your machine.

---

## What it does

- **Push-to-Talk dictation**: hold a hotkey while speaking, release to transcribe.
- **Toggle-to-Talk mode**: press once to start, again to stop.
- **Voice Activation (VAD)**: hands-free — speech is auto-detected and transcribed when you pause.
- **Pastes into the focused app**: detects the foreground window and uses the right paste keystroke (`Ctrl+V` for normal apps, `Ctrl+Shift+V` for terminal emulators like Windows Terminal, WezTerm, Alacritty, etc.).
- **Live UI**: main window shows recording state, real-time mic level meter, scrollable transcript log of recent dictations.
- **System tray**: minimize-to-tray so it stays out of the way; tray menu for quick model/device switching.
- **Text post-processing**: remove filler words (um, uh), spoken punctuation commands ("period" → "."), newline commands ("new line"), informal-to-formal (gonna → going to), auto-capitalization, sentence spacing, trailing space between dictations.
- **Hot-apply settings**: change model / device / hotkeys / mode in the UI and Save — no restart required.
- **Splash screen** while the model loads (first launch is the slowest because Whisper has to download the model weights).

---

## Hardware requirements

| Component | Recommended | Minimum |
|---|---|---|
| **GPU** | NVIDIA with CUDA support, ≥6 GB VRAM for `medium` model, ≥10 GB for `large` | None — falls back to CPU automatically (slower) |
| **CPU** | Any modern x64 | Any x64 capable of running Python 3.12 |
| **RAM** | 8 GB+ | 4 GB |
| **Disk** | ~5 GB free for Python + models | ~2 GB if using small models only |
| **Microphone** | Any Windows-recognized USB or built-in mic | Required |
| **OS** | Windows 10 / 11 | Windows 10 |

**Model size vs hardware**:

| Model | Size on disk | VRAM (float16) | Quality | Speed (RTX A5000 Laptop) |
|---|---|---|---|---|
| `tiny` | ~75 MB | ~1 GB | Low | Real-time on CPU |
| `base` | ~140 MB | ~1 GB | Decent | Fast |
| `small` | ~460 MB | ~2 GB | Good | Fast |
| `medium` | ~1.5 GB | ~5 GB | Very good | ~1× real-time on CPU, near-instant on GPU |
| `large` | ~3 GB | ~10 GB | Best | Needs a GPU for usable latency |

---

## My setup (reference)

| | |
|---|---|
| **OS** | Windows 11 |
| **Python** | 3.12.0 |
| **GPU** | NVIDIA RTX A5000 Laptop GPU |
| **CUDA** | 12.4 (via PyTorch wheels) |
| **PyTorch** | 2.6.0+cu124 |
| **Model in use** | `small` (good balance for live dictation; bumps up to `medium` for accuracy) |

---

## Installed packages (exact versions in my venv)

These are the actual versions running in the working environment:

```
PyAutoGUI            0.9.54
PyYAML               6.0.3
ctranslate2          4.7.1     (Whisper inference backend)
customtkinter        5.2.2     (UI)
faster-whisper       1.2.1     (Whisper wrapper)
keyboard             0.13.5    (global hotkeys)
numpy                2.3.5
pillow               12.1.0    (tray icon rendering)
pyperclip            1.11.0    (clipboard)
pystray              0.19.5    (system tray)
sounddevice          0.5.5     (audio capture)
torch                2.6.0+cu124
torchaudio           2.6.0+cu124
```

The pinned floors in `requirements.txt` are looser than this:

```
faster-whisper>=1.0.0
sounddevice>=0.4.6
numpy>=1.24.0
keyboard>=0.13.5
pyautogui>=0.9.54
pyperclip>=1.8.2
pyyaml>=6.0
torch>=2.0.0
torchaudio>=2.0.0
```

`customtkinter`, `pystray`, and `Pillow` are required for the GUI but not pinned in `requirements.txt` — `setup.bat` and the manual install steps below handle that.

---

## Installation

### Prerequisites

1. **Install Python 3.12** from python.org (check "Add to PATH" during install).
2. **Install NVIDIA driver** (latest game/studio driver) — the CUDA 12.x runtime ships inside the PyTorch wheels, so you don't need to install CUDA separately.
3. Clone or copy the project folder. The layout:
   ```
   s2t/
   ├── main.py                  CLI entry point
   ├── main_gui.py              GUI entry point
   ├── main_window.py           Main window (CustomTkinter)
   ├── transcriber.py           Whisper wrapper (faster-whisper)
   ├── audio.py                 Audio capture (sounddevice)
   ├── hotkeys.py               Hotkey helpers
   ├── keystate.py              Win32 key-state polling
   ├── typer.py                 Target-aware paste
   ├── text_processor.py        Post-transcription text cleanup
   ├── vad.py                   Voice activity detection (Silero VAD + simple RMS)
   ├── tray_icon.py             System tray
   ├── config.py                Config dataclasses + YAML load/save
   ├── config.yaml              User settings (created on first run)
   ├── requirements.txt
   ├── setup.bat                Automated CUDA install
   ├── run.bat                  Launch CLI (CPU venv)
   ├── run_cuda.bat             Launch CLI (CUDA venv)
   └── run_gui.bat              Launch GUI (CUDA venv, no terminal)
   ```

### Option A — Automatic setup (CUDA GPU)

From the project folder, double-click `setup.bat`. It will:

1. Create `venv\` and activate it.
2. Install PyTorch + torchaudio from `https://download.pytorch.org/whl/cu121`.
3. Install the rest of the dependencies.

After that, **also install the GUI deps** (setup.bat doesn't do this):

```bat
venv\Scripts\activate
pip install customtkinter pystray Pillow
```

### Option B — Manual setup (CPU only or custom)

From an admin PowerShell or cmd in the project folder:

```bat
python -m venv venv
venv\Scripts\activate

REM CPU-only PyTorch:
pip install torch torchaudio

REM ...OR CUDA 12.x PyTorch (recommended if you have an NVIDIA GPU):
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

pip install -r requirements.txt
pip install customtkinter pystray Pillow
```

### Option C — Use my exact versions

If you want bit-for-bit the same environment:

```bat
python -m venv venv
venv\Scripts\activate
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
pip install faster-whisper==1.2.1 sounddevice==0.5.5 numpy==2.3.5 keyboard==0.13.5 pyautogui==0.9.54 pyperclip==1.11.0 pyyaml==6.0.3 customtkinter==5.2.2 pystray==0.19.5 pillow==12.1.0
```

### Naming the venv

The launch scripts (`run.bat`, `run_cuda.bat`, `run_gui.bat`) look for specific venv folder names:

- `run.bat` → looks for `venv\`
- `run_cuda.bat` and `run_gui.bat` → look for `venv_cuda\`

If you ran `setup.bat` (which creates `venv\`), either rename it to `venv_cuda` or edit the run scripts. Simplest: just `ren venv venv_cuda` after install.

---

## First run

1. Double-click `run_gui.bat` (no console window appears — it launches via `pythonw.exe`).
2. A splash window appears with status: "Loading Whisper model (small)…".
3. **First time only**: faster-whisper downloads the model from HuggingFace (~460 MB for `small`, ~1.5 GB for `medium`). This is one-time per model size; cached in `%USERPROFILE%\.cache\huggingface\`. Subsequent launches are fast.
4. Main window appears. The system-tray icon appears (green circle).
5. **Hold `Alt + `​`** (Alt + backtick), speak, release. You'll hear an ascending beep on start and a descending beep on stop.
6. Whisper transcribes; the text is pasted wherever your cursor is.

---

## Configuration

All settings live in `config.yaml` (created on first run with sensible defaults) and are editable from the UI tabs. Most changes hot-apply on **Save & Apply** — no restart needed.

### Tabs in the UI

| Tab | What's there |
|---|---|
| **Model** | Whisper model size (tiny/base/small/medium/large), language (auto / en / es / fr / ...), and a word list: names and acronyms Whisper should expect, spelled the way they should be pasted (saved as `vocabulary` in `config.yaml`). |
| **Audio** | Microphone (dropdown, filtered to WASAPI for one entry per real mic), beep volume. Audio is always captured at 16 kHz, the rate Whisper needs; Windows converts each mic's own rate. |
| **Mode & VAD** | Recording mode (push_to_talk / toggle_to_talk / voice_activation), VAD speech threshold and silence duration sliders. |
| **Text** | Master enable + 8 sub-toggles: remove fillers, punctuation commands, newline commands, informal→formal, fix capitalization, ensure sentence spacing, add trailing space, collapse repeated words. |

Every control has a hover-tooltip with detailed explanation.

### Hotkeys (currently set in `config.yaml`, no UI editor)

```yaml
hotkeys:
  push_to_talk: alt+`         # hold to record (or press in toggle mode)
  switch_model: ctrl+shift+m  # cycle through model sizes
  switch_mode:  ctrl+shift+v  # cycle PTT → toggle → VAD
  switch_device: ctrl+shift+d # cycle through input devices
  quit: ctrl+shift+q
```

In the window version only `push_to_talk` and `quit` are live. Switch the model or the mic from the tray menu or the window: Ctrl+Shift+M and Ctrl+Shift+D also fire in other apps (VS Code's Problems panel, Chrome's "bookmark all tabs"), so a stray press used to switch and save the setting. The command-line version (`main.py`) still uses all five.

**Important**: the original default was `ctrl+`​`, but that collides with Claude Code Desktop / VS Code's "Open Terminal" shortcut — when used in those apps, pressing the hotkey opens the terminal panel and steals focus, so the transcription pastes into the terminal instead of the chat input. Changed to `alt+`​`, which is free. Other safe alternatives if Alt collides with anything in your workflow: `scroll lock`, `pause`, `f13` (if your keyboard has it).

---

## How it works (architecture)

1. **`sounddevice` audio callback** runs on PortAudio's background thread, continuously streaming mic input. The callback computes RMS level (for the meter) every block and appends to a buffer when recording is active.
2. **Hotkey detection**: `keyboard` library installs a low-level Windows keyboard hook for utility hotkeys (model switch, mode switch, etc.). The PTT key is polled via `GetAsyncKeyState` from the Tk UI tick (no hook = no risk of stuck modifier keys).
3. **Transcription** happens on a dedicated worker thread. When recording ends, the audio buffer is pushed onto a `queue.Queue`. The worker thread pulls jobs, calls `faster-whisper` (CTranslate2 backend, float16 on CUDA / int8 on CPU), runs the result through the text processor, then pastes.
4. **Paste path** ([typer.py](typer.py)): identifies the foreground window's exe via `GetForegroundWindow` + `QueryFullProcessImageName`, picks `Ctrl+Shift+V` for known terminal emulators (Windows Terminal, WezTerm, Alacritty, mintty, Hyper, Tabby, ConEmu) and `Ctrl+V` for everything else. Saves the clipboard's text, rich text, HTML, images and copied files, copies the new text, polls until the clipboard actually contains it (to avoid race conditions), sends the paste keystroke via the `keyboard` library, and about a second later restores the old clipboard (skipped if you copied something new in the meantime). The talk key works again before that wait.
5. **UI**: Tk owns the main thread. CustomTkinter for the styled widgets. The UI tick (every 33 ms) reads the latest audio level (with exponential smoothing) and updates the meter and status pill. Transcriptions are marshaled back from the worker to the Tk thread via `window.after(0, …)`.

---

## Usage tips

- **Best mic placement**: 6–12 inches from your mouth, off-axis (not pointing straight at it) to reduce plosives. Watch the level meter — peaks should be in the upper third of the bar, not pinning the top.
- **Pinning the language** (instead of "auto") makes Whisper noticeably faster and more accurate. Auto-detect runs on the first ~30 seconds of every utterance.
- **`small` is the sweet spot** for live dictation. `medium` is more accurate but ~3× slower; only worth it if you find yourself correcting Whisper a lot. `tiny` and `base` are noticeably worse with technical terms or proper nouns.
- **VAD mode** is great for long-form note-taking when you don't want to hold a key, but it can cut you off if you pause for too long mid-sentence — bump the silence duration to 2–3 seconds.
- **Punctuation commands**: leave OFF unless you want to dictate code or formatted text. They turn the word "period" into "." which is annoying for normal prose.
- **Sentence spacing + trailing space**: leave ON. They ensure two consecutive dictations don't collide (`First sentence.Second sentence.` → `First sentence. Second sentence.`).

---

## Known quirks

- **Claude Code Desktop / VS Code**: don't use `ctrl+`​` as the PTT key — collides with the built-in "Toggle Terminal" shortcut. Use `alt+`​` (current default) or a non-modifier key.
- **Microphone list**: by default the UI filters to **WASAPI-only** devices so you see one entry per physical mic. Without that filter, PortAudio enumerates every mic once per host API (MME, DirectSound, WASAPI, WDM-KS) which gives ~4× too many entries.
- **First model load is slow** — Whisper downloads weights from HuggingFace. Subsequent launches use the cached weights and start in a few seconds.
- **Console hidden under pythonw.exe**: all output goes to `startup.log` in the project folder. If anything misbehaves, that's the first place to look. It records each clip's length and how long Whisper took, not your words; those stay in the window's Recent Transcriptions list.
- **Window placement on multi-monitor setups**: the window is re-centered on the primary monitor each launch (otherwise Tk would remember a position on a since-disconnected monitor).

---

## Files to send your friend

The whole project folder, but in particular the source files (~12 Python files, total ~2000 lines) and these:

- `setup.bat`
- `run_gui.bat`
- `requirements.txt`
- `config.yaml` (or let it generate fresh on first run)
- This `PROJECT_REPORT.md`

That's everything. After installing, they just double-click `run_gui.bat`, wait for the model to download once, hold `Alt+`​` and start talking.
