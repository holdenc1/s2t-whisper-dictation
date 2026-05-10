"""Test microphone input."""
import sounddevice as sd
import numpy as np

print("=" * 50)
print("Microphone Test")
print("=" * 50)

# List all audio devices
print("\nAvailable audio devices:")
print(sd.query_devices())

print("\n" + "-" * 50)
print(f"Default input device: {sd.default.device[0]}")
print(f"Default output device: {sd.default.device[1]}")

# Test recording
print("\n" + "=" * 50)
print("Recording 3 seconds of audio...")
print("Speak into your microphone NOW!")
print("=" * 50)

duration = 3  # seconds
sample_rate = 16000

try:
    audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype=np.float32)
    sd.wait()  # Wait for recording to finish

    print(f"\nRecording complete!")
    print(f"Audio shape: {audio.shape}")
    print(f"Audio dtype: {audio.dtype}")
    print(f"Max amplitude: {np.abs(audio).max():.6f}")
    print(f"Mean amplitude: {np.abs(audio).mean():.6f}")

    if np.abs(audio).max() < 0.001:
        print("\n⚠️  WARNING: Very low audio level detected!")
        print("   This could mean:")
        print("   - Microphone is muted")
        print("   - Wrong input device selected")
        print("   - Microphone permissions not granted")
    else:
        print("\n✓ Audio captured successfully!")

except Exception as e:
    print(f"\n❌ Error recording: {e}")

input("\nPress Enter to exit...")
