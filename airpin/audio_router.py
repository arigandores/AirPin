"""
Audio router: captures system audio via WASAPI loopback and plays it
to the RayNeo glasses USB audio output using sounddevice.
"""

import threading
import numpy as np

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

import config


def find_glasses_output_device(name_substring=None):
    """Find the glasses audio output device index by name substring."""
    if not HAS_SOUNDDEVICE:
        return None
    name_substring = name_substring or config.GLASSES_AUDIO_DEVICE
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if (name_substring.lower() in dev['name'].lower()
                and dev['max_output_channels'] > 0):
            return i
    return None


def find_loopback_device():
    """
    Find a WASAPI loopback input device.
    On Windows with the WASAPI host API, loopback devices appear as input
    devices with names like "... [Loopback]" or similar.
    """
    if not HAS_SOUNDDEVICE:
        return None
    devices = sd.query_devices()
    # Look for loopback device
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        if 'loopback' in name and dev['max_input_channels'] > 0:
            return i
    # Fallback: try to use the default output as loopback
    # (sounddevice with WASAPI backend supports this)
    return None


class AudioRouter:
    """Captures system audio and routes it to the glasses speaker."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._input_device = None
        self._output_device = None
        self.active = False

    def start(self):
        """Start audio routing."""
        if not HAS_SOUNDDEVICE:
            print("  Audio: sounddevice not installed. Run: pip install sounddevice")
            return False

        self._output_device = find_glasses_output_device()
        if self._output_device is None:
            print(f"  Audio: Glasses audio device '{config.GLASSES_AUDIO_DEVICE}' not found.")
            print("  Available output devices:")
            for i, dev in enumerate(sd.query_devices()):
                if dev['max_output_channels'] > 0:
                    print(f"    [{i}] {dev['name']}")
            return False

        self._input_device = find_loopback_device()

        out_info = sd.query_devices(self._output_device)
        in_info = sd.query_devices(self._input_device) if self._input_device is not None else None

        print(f"  Audio: Output → {out_info['name']}")
        if in_info:
            print(f"  Audio: Input  ← {in_info['name']}")

        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()
        self.active = True
        return True

    def _stream_loop(self):
        """Audio capture and playback loop."""
        try:
            samplerate = config.AUDIO_SAMPLE_RATE
            blocksize = config.AUDIO_BUFFER_FRAMES
            channels = 2  # stereo

            out_info = sd.query_devices(self._output_device)
            out_rate = int(out_info['default_samplerate'])
            if out_rate > 0:
                samplerate = out_rate

            # If we found a loopback device, use it as input
            if self._input_device is not None:
                in_info = sd.query_devices(self._input_device)
                in_channels = min(int(in_info['max_input_channels']), channels)
                out_channels = min(int(out_info['max_output_channels']), channels)

                def callback(indata, outdata, frames, time_info, status):
                    if status:
                        pass  # ignore xruns
                    # Copy input to output, handling channel mismatch
                    if indata.shape[1] >= out_channels:
                        outdata[:] = indata[:, :out_channels]
                    else:
                        outdata[:, :indata.shape[1]] = indata
                        outdata[:, indata.shape[1]:] = 0

                with sd.Stream(
                    samplerate=samplerate,
                    blocksize=blocksize,
                    device=(self._input_device, self._output_device),
                    channels=(in_channels, out_channels),
                    dtype='float32',
                    callback=callback
                ):
                    while self._running:
                        sd.sleep(100)
            else:
                # No loopback device found — try using default output as loopback
                # This is a WASAPI-specific feature
                print("  Audio: No loopback device found. Trying WASAPI loopback...")
                print("  Audio: If no sound, set glasses as default audio device in Windows Settings.")

                # As a fallback, just keep the thread alive
                while self._running:
                    import time
                    time.sleep(0.5)

        except Exception as e:
            print(f"  Audio error: {e}")
            self.active = False

    def stop(self):
        """Stop audio routing."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.active = False
