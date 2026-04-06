#
# Create tones singleton
#

import os
import ctypes
import ctypes.util
import threading
import numpy as np
import pyaudio


def _suppress_alsa_errors() -> None:
    """
    Install a no-op ALSA error handler to silence the harmless
    'ALSA lib …' messages that PortAudio prints to stderr on Linux.
    """

    try:
        lib_name = ctypes.util.find_library("asound") or "libasound.so.2"
        asound = ctypes.cdll.LoadLibrary(lib_name)
        # Signature: void handler(const char*, int, const char*, int, const char*, ...)
        # Passing NULL replaces the handler with a silent no-op.
        ERROR_HANDLER = ctypes.CFUNCTYPE(
            None,
            ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p,
        )
        asound.snd_lib_error_set_handler(ERROR_HANDLER(0))
    except Exception:
        pass  # not on Linux / libasound not found – silently ignore


class Playback:
    """
    Handles all audio tones that is not part of the AI conversation stream.

    Covers the 425 Hz dial tone (both blocking and non-blocking variants) and
    the ringing tone sequence played before a connection is established.
    """

    def __init__(self, rate: int = 24000, freq: int = 425):
        """
        :param rate: Sample rate in Hz (default 24 000).
        :param freq: Dial-tone frequency in Hz (default 425).
        """
        _suppress_alsa_errors()

        self.rate = rate
        self.freq = freq

        # Single shared PyAudio instance – avoids repeated ALSA init noise.
        self._pa: pyaudio.PyAudio = pyaudio.PyAudio()
        self._dial_tone_stream = None

        self._ring_thread: threading.Thread | None = None
        self._ring_stop: threading.Event = threading.Event()
        self._ring_tone_dur: float = 1.0
        self._ring_pause_dur: float = 4.0
        self._ring_signal: np.ndarray | None = None

        self.is_running = False

    def __del__(self) -> None:
        """Release the shared PyAudio instance on garbage collection."""
        try:
            if self._pa is not None:
                self._pa.terminate()
                self._pa = None
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Dial tone – non-blocking
    # ------------------------------------------------------------------

    def beep(self) -> None:
        """Start the 425 Hz dial tone in the background (non-blocking)."""

        if self.is_running:
            return
        self.is_running = True

        step = 2 * np.pi * self.freq / self.rate
        phase = {"phi": 0.0}

        def _callback(in_data, frame_count, time_info, status):
            phi0 = phase["phi"]
            t = phi0 + step * np.arange(frame_count, dtype=np.float32)
            samples = (0.1 * np.sin(t) * 32767).astype(np.int16)
            phase["phi"] = (phi0 + frame_count * step) % (2 * np.pi)
            return samples.tobytes(), pyaudio.paContinue

        self._dial_tone_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            output=True,
            stream_callback=_callback,
        )
        self._dial_tone_stream.start_stream()
        print("Tones: Dial tone started.")

    def ring(
            self,
            tone_dur: float = 1.0,
            pause_dur: float = 3.0,
    ) -> None:
        """
        Start the ringing tone sequence (non-blocking).

        Fires repeating bursts of *tone_dur* seconds separated by *pause_dur*
        seconds of silence, driven by a background thread.
        Returns immediately. Call stop() to end at any time.

        :param tone_dur: Duration of each ring burst in seconds.
        :param pause_dur: Silence between bursts in seconds.
        """

        if self.is_running:
            return
        self.is_running = True

        print("Tones: Ring tone starting.")

        self._ring_stop.clear()
        self._ring_tone_dur = tone_dur
        self._ring_pause_dur = pause_dur
        self._ring_signal = (
            0.1
            * np.sin(
                2 * np.pi * self.freq
                * np.linspace(0, tone_dur, int(self.rate * tone_dur), endpoint=False)
            )
            * 32767
        ).astype(np.int16)

        self._ring_thread = threading.Thread(target=self._ring_loop, daemon=True)
        self._ring_thread.start()

    def stop(self) -> None:
        """Immediately stop both the dial tone and the ring loop."""

        if not self.is_running:
            return

        print("Tones: Stopping")

        # Stop the dial tone
        if self._dial_tone_stream is not None:
            try:
                self._dial_tone_stream.stop_stream()
                self._dial_tone_stream.close()
            finally:
                self._dial_tone_stream = None
                print("Tones: Dial tone stopped.")

        # Stop the ring tone
        self._ring_stop.set()

        self.is_running = False

    # ------------------------------------------------------------------
    # Ring background thread
    # ------------------------------------------------------------------

    def _ring_loop(self) -> None:
        """Plays ring bursts in a loop until _ring_stop is set."""
        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            output=True,
        )
        burst = 0
        try:
            while not self._ring_stop.is_set():
                burst += 1
                print(f"Tones: Ring burst {burst}.")
                stream.write(self._ring_signal.tobytes())
                # wait for the pause duration, but wake up early on stop()
                if self._ring_stop.wait(self._ring_pause_dur):
                    break
        finally:
            stream.stop_stream()
            stream.close()
            print("Tones: Ring loop ended.")

# Module-level singleton
tones = Playback()
