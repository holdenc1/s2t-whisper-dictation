"""Test push-to-talk recording flow."""
import time
import numpy as np
import sounddevice as sd
import keyboard

print("=" * 50)
print("Push-to-Talk Test")
print("=" * 50)
print("Hold SPACE to record, release to see results")
print("Press ESC to quit")
print("=" * 50)

sample_rate = 16000
audio_buffer = []
recording = False
stream = None

def audio_callback(indata, frames, time_info, status):
    global audio_buffer, recording
    if status:
        print(f"Status: {status}")
    if recording:
        audio_buffer.append(indata.copy())

# Start the audio stream
stream = sd.InputStream(
    samplerate=sample_rate,
    channels=1,
    dtype=np.float32,
    callback=audio_callback,
)
stream.start()
print("\nAudio stream started. Ready!")

try:
    while True:
        if keyboard.is_pressed('escape'):
            print("\nExiting...")
            break

        if keyboard.is_pressed('space'):
            if not recording:
                audio_buffer = []
                recording = True
                print("\r[RECORDING...] ", end="", flush=True)
        else:
            if recording:
                recording = False
                if audio_buffer:
                    audio = np.concatenate(audio_buffer, axis=0).flatten()
                    print(f"\r[STOPPED] Captured {len(audio)} samples ({len(audio)/sample_rate:.2f}s)")
                    print(f"  Max amplitude: {np.abs(audio).max():.6f}")
                    print(f"  Mean amplitude: {np.abs(audio).mean():.6f}")
                    if np.abs(audio).max() > 0.01:
                        print("  Audio looks good!")
                    else:
                        print("  WARNING: Audio level is very low")
                else:
                    print("\r[STOPPED] No audio in buffer!")

        time.sleep(0.01)

except KeyboardInterrupt:
    pass
finally:
    stream.stop()
    stream.close()
    print("Done.")
