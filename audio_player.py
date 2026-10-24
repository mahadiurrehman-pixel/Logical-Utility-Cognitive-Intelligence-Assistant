"""
LUCIA Persistent Audio Player
------------------------------
- Single PyAudio instance across daemon lifetime
- Reuses output stream when audio format matches (kills ALSA reinit gap)
- Thread-safe playback with generation-ID interruption
- Supports seamless concatenated playback

Key Design:
    Old: PyAudio() -> open -> write -> close -> terminate  (per chunk, ~200ms gap)
    New: PyAudio() -> open once -> write -> write -> write  (persistent, ~0ms gap)
"""
import os
import sys
import io
import threading
from pydub import AudioSegment


def _suppress_stderr():
    try:
        null_fd = os.open(os.devnull, os.O_WRONLY)
        stderr_fd = sys.stderr.fileno()
        saved = os.dup(stderr_fd)
        os.dup2(null_fd, stderr_fd)
        os.close(null_fd)
        return saved
    except Exception:
        return None


def _restore_stderr(saved):
    try:
        if saved is not None:
            os.dup2(saved, sys.stderr.fileno())
            os.close(saved)
    except Exception:
        pass


_saved = _suppress_stderr()
import pyaudio
_restore_stderr(_saved)


class PersistentAudioPlayer:
    """
    Reusable audio playback engine.

    Public API:
        play(audio_bytes)         → decode + play (blocks until done)
        play_raw_pcm(pcm, fmt)    → play preformatted PCM (fastest, no decode)
        stop()                    → interrupt current playback
        close()                   → shutdown
    """

    def __init__(self):
        saved = _suppress_stderr()
        self._pa = pyaudio.PyAudio()
        _restore_stderr(saved)

        self._stream = None
        self._stream_format = None   # (width, channels, rate)
        self._stream_lock = threading.Lock()
        self._playback_lock = threading.Lock()
        self._interrupt_flag = threading.Event()
        self._closed = False

    def _ensure_stream(self, width: int, channels: int, rate: int):
        """Open/reuse an output stream matching the requested format."""
        target = (width, channels, rate)
        with self._stream_lock:
            if self._stream is not None and self._stream_format == target:
                return self._stream

            # Format differs → close old, open new
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass

            saved = _suppress_stderr()
            self._stream = self._pa.open(
                format=self._pa.get_format_from_width(width),
                channels=channels,
                rate=rate,
                output=True,
                frames_per_buffer=1024,
            )
            _restore_stderr(saved)
            self._stream_format = target
            return self._stream

    def play(self, audio_bytes: bytes, should_continue=None) -> bool:
        """
        Decode audio_bytes (MP3/WAV) and stream to speakers.

        Args:
            audio_bytes: encoded audio (typically MP3 from Edge-TTS)
            should_continue: optional callable returning False to abort

        Returns:
            True if playback completed, False if interrupted
        """
        if not audio_bytes or self._closed:
            return False

        try:
            sound = AudioSegment.from_file(io.BytesIO(audio_bytes))
            stream = self._ensure_stream(
                sound.sample_width, sound.channels, sound.frame_rate
            )
            raw = sound.raw_data
            chunk_size = 1024
            self._interrupt_flag.clear()

            with self._playback_lock:
                for i in range(0, len(raw), chunk_size):
                    if self._closed or self._interrupt_flag.is_set():
                        return False
                    if should_continue and not should_continue():
                        return False
                    stream.write(raw[i:i + chunk_size])
            return True
        except Exception as e:
            print(f"[PersistentAudioPlayer.play Error] {e}")
            return False

    def play_raw_pcm(self, pcm_data: bytes, width: int, channels: int, rate: int,
                     should_continue=None) -> bool:
        """
        Play pre-decoded PCM bytes (fastest path — no decode step).
        Used for pre-concatenated multi-chunk audio.
        """
        if not pcm_data or self._closed:
            return False

        try:
            stream = self._ensure_stream(width, channels, rate)
            chunk_size = 1024
            self._interrupt_flag.clear()

            with self._playback_lock:
                for i in range(0, len(pcm_data), chunk_size):
                    if self._closed or self._interrupt_flag.is_set():
                        return False
                    if should_continue and not should_continue():
                        return False
                    stream.write(pcm_data[i:i + chunk_size])
            return True
        except Exception as e:
            print(f"[PersistentAudioPlayer.play_raw_pcm Error] {e}")
            return False

    def stop(self):
        """Signal interruption to any active play() call."""
        self._interrupt_flag.set()

    def close(self):
        """Clean shutdown."""
        self._closed = True
        self._interrupt_flag.set()
        with self._stream_lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            try:
                self._pa.terminate()
            except Exception:
                pass


# ============================================================
# GLOBAL SINGLETON
# ============================================================
_player: PersistentAudioPlayer = None
_player_lock = threading.Lock()


def get_player() -> PersistentAudioPlayer:
    global _player
    with _player_lock:
        if _player is None:
            _player = PersistentAudioPlayer()
        return _player


def shutdown_player():
    global _player
    with _player_lock:
        if _player is not None:
            _player.close()
            _player = None