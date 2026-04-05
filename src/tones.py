#
# Create tones singleton
#

import threading
import numpy as np
import sounddevice as sd

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
        self.rate = rate
        self.freq = freq
        self._dial_tone_stream = None
        self._ring_timer: threading.Timer | None = None
        self._ring_stop: threading.Event = threading.Event()
        self._ring_tone_dur: float = 1.0
        self._ring_pause_dur: float = 4.0
        self._ring_burst_count: int = 0
        self._ring_signal: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Dial tone – non-blocking
    # ------------------------------------------------------------------

    def beep(self) -> None:
        """Start the 425 Hz dial tone in the background (non-blocking)."""
        if self._dial_tone_stream is not None:
            return
        step = 2 * np.pi * self.freq / self.rate
        phase = {"phi": 0.0}

        def _callback(outdata, frames, time_info, status):
            phi0 = phase["phi"]
            t = phi0 + step * np.arange(frames, dtype=np.float32)
            outdata[:] = (0.1 * np.sin(t)).reshape(-1, 1)
            phase["phi"] = (phi0 + frames * step) % (2 * np.pi)

        self._dial_tone_stream = sd.OutputStream(
            samplerate=self.rate,
            channels=1,
            dtype="float32",
            callback=_callback,
        )
        self._dial_tone_stream.start()
        print("Tones: Dial tone started.")

    def stop(self) -> None:
        """Immediately stop both the dial tone and the ring loop."""
        # stop dial tone stream
        if self._dial_tone_stream is not None:
            try:
                self._dial_tone_stream.stop()
                self._dial_tone_stream.close()
            finally:
                self._dial_tone_stream = None
                print("Tones: Dial tone stopped.")

        # cancel pending ring timer and abort current playback
        self._ring_stop.set()
        if self._ring_timer is not None:
            self._ring_timer.cancel()
            self._ring_timer = None

        # immediately cut off any active sd.play()
        sd.stop()
        #print("Tones: Ring tone stopped.")

    # ------------------------------------------------------------------
    # Ring timer callbacks
    # ------------------------------------------------------------------

    def _fire_burst(self) -> None:
        """Play one ring burst, then schedule _after_burst."""
        if self._ring_stop.is_set():
            self._ring_timer = None
            print("Tones: Ring loop ended.")
            return
        self._ring_burst_count += 1
        print(f"Tones: Ring burst {self._ring_burst_count}.")
        sd.play(self._ring_signal, samplerate=self.rate)
        self._ring_timer = threading.Timer(self._ring_tone_dur, self._after_burst)
        self._ring_timer.start()

    def _after_burst(self) -> None:
        """Called when a burst has finished – schedules the next burst after the pause."""
        if self._ring_stop.is_set():
            self._ring_timer = None
            print("Tones: Ring loop ended.")
            return
        self._ring_timer = threading.Timer(self._ring_pause_dur, self._fire_burst)
        self._ring_timer.start()

    def ring(
        self,
        tone_dur: float = 1.0,
        pause_dur: float = 3.0,
    ) -> None:
        """
        Start the ringing tone sequence (non-blocking).

        Fires repeating bursts of *tone_dur* seconds separated by *pause_dur*
        seconds of silence, driven entirely by threading.Timer callbacks.
        Returns immediately. Call stop() to end at any time.

        :param tone_dur: Duration of each ring burst in seconds.
        :param pause_dur: Silence between bursts in seconds.
        """
        if self._ring_timer is not None:
            return  # already ringing

        self._ring_stop.clear()
        self._ring_tone_dur = tone_dur
        self._ring_pause_dur = pause_dur
        self._ring_burst_count = 0
        self._ring_signal = (
            0.1 * np.sin(
                2 * np.pi * self.freq *
                np.linspace(0, tone_dur, int(self.rate * tone_dur), endpoint=False)
            )
        ).astype(np.float32)

        self._fire_burst()
        print("Tones: Ring tone started.")

    # ------------------------------------------------------------------
    # Blocking tones
    # ------------------------------------------------------------------

    def beepBlocking(self, duration: float = 5.0) -> None:
        """
        Play a single blocking 425 Hz tone.

        :param duration: Duration in seconds.
        """
        t = np.linspace(0, duration, int(self.rate * duration), endpoint=False)
        signal = (0.1 * np.sin(2 * np.pi * self.freq * t)).astype(np.float32)
        sd.play(signal, samplerate=self.rate)
        sd.wait()

    def ringBlocking(
        self,
        repeats: int = 2,
        tone_dur: float = 1.0,
        pause_dur: float = 4.0,
    ) -> None:
        """
        Play the European double-ringing tone sequence (blocking).

        :param repeats: Number of ring bursts.
        :param tone_dur: Duration of each burst in seconds.
        :param pause_dur: Silence between bursts in seconds.
        """
        for i in range(repeats):
            print(f"Tones: Ring tone {i + 1}/{repeats}")
            t = np.linspace(0, tone_dur, int(self.rate * tone_dur), endpoint=False)
            signal = (0.1 * np.sin(2 * np.pi * self.freq * t)).astype(np.float32)
            sd.play(signal, samplerate=self.rate)
            sd.wait()
            if i < repeats - 1:
                print("Tones: Pause.")
                import time
                time.sleep(pause_dur)
        print("Tones: Ringing tone finished.")

# Module-level singleton
tones = Playback()
