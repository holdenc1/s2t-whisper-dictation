from typing import Callable, Optional
import keyboard


class HotkeyHandler:
    def __init__(self):
        self._registered_hotkeys: list[tuple[str, Callable]] = []
        self._ptt_key: Optional[str] = None
        self._ptt_press_callback: Optional[Callable] = None
        self._ptt_release_callback: Optional[Callable] = None
        self._ptt_pressed = False

    def register_hotkey(self, hotkey: str, callback: Callable):
        """Register a hotkey that triggers on press."""
        keyboard.add_hotkey(hotkey, callback)
        self._registered_hotkeys.append((hotkey, callback))

    def register_push_to_talk(
        self,
        hotkey: str,
        on_press: Callable,
        on_release: Callable,
    ):
        """Register push-to-talk hotkey (hold to record, release to stop)."""
        self._ptt_key = hotkey
        self._ptt_press_callback = on_press
        self._ptt_release_callback = on_release

        # Handle key press
        def on_key_down(e):
            if not self._ptt_pressed:
                self._ptt_pressed = True
                if self._ptt_press_callback:
                    self._ptt_press_callback()

        # Handle key release
        def on_key_up(e):
            if self._ptt_pressed:
                self._ptt_pressed = False
                if self._ptt_release_callback:
                    self._ptt_release_callback()

        keyboard.on_press_key(hotkey.split("+")[-1], on_key_down)
        keyboard.on_release_key(hotkey.split("+")[-1], on_key_up)

        # For combo hotkeys (ctrl+space), we need different handling
        if "+" in hotkey:
            # Use a hook to check modifiers
            modifiers = hotkey.split("+")[:-1]
            key = hotkey.split("+")[-1]

            def check_combo_press(e):
                if e.name == key and e.event_type == "down":
                    if all(keyboard.is_pressed(mod) for mod in modifiers):
                        if not self._ptt_pressed:
                            self._ptt_pressed = True
                            if self._ptt_press_callback:
                                self._ptt_press_callback()
                            return False  # Suppress
                return True

            def check_combo_release(e):
                if e.name == key and e.event_type == "up":
                    if self._ptt_pressed:
                        self._ptt_pressed = False
                        if self._ptt_release_callback:
                            self._ptt_release_callback()
                        return False  # Suppress
                return True

            # Remove the simple handlers and add combo handlers
            keyboard.unhook_all()
            keyboard.hook(check_combo_press)
            keyboard.hook(check_combo_release)

    def unregister_push_to_talk(self):
        """Unregister the push-to-talk hotkey."""
        self._ptt_key = None
        self._ptt_press_callback = None
        self._ptt_release_callback = None
        self._ptt_pressed = False

    def clear_all(self):
        """Remove all registered hotkeys."""
        keyboard.unhook_all()
        self._registered_hotkeys = []
        self._ptt_key = None
        self._ptt_press_callback = None
        self._ptt_release_callback = None
        self._ptt_pressed = False


class HotkeyManager:
    """High-level hotkey manager for the S2T application."""

    def __init__(self):
        self._hotkeys: dict[str, int] = {}

    def register(
        self,
        name: str,
        hotkey: str,
        callback: Callable,
    ):
        """Register a named hotkey."""
        hook_id = keyboard.add_hotkey(hotkey, callback)
        self._hotkeys[name] = hook_id

    def unregister(self, name: str):
        """Unregister a hotkey by name."""
        if name in self._hotkeys:
            keyboard.remove_hotkey(self._hotkeys[name])
            del self._hotkeys[name]

    def clear_all(self):
        """Remove all hotkeys."""
        for hook_id in self._hotkeys.values():
            try:
                keyboard.remove_hotkey(hook_id)
            except:
                pass
        self._hotkeys = {}
