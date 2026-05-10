"""System tray icon for Speech-to-Text application."""

import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as Item


class TrayIcon:
    """System tray icon with status indicators."""

    # Status colors
    COLORS = {
        "idle": "#4CAF50",       # Green
        "recording": "#F44336",  # Red
        "processing": "#FF9800", # Orange
    }

    def __init__(
        self,
        on_show: Optional[Callable] = None,
        on_switch_model: Optional[Callable] = None,
        on_switch_device: Optional[Callable] = None,
        on_quit: Optional[Callable] = None,
    ):
        self.on_show = on_show
        self.on_switch_model = on_switch_model
        self.on_switch_device = on_switch_device
        self.on_quit = on_quit

        self._status = "idle"
        self._model = "small"
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def _create_icon_image(self, color: str, size: int = 64) -> Image.Image:
        """Create a circular icon with the given color."""
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Draw filled circle
        margin = 4
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=color,
            outline="#FFFFFF",
            width=2,
        )

        return image

    def _get_menu(self):
        """Create the context menu."""
        return pystray.Menu(
            Item(f"Status: {self._status.replace('_', ' ').title()}", None, enabled=False),
            Item(f"Model: {self._model}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Show Window", lambda: self._run_callback(self.on_show), default=True),
            Item("Next Model", lambda: self._run_callback(self.on_switch_model)),
            Item("Next Device", lambda: self._run_callback(self.on_switch_device)),
            pystray.Menu.SEPARATOR,
            Item("Quit", lambda: self._run_callback(self.on_quit)),
        )

    def _run_callback(self, callback):
        """Run a callback in a separate thread."""
        if callback:
            threading.Thread(target=callback, daemon=True).start()

    def set_status(self, status: str):
        """Update the tray icon status."""
        self._status = status
        color = self.COLORS.get(status, self.COLORS["idle"])

        if self._icon:
            self._icon.icon = self._create_icon_image(color)
            self._icon.menu = self._get_menu()

    def set_model(self, model: str):
        """Update the current model."""
        self._model = model
        if self._icon:
            self._icon.menu = self._get_menu()

    def start(self):
        """Start the tray icon in a separate thread."""
        def run():
            self._icon = pystray.Icon(
                "S2T",
                self._create_icon_image(self.COLORS["idle"]),
                "Speech-to-Text",
                self._get_menu(),
            )
            self._icon.run()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the tray icon."""
        if self._icon:
            self._icon.stop()

    def notify(self, title: str, message: str):
        """Show a notification."""
        if self._icon:
            try:
                self._icon.notify(message, title)
            except:
                pass  # Notifications may not be supported
