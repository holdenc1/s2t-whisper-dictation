"""Direct Win32 API key state polling. No hooks, no interference with other apps."""

import ctypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Common virtual key codes
VK_MAP = {
    "ctrl": 0x11,
    "left ctrl": 0xA2,
    "right ctrl": 0xA3,
    "shift": 0x10,
    "left shift": 0xA0,
    "right shift": 0xA1,
    "alt": 0x12,
    "left alt": 0xA4,
    "right alt": 0xA5,
    "win": 0x5B,
    "left win": 0x5B,
    "right win": 0x5C,
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "page up": 0x21,
    "page down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "caps lock": 0x14,
    "num lock": 0x90,
    "scroll lock": 0x91,
    "pause": 0x13,
    "print screen": 0x2C,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "f13": 0x7C, "f14": 0x7D, "f15": 0x7E, "f16": 0x7F,
    "f17": 0x80, "f18": 0x81, "f19": 0x82, "f20": 0x83,
    "f21": 0x84, "f22": 0x85, "f23": 0x86, "f24": 0x87,
    "`": 0xC0, "grave": 0xC0,
    "-": 0xBD, "=": 0xBB,
    "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE,
    ",": 0xBC, ".": 0xBE, "/": 0xBF,
}

# Add letter keys a-z
for c in range(ord('a'), ord('z') + 1):
    VK_MAP[chr(c)] = c - 32  # VK codes for A-Z are 0x41-0x5A

# Add number keys 0-9
for c in range(ord('0'), ord('9') + 1):
    VK_MAP[chr(c)] = c


def _get_vk(key_name: str) -> int:
    """Convert a key name to a virtual key code."""
    name = key_name.strip().lower()
    if name in VK_MAP:
        return VK_MAP[name]
    raise ValueError(f"Unknown key name: {key_name!r}")


def is_pressed(key_name: str) -> bool:
    """Check if a key is currently held down using GetAsyncKeyState (no hooks)."""
    vk = _get_vk(key_name)
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def is_combo_pressed(hotkey: str) -> bool:
    """Check if a hotkey combo like 'ctrl+space' is currently held down."""
    parts = hotkey.strip().lower().split("+")
    return all(is_pressed(part) for part in parts)


def release_modifiers():
    """Force-release all modifier keys to clear stuck state."""
    KEYEVENTF_KEYUP = 0x0002
    for vk in [0xA2, 0xA3, 0xA0, 0xA1, 0xA4, 0xA5, 0x5B, 0x5C]:
        scan = user32.MapVirtualKeyW(vk, 0)
        user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
