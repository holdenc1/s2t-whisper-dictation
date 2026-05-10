"""Diagnose and fix stuck modifier keys left behind by the keyboard module."""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Virtual key codes for modifier keys
MODIFIERS = {
    "Left Ctrl":  0xA2,
    "Right Ctrl": 0xA3,
    "Left Shift": 0xA0,
    "Right Shift":0xA1,
    "Left Alt":   0xA4,
    "Right Alt":  0xA5,
    "Left Win":   0x5B,
    "Right Win":  0x5C,
}

KEYEVENTF_KEYUP = 0x0002

def get_key_state(vk):
    """Returns True if the OS thinks this key is currently held down."""
    state = user32.GetAsyncKeyState(vk)
    return bool(state & 0x8000)

def force_release(vk):
    """Send a key-up event to unstick a modifier key."""
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)

print("=== Modifier Key State Check ===\n")

stuck = []
for name, vk in MODIFIERS.items():
    is_down = get_key_state(vk)
    status = "STUCK DOWN" if is_down else "ok"
    print(f"  {name:12s} (0x{vk:02X}): {status}")
    if is_down:
        stuck.append((name, vk))

if stuck:
    print(f"\nFound {len(stuck)} stuck key(s). Releasing them now...")
    for name, vk in stuck:
        force_release(vk)
        print(f"  Released {name}")
    print("\nRe-checking...")
    still_stuck = []
    for name, vk in stuck:
        if get_key_state(vk):
            still_stuck.append(name)
            print(f"  {name}: STILL STUCK (try physically pressing and releasing it)")
        else:
            print(f"  {name}: fixed")
    if not still_stuck:
        print("\nAll keys released. You should be good now.")
    else:
        print(f"\nSome keys are still stuck. Try physically pressing and releasing: {', '.join(still_stuck)}")
else:
    print("\nNo stuck modifier keys detected. All clear.")
