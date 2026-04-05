#
# Create conversation singleton
#

import os
import queue
import threading
import time
import wave
import datetime
import random

import numpy as np
import pyaudio

from config.roles import roles as roles
from src.connection import Connection

class Conversation:
    """
    Manages a single telephone conversation session.

    Opens microphone and speaker audio streams, records the microphone input
    to a timestamped WAV file, and drives the OpenAI Realtime WebSocket
    connection for the duration of the call.

    Call start() to launch the session in a background thread (non-blocking).
    The caller is responsible for calling stop() when the handset is hung up.
    """

    def __init__(self):
        self.role = None
        self.greeting = False

        # Is set after calling start() or stop()
        # To see whether the thread is active, use the is_active property
        # To see whether the conversation is ready, use the is_ready property
        self.is_running = False

        self.audio_buffer = bytearray()
        self.mic_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()

        self._thread: threading.Thread | None = None
        self._mic_wav_file: wave.Wave_write | None = None
        self._mic_on_at: float = 0.0

        self.chunk_size = 2048
        self.format = pyaudio.paInt16
        self.reengage_delay = 500
        self.rate = 24000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, role: int | None = None, greeting: bool = True) -> None:
        """
        Start the conversation in a background thread (non-blocking).

        Returns immediately. Use is_active to check whether the session is
        still active, and stop() to end it.

        :param role: 1-based role index from the rotary dial, or None for random.
        :param greeting: Whether to inject the greeting WAV at the start of the session.
        """
        if self.is_running:
            return

        self.is_running = True

        self.role = role
        self.greeting = "assets/greeting.wav" if greeting else None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the conversation to end and wait for the thread to finish."""
        if not self.is_active:
            return

        print("Conversation: Stopping...")
        self.stop_event.set()
        self.ready_event.clear()
        if self._thread:
            self._thread.join(timeout=5)
        self.is_running = False

    @property
    def is_active(self) -> bool:
        """True while the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_ready(self) -> bool:
        """True if the conversation just started and is ready."""
        if self.ready_event.is_set():
            self.ready_event.clear()
            return True

        return False

    # ------------------------------------------------------------------
    # Private – blocking implementation (runs inside the thread)
    # ------------------------------------------------------------------

    def _run(self, record = False) -> None:
        """Blocking session body – executed inside the background thread."""
        self._reset()

        if record:
            self._start_recording()

        p = pyaudio.PyAudio()
        mic_stream = p.open(
            format=self.format,
            channels=1,
            rate=self.rate,
            input=True,
            stream_callback=self._mic_callback,
            frames_per_buffer=self.chunk_size,
        )
        speaker_stream = p.open(
            format=self.format,
            channels=1,
            rate=self.rate,
            output=True,
            stream_callback=self._speaker_callback,
            frames_per_buffer=self.chunk_size,
        )

        role = self._resolve_role()
        print(f"Conversation: Role: {role['name']}")

        persons = [None]

        try:
            mic_stream.start_stream()
            speaker_stream.start_stream()

            Connection(
                self.mic_queue,
                self.audio_buffer,
                self.stop_event,
                self.ready_event,
                [role],
                persons,
                greeting=self.greeting,
            ).connect()

        except Exception as e:
            print(f"Conversation: Error {e}")

        finally:
            mic_stream.stop_stream()
            mic_stream.close()
            speaker_stream.stop_stream()
            speaker_stream.close()
            p.terminate()
            self._stop_recording()
            print("Conversation: Ended.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        """Clear all buffers and reset the stop flag for a fresh session."""
        self.stop_event.clear()
        self.ready_event.clear()
        self.audio_buffer.clear()
        while not self.mic_queue.empty():
            self.mic_queue.get_nowait()

    def _start_recording(self) -> None:
        """Open a timestamped WAV file to record the microphone input."""
        os.makedirs("recordings", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_path = os.path.join("recordings", f"mic_{timestamp}.wav")
        self._mic_wav_file = wave.open(wav_path, "wb")
        self._mic_wav_file.setnchannels(1)
        self._mic_wav_file.setsampwidth(2)   # paInt16 = 2 bytes
        self._mic_wav_file.setframerate(self.rate)
        print(f"Recording: Started in {wav_path}")

    def _stop_recording(self) -> None:
        """Flush and close the microphone WAV file."""
        if self._mic_wav_file is not None:
            self._mic_wav_file.close()
            self._mic_wav_file = None

    def _resolve_role(self) -> dict:
        """Return the role dict for the selected role number, or the default role."""

        # Default to first role
        if self.role is None:
            self.role = 0

        # Select role by number
        if 0 <= self.role < len(roles):
            return roles[self.role]

        print("Conversation: Invalid role number, choosing randomly.")
        return random.choice(roles)

    def _process_audio(self, data: bytes) -> bytes:
        """
        Apply DC-offset removal, noise gate, smoothing and clipping to a PCM16 chunk.

        :param data: Raw PCM16 bytes from the microphone.
        :return: Processed PCM16 bytes.
        """
        audio = np.frombuffer(data, dtype=np.int16).copy().astype(np.float32)
        audio -= audio.mean()                                   # DC offset
        if np.abs(audio).mean() < 500:                         # noise gate
            audio[:] = 0
        else:
            audio = np.convolve(audio, np.ones(5) / 5, mode="same")   # smooth
        audio = np.clip(audio, -32768, 32767)
        return audio.astype(np.int16).tobytes()

    # ------------------------------------------------------------------
    # PyAudio stream callbacks
    # ------------------------------------------------------------------

    def _mic_callback(self, in_data, frame_count, time_info, status):
        """PyAudio input callback – processes and enqueues microphone audio."""
        in_data = self._process_audio(in_data)
        self.mic_queue.put(in_data)
        if self._mic_wav_file is not None:
            self._mic_wav_file.writeframes(in_data)
        return None, pyaudio.paContinue

    def _speaker_callback(self, in_data, frame_count, time_info, status):
        """PyAudio output callback – drains the AI audio buffer to the speaker."""
        bytes_needed = frame_count * 2
        if len(self.audio_buffer) >= bytes_needed:
            chunk = bytes(self.audio_buffer[:bytes_needed])
            self.audio_buffer[:] = self.audio_buffer[bytes_needed:]
            self._mic_on_at = time.time() + self.reengage_delay / 1000
        else:
            chunk = bytes(self.audio_buffer) + b"\x00" * (
                bytes_needed - len(self.audio_buffer)
            )
            self.audio_buffer.clear()
        return chunk, pyaudio.paContinue

conversation = Conversation()