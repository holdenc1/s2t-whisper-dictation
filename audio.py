import threading
from typing import Optional, Callable
import numpy as np
import sounddevice as sd


def _wasapi_hostapi_index() -> Optional[int]:
    """Return the host-API index for Windows WASAPI, or None if not present."""
    try:
        for i, api in enumerate(sd.query_hostapis()):
            if "WASAPI" in api["name"]:
                return i
    except Exception:
        pass
    return None


def wasapi_extra_settings(device: Optional[int]) -> Optional[sd.WasapiSettings]:
    """Stream settings that let a WASAPI mic record at Whisper's 16 kHz.

    In shared mode a WASAPI mic opens only at its own rate (48 kHz on every mic
    tested 2026-11-01) and refuses 16 kHz with "Invalid sample rate".
    auto_convert asks Windows to convert. Returns None for other host APIs (the
    "Default" device is MME, which converts on its own), because PortAudio
    rejects WASAPI settings on a non-WASAPI device."""
    try:
        idx = device if device is not None else sd.default.device[0]
        if sd.query_devices(idx)["hostapi"] == _wasapi_hostapi_index():
            return sd.WasapiSettings(auto_convert=True)
    except Exception:
        pass
    return None


def list_audio_devices(prefer_wasapi: bool = True):
    """List available audio input devices.

    On Windows, PortAudio enumerates every physical mic once per host API
    (MME, DirectSound, WASAPI, WDM-KS), so a 3-mic system shows ~12+ entries.
    By default we filter to WASAPI only — modern, low-latency, doesn't lock
    the device — which gives one entry per physical mic. Pass
    prefer_wasapi=False to see the unfiltered list.
    """
    devices = sd.query_devices()
    target_api = _wasapi_hostapi_index() if prefer_wasapi else None

    input_devices = []
    for idx, device in enumerate(devices):
        if device["max_input_channels"] <= 0:
            continue
        if target_api is not None and device["hostapi"] != target_api:
            continue
        input_devices.append((idx, device))

    # Fallback: if WASAPI filtering produced nothing, show everything so the
    # user isn't left with an empty dropdown on a quirky system.
    if prefer_wasapi and not input_devices:
        return list_audio_devices(prefer_wasapi=False)

    return input_devices


def select_audio_device(config) -> Optional[int]:
    """
    Display available audio input devices and prompt user to select one.
    Returns the device index or None to use default.
    """
    print("\n" + "=" * 60)
    print("Available Audio Input Devices:")
    print("=" * 60)

    input_devices = list_audio_devices()

    if not input_devices:
        print("No audio input devices found!")
        return None

    # Get current device
    current_device = config.audio.device

    for i, (idx, device) in enumerate(input_devices, 1):
        is_current = " (current)" if idx == current_device else ""
        is_default = " [DEFAULT]" if idx == sd.default.device[0] else ""
        print(f"{i}. [{idx}] {device['name']}{is_default}{is_current}")
        print(f"   Channels: {device['max_input_channels']}, Sample Rate: {device['default_samplerate']:.0f} Hz")

    print("-" * 60)
    print("Enter device number (or press Enter to use default):")

    while True:
        try:
            choice = input("> ").strip()

            if choice == "":
                # Use default
                print(f"Using default device: {sd.query_devices(sd.default.device[0])['name']}")
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(input_devices):
                selected_idx = input_devices[choice_num - 1][0]
                selected_device = input_devices[choice_num - 1][1]
                print(f"Selected: {selected_device['name']}")
                return selected_idx
            else:
                print(f"Please enter a number between 1 and {len(input_devices)} (or press Enter for default)")
        except ValueError:
            print("Invalid input. Please enter a number (or press Enter for default)")
        except KeyboardInterrupt:
            print("\nUsing current configuration")
            return current_device


def select_audio_device_runtime(current_device: Optional[int]) -> Optional[int]:
    """
    Display available audio input devices and prompt user to select one during runtime.
    Returns the device index or None to keep current device.
    """
    print("\n" + "=" * 60)
    print("Switch Audio Device:")
    print("=" * 60)

    input_devices = list_audio_devices()

    if not input_devices:
        print("No audio input devices found!")
        return current_device

    for i, (idx, device) in enumerate(input_devices, 1):
        is_current = " (CURRENT)" if idx == current_device else ""
        is_default = " [DEFAULT]" if idx == sd.default.device[0] else ""
        print(f"{i}. [{idx}] {device['name']}{is_default}{is_current}")

    print("-" * 60)
    print("Enter device number (or press Enter to cancel):")

    while True:
        try:
            choice = input("> ").strip()

            if choice == "":
                # Cancel
                print("Cancelled - keeping current device")
                return current_device

            choice_num = int(choice)
            if 1 <= choice_num <= len(input_devices):
                selected_idx = input_devices[choice_num - 1][0]
                selected_device = input_devices[choice_num - 1][1]
                print(f"Switched to: {selected_device['name']}")
                return selected_idx
            else:
                print(f"Please enter a number between 1 and {len(input_devices)} (or press Enter to cancel)")
        except ValueError:
            print("Invalid input. Please enter a number (or press Enter to cancel)")
        except KeyboardInterrupt:
            print("\nCancelled - keeping current device")
            return current_device


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[int] = None,
        channels: int = 1,
    ):
        self.sample_rate = sample_rate
        self.device = device
        self.channels = channels
        self.recording = False
        self.audio_buffer: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"Audio status: {status}")
        if self.recording:
            with self._lock:
                self.audio_buffer.append(indata.copy())

    def start(self):
        """Start recording audio."""
        with self._lock:
            self.audio_buffer = []
            self.recording = True

        if self._stream is None:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                device=self.device,
                channels=self.channels,
                dtype=np.float32,
                callback=self._audio_callback,
            )
            self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop recording and return the audio buffer."""
        self.recording = False

        with self._lock:
            if not self.audio_buffer:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self.audio_buffer, axis=0)
            self.audio_buffer = []

        return audio.flatten()

    def get_current_buffer(self) -> np.ndarray:
        """Get a copy of the current audio buffer without stopping."""
        with self._lock:
            if not self.audio_buffer:
                return np.array([], dtype=np.float32)
            return np.concatenate(self.audio_buffer, axis=0).flatten()

    def clear_buffer(self):
        """Clear the audio buffer."""
        with self._lock:
            self.audio_buffer = []

    def close(self):
        """Close the audio stream."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class ContinuousAudioRecorder:
    """Continuously records audio, useful for VAD mode."""

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[int] = None,
        channels: int = 1,
        chunk_callback: Optional[Callable[[np.ndarray], None]] = None,
        chunk_duration: float = 0.1,
    ):
        self.sample_rate = sample_rate
        self.device = device
        self.channels = channels
        self.chunk_callback = chunk_callback
        self.chunk_samples = int(sample_rate * chunk_duration)
        self._stream: Optional[sd.InputStream] = None
        self._running = False

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"Audio status: {status}")
        if self._running and self.chunk_callback:
            self.chunk_callback(indata.copy().flatten())

    def start(self):
        """Start continuous recording."""
        self._running = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            device=self.device,
            channels=self.channels,
            dtype=np.float32,
            callback=self._audio_callback,
            blocksize=self.chunk_samples,
        )
        self._stream.start()

    def stop(self):
        """Stop continuous recording."""
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
