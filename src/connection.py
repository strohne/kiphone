#
# Connect to LLM
#

import base64
import json
import socket
import ssl
import threading
import time
import websocket
import socks
import wave

from config.config import API_KEY, API_URL
from config.callers import persons

# Force all sockets through the SOCKS proxy
socket.socket = socks.socksocket

class Connection:
    """
    Manages a real-time WebSocket connection to the OpenAI Realtime API.

    Handles session configuration, bidirectional audio streaming (microphone
    send / speaker receive), optional greeting injection, and speaker
    identification from transcripts.
    """

    def __init__(
        self,
        mic_queue,
        audio_buffer,
        stop_event,
        ready_event,
        role,
        persons,
        greeting=None,
    ):
        """
        :param mic_queue: Queue supplying raw PCM16 microphone chunks.
        :param audio_buffer: Bytearray that receives decoded AI audio chunks.
        :param stop_event: threading.Event that signals the connection to shut down.
        :param ready_event: threading.Event that signals that the connection is ready.
        :param role: Mutable list [dict] holding the active role configuration.
        :param persons: Mutable list [dict|None] holding the detected caller.
        :param greeting: Path to a PCM16 WAV file to inject as the opening utterance, or None.
        """
        self.mic_queue = mic_queue
        self.audio_buffer = audio_buffer
        self.stop_event = stop_event
        self.ready_event = ready_event
        self.role = role
        self.persons = persons
        self.greeting = greeting
        self._ws = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Open the WebSocket, start send/receive threads, and block until
        stop_event is set or an error occurs.
        """
        try:
            self._ws = self._create_connection()
            print("Connection: Connected to OpenAI WebSocket")

            recv_thread = threading.Thread(target=self._receive_loop)
            send_thread = threading.Thread(target=self._send_loop)
            recv_thread.start()
            send_thread.start()

            self._send_session_update()

            if self.greeting:
                print(f"Connection: Injecting {self.greeting}")
                self._inject_audio(self.greeting)

            while not self.stop_event.is_set():
                time.sleep(0.1)

            try:
                self._ws.send_close()
            except Exception:
                pass

            recv_thread.join()
            send_thread.join()
            print("Connection: Closed.")

        except Exception as e:
            print(f"Connection: Failed: {e}")
        finally:
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_connection():
        """Open a WebSocket connection forced over IPv4."""
        original_getaddrinfo = socket.getaddrinfo

        def _ipv4_only(host, port, family=socket.AF_INET, *args):
            return original_getaddrinfo(host, port, socket.AF_INET, *args)

        socket.getaddrinfo = _ipv4_only
        try:
            return websocket.create_connection(
                API_URL,
                header=[
                    f"Authorization: Bearer {API_KEY}",
                    "OpenAI-Beta: realtime=v1",
                ],
                sslopt={"cert_reqs": ssl.CERT_NONE},
            )
        finally:
            socket.getaddrinfo = original_getaddrinfo

    def _send_loop(self) -> None:
        """Send microphone chunks from the queue to the WebSocket."""
        try:
            while not self.stop_event.is_set():
                if not self.mic_queue.empty():
                    chunk = self.mic_queue.get()
                    encoded = base64.b64encode(chunk).decode("utf-8")
                    msg = json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": encoded,
                    })
                    try:
                        self._ws.send(msg)
                    except Exception as e:
                        print(f"Audio: Microhpone send error: {e}")
        except Exception as e:
            print(f"Audio: Send thread error: {e}")
        finally:
            print("Audio: Send thread finished.")

    def _receive_loop(self) -> None:
        """Receive audio deltas and events from the WebSocket."""
        try:
            while not self.stop_event.is_set():
                message = self._ws.recv()
                if not message:
                    continue
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    print("Receive: Invalid JSON data.")
                    continue
                self._handle_event(data)
        except Exception as e:
            print(f"Receive: Thread error: {e}")
        finally:
            print("Receive: Thread finished.")

    def _handle_event(self, data: dict) -> None:
        """Dispatch a single WebSocket event to the appropriate handler."""
        event_type = data.get("type", "")

        if event_type == "session.created":
            self._send_session_update()

        # AI is answering
        elif event_type == "response.audio.delta":
            self.ready_event.set()
            self.audio_buffer.extend(base64.b64decode(data["delta"]))

        # Caller started speaking
        elif event_type == "input_audio_buffer.speech_started":
            self.audio_buffer.clear()

        # Transcription of caller speech
        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = data.get("transcript")

            if not transcript:
                for part in data.get("item", {}).get("content", []):
                    if isinstance(part, dict) and part.get("transcript"):
                        transcript = part["transcript"]
                        break

            if transcript:
                print(f"*You*: {transcript}")
                self._process_transcript(transcript)

        elif event_type == "conversation.item.input_audio_transcription.failed":
            print(f"Converation: User transcription failed: {data.get('error', {})}")

        # Transcription of AI speech
        elif event_type == "response.audio_transcript.done":
            print(f"*AI*: {data.get('transcript', '')}")

    def _send_session_update(self) -> None:
        """Push the current session configuration (instructions, voice, VAD …) to the API."""
        caller = self.persons[0]
        role = self.role[0]
        extra = ""
        if caller:
            extra = (
                f"Der Gesprächspartner heißt {caller['name']}. "
                f"Er/Sie ist {caller['alter']} Jahre alt, arbeitet als {caller['beruf']} "
                f"und hat als Hobby {caller['hobby']}. "
            )

        session_config = {
            "type": "session.update",
            "session": {
                "instructions": f"{extra}Du bist {role['gpt_style']}",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "voice": role["voice_id"],
                "temperature": 1,
                "max_response_output_tokens": 4096,
                "modalities": ["text", "audio"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
            },
        }
        try:
            self._ws.send(json.dumps(session_config))
            print("Connection: Session update sent.")
        except Exception as e:
            print(f"Connection: Session update failed: {e}")

    def _inject_audio(self, wav_path: str) -> None:
        """
        Stream a WAV file as input audio to prime the AI's first response.

        :param wav_path: Path to a mono PCM16 WAV file at 24 000 Hz.
        :raises ValueError: If the WAV file does not meet the required format.
        """
        try:
            with wave.open(wav_path, "rb") as wf:
                if wf.getsampwidth() != 2:
                    raise ValueError("Audio file must be PCM16 (16-bit).")
                if wf.getframerate() != 24000:
                    raise ValueError("Audio file must be 24 000 Hz.")
                if wf.getnchannels() != 1:
                    raise ValueError("Audio file must be mono.")
                if wf.getcomptype() != "NONE":
                    raise ValueError("Audio file must be uncompressed.")

                chunk_duration = 0.1
                frames_per_chunk = int(24000 * chunk_duration)
                while True:
                    data = wf.readframes(frames_per_chunk)
                    if not data:
                        break
                    self._ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(data).decode("utf-8"),
                    }))
                    time.sleep(chunk_duration)

            self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            self._ws.send(json.dumps({"type": "response.create"}))
            print("Audio: Injected file.")
        except Exception as e:
            print(f"Audio: Could not inject audio: {e}")

    def _process_transcript(self, transcript: str) -> None:
        """
        Detect a known caller name in *transcript* and update persons.

        :param transcript: The transcribed user utterance.
        """
        if self.persons[0]:
            return

        for name, info in persons.items():
            if name.lower() in transcript.lower():
                self.persons[0] = {"name": name, **info}
                print(f"Conversation: Caller {self.persons[0]} identified.")
                self._send_session_update()
                break
