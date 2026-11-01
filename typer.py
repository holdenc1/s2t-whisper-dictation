import ctypes
import time
from ctypes import wintypes
from typing import Callable, Optional

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

# Clipboard and global-memory calls used to save and restore the clipboard.
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
_user32.EnumClipboardFormats.restype = wintypes.UINT
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
_user32.RegisterClipboardFormatW.restype = wintypes.UINT
_user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL

_CF_DIB = 8
_CF_UNICODETEXT = 13
_CF_HDROP = 15
_CF_DIBV5 = 17
_GMEM_MOVEABLE = 0x0002

# Formats saved before a paste and put back after it: plain, rich and HTML
# text, images (DIB and PNG; Windows rebuilds CF_BITMAP from the DIB) and
# copied files. Only these, not every format: reading an app's other formats
# (Word and Excel offer a dozen) makes it render each one, which can be slow
# and large. Anything else on the clipboard is lost, as it was before.
_KEEP_FORMATS = {_CF_UNICODETEXT, _CF_DIB, _CF_DIBV5, _CF_HDROP}
_KEEP_FORMAT_NAMES = (
    "HTML Format",
    "Rich Text Format",
    "PNG",
    "Shell IDList Array",
    "Preferred DropEffect",
    "FileNameW",
    "FileName",
)

# Seconds between the paste keystroke and putting the old clipboard back. The
# old 0.1 s was short enough that a busy app or a Remote Desktop window could
# read the clipboard after the restore and paste the old contents instead.
# main_gui.py waits this out after the talk key is live again, so it costs no
# responsiveness, and the restore is skipped if anything new was copied.
RESTORE_DELAY = 1.0


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


def _open_clipboard(hwnd: Optional[int]) -> bool:
    """OpenClipboard, retrying for about half a second while another app has it."""
    for _ in range(25):
        if _user32.OpenClipboard(hwnd):
            return True
        time.sleep(0.02)
    return False


def _save_clipboard() -> Optional[list[tuple[int, bytes]]]:
    """Copy the clipboard's _KEEP_FORMATS into memory, in the order they are
    listed there. None if the clipboard could not be opened."""
    keep = _KEEP_FORMATS | {_user32.RegisterClipboardFormatW(n) for n in _KEEP_FORMAT_NAMES}
    if not _open_clipboard(None):
        return None
    saved = []
    try:
        fmt = _user32.EnumClipboardFormats(0)
        while fmt:
            if fmt in keep:
                handle = _user32.GetClipboardData(fmt)
                ptr = _kernel32.GlobalLock(handle) if handle else None
                if ptr:
                    try:
                        saved.append((fmt, ctypes.string_at(ptr, _kernel32.GlobalSize(handle))))
                    finally:
                        _kernel32.GlobalUnlock(handle)
            fmt = _user32.EnumClipboardFormats(fmt)
    finally:
        _user32.CloseClipboard()
    return saved


def _restore_clipboard(saved: list[tuple[int, bytes]]) -> None:
    """Replace the clipboard with formats from _save_clipboard()."""
    # A hidden window owns the clipboard while writing, as pyperclip does:
    # with no owner window, SetClipboardData may fail.
    hwnd = _user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)
    try:
        if not _open_clipboard(hwnd):
            return
        try:
            _user32.EmptyClipboard()
            for fmt, data in saved:
                hmem = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, max(len(data), 1))
                ptr = _kernel32.GlobalLock(hmem) if hmem else None
                if not ptr:
                    if hmem:
                        _kernel32.GlobalFree(hmem)
                    continue
                ctypes.memmove(ptr, data, len(data))
                _kernel32.GlobalUnlock(hmem)
                if not _user32.SetClipboardData(fmt, hmem):
                    _kernel32.GlobalFree(hmem)  # the system took no ownership
        finally:
            _user32.CloseClipboard()
    finally:
        if hwnd:
            _user32.DestroyWindow(hwnd)


def _do_nothing() -> None:
    pass


def type_text(text: str, interval: float = 0.01):
    """Type text via keystroke simulation (no clipboard)."""
    if not text:
        return
    pyautogui.write(text, interval=interval)


def type_text_slow(text: str, interval: float = 0.05):
    """Type text with a slower interval for visibility."""
    type_text(text, interval=interval)


def paste_text(text: str) -> Callable[[], None]:
    """
    Paste text via the clipboard. Returns a function that puts the old
    clipboard back; call it about RESTORE_DELAY seconds later, once the target
    app has read the clipboard.

    - Saves the old clipboard's text, rich text, HTML, images and copied files
      (see _KEEP_FORMATS), not just its plain text.
    - Polls until the clipboard actually holds the new text before sending
      the paste keystroke (avoids racing the OS clipboard sync).
    - Picks Ctrl+Shift+V for terminal emulators where Ctrl+V is unreliable.
    - Uses keyboard.send() rather than pyautogui.hotkey() — keyboard tracks
      modifier state on Windows more reliably across windows/TUIs.
    - The returned restore does nothing if anything new was copied meanwhile.
    """
    if not text:
        return _do_nothing

    saved = _save_clipboard()

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
        return _do_nothing

    if not _wait_for_clipboard(text, timeout=0.5):
        # Clipboard never reflected our text — bail rather than pasting stale data
        return _do_nothing

    ours = _user32.GetClipboardSequenceNumber()
    hotkey = _paste_hotkey_for_target()
    keyboard.send(hotkey)

    def restore() -> None:
        # The sequence number changes on every clipboard write, so a mismatch
        # means something new was copied since: keep it rather than undo it.
        if saved is None or _user32.GetClipboardSequenceNumber() != ours:
            return
        try:
            _restore_clipboard(saved)
        except Exception:
            pass  # a failed restore must never break dictation

    return restore


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
            self.paste(text)
        else:
            type_text(text, interval=self.typing_interval)

    def paste(self, text: str):
        """Paste via the clipboard, regardless of use_clipboard, then put the old
        clipboard back. Blocks for RESTORE_DELAY."""
        restore = paste_text(text)
        time.sleep(RESTORE_DELAY)
        restore()

    def paste_and_defer_restore(self, text: str) -> Callable[[], None]:
        """Paste now and hand back the clipboard restore, for a caller with other
        work to do first. Run it about RESTORE_DELAY seconds later."""
        return paste_text(text)

    def type_with_prefix(self, text: str, prefix: str = "", suffix: str = ""):
        """Type text with optional prefix and suffix."""
        full_text = f"{prefix}{text}{suffix}"
        self.type(full_text)
