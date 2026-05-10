import ctypes
import time
from ctypes import wintypes
from typing import Optional

import keyboard
import pyautogui
import pyperclip


# Disable pyautogui's fail-safe (moving mouse to corner won't abort)
pyautogui.FAILSAFE = False

# Set a small pause between keystrokes for reliability
pyautogui.PAUSE = 0.01


# Terminal/emulator executables where Ctrl+V is unreliable for paste —
# either because the terminal binds paste to Ctrl+Shift+V, or because the
# hosted TUI app (e.g. readline "quoted-insert") consumes Ctrl+V itself.
_CTRL_SHIFT_V_TARGETS = {
    "windowsterminal.exe",
    "wezterm-gui.exe",
    "wezterm.exe",
    "alacritty.exe",
    "mintty.exe",
    "hyper.exe",
    "tabby.exe",
    "conemu.exe",
    "conemu64.exe",
}


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


def get_foreground_exe() -> Optional[str]:
    """Return the lowercase exe filename of the foreground window's process."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None

    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None

    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1].lower()
        return None
    finally:
        _kernel32.CloseHandle(handle)


def _paste_hotkey_for_target() -> str:
    """Pick the right paste hotkey based on the foreground window's exe."""
    exe = get_foreground_exe()
    if exe and exe in _CTRL_SHIFT_V_TARGETS:
        return "ctrl+shift+v"
    return "ctrl+v"


def _wait_for_clipboard(expected: str, timeout: float = 0.5) -> bool:
    """Poll until pyperclip.paste() == expected, or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if pyperclip.paste() == expected:
                return True
        except Exception:
            pass  # Clipboard temporarily locked by another app
        time.sleep(0.005)
    return False


def type_text(text: str, interval: float = 0.01):
    """Type text via keystroke simulation (no clipboard)."""
    if not text:
        return
    pyautogui.write(text, interval=interval)


def type_text_slow(text: str, interval: float = 0.05):
    """Type text with a slower interval for visibility."""
    type_text(text, interval=interval)


def paste_text(text: str):
    """
    Paste text via the clipboard.

    - Saves and restores the previous clipboard contents.
    - Polls until the clipboard actually holds the new text before sending
      the paste keystroke (avoids racing the OS clipboard sync).
    - Picks Ctrl+Shift+V for terminal emulators where Ctrl+V is unreliable.
    - Uses keyboard.send() rather than pyautogui.hotkey() — keyboard tracks
      modifier state on Windows more reliably across windows/TUIs.
    """
    if not text:
        return

    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        old_clipboard = ""

    # Retry the copy in case the clipboard is briefly held by another app
    copied = False
    for _ in range(3):
        try:
            pyperclip.copy(text)
            copied = True
            break
        except Exception:
            time.sleep(0.05)
    if not copied:
        return

    if not _wait_for_clipboard(text, timeout=0.5):
        # Clipboard never reflected our text — bail rather than pasting stale data
        return

    hotkey = _paste_hotkey_for_target()
    keyboard.send(hotkey)

    # Give the target app time to consume the clipboard before we restore it
    time.sleep(0.1)

    try:
        pyperclip.copy(old_clipboard)
    except Exception:
        pass


class TextTyper:
    """Text typer with configurable behavior."""

    def __init__(
        self,
        use_clipboard: bool = True,
        typing_interval: float = 0.01,
    ):
        self.use_clipboard = use_clipboard
        self.typing_interval = typing_interval

    def type(self, text: str):
        """Type or paste the given text."""
        if not text:
            return

        if self.use_clipboard:
            paste_text(text)
        else:
            type_text(text, interval=self.typing_interval)

    def paste(self, text: str):
        """Always paste via clipboard, regardless of use_clipboard."""
        paste_text(text)

    def type_with_prefix(self, text: str, prefix: str = "", suffix: str = ""):
        """Type text with optional prefix and suffix."""
        full_text = f"{prefix}{text}{suffix}"
        self.type(full_text)
