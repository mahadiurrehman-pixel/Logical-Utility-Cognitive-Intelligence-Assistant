"""
LUCIA Audio Engine (Optimized)
------------------
STT:
    1. Groq Whisper (PRIMARY)
    2. faster-whisper local (FALLBACK)

TTS:
    1. Edge-TTS (PRIMARY, persistent asyncio loop)
    2. Google gTTS (FALLBACK)

Bounded LRU TTS cache for short deterministic phrases.
Automatic silence trimming to eliminate inter-chunk gaps.
Maintains existing public interfaces.
"""

import io
import os
import re
import asyncio
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydub import AudioSegment
from pydub.silence import detect_leading_silence
import edge_tts
from gtts import gTTS

# ============================================================
# ENVIRONMENT
# ============================================================
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

GROQ_API_KEY = (
    os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
)


# ============================================================
# PERSISTENT ASYNCIO LOOP FOR TTS
# ============================================================
_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def _get_persistent_loop():
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is None or not _loop.is_running():
            _loop = asyncio.new_event_loop()
            def _run_loop():
                asyncio.set_event_loop(_loop)
                _loop.run_forever()
            _loop_thread = threading.Thread(target=_run_loop, daemon=True, name="LuciaTTSLoop")
            _loop_thread.start()
    return _loop


def shutdown_tts_loop():
    global _loop
    with _loop_lock:
        if _loop and _loop.is_running():
            _loop.call_soon_threadsafe(_loop.stop)


# ============================================================
# LOCAL FASTER-WHISPER
# ============================================================
_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            print("[LUCIA STT] Loading local faster-whisper model...")
            _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            print("[LUCIA STT] Local faster-whisper model loaded.")
        except Exception as e:
            print(f"[LUCIA STT] Local Whisper unavailable: {e}")
            return None
    return _whisper_model


def convert_to_wav(audio_bytes: bytes) -> bytes:
    if not audio_bytes:
        return b""
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        audio = audio.set_channels(1).set_frame_rate(16000)
        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        return wav_buffer.read()
    except Exception as e:
        print(f"[Audio Conversion Error] {e}")
        return audio_bytes


# ============================================================
# STT
# ============================================================
def transcribe_groq(audio_bytes: bytes) -> str:
    if not GROQ_API_KEY or not audio_bytes:
        return ""
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        wav_bytes = convert_to_wav(audio_bytes)
        transcription = client.audio.transcriptions.create(
            file=("command.wav", wav_bytes, "audio/wav"),
            model="whisper-large-v3-turbo",
            response_format="text"
        )
        return str(transcription).strip()
    except Exception as e:
        print(f"[Groq STT Error, switching to local fallback] {e}")
        return ""


def transcribe_local(audio_bytes: bytes) -> str:
    model = get_whisper_model()
    if model is None or not audio_bytes:
        return ""
    wav_bytes = convert_to_wav(audio_bytes)
    if not wav_bytes:
        return ""
    temp_path = None
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            temp_path = f.name
        segments, _ = model.transcribe(
            temp_path, language=None, beam_size=5,
            vad_filter=True, condition_on_previous_text=False
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as e:
        print(f"[Local STT Error] {e}")
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def transcribe_audio(audio_bytes: bytes) -> str:
    if not audio_bytes:
        return ""
    text = transcribe_groq(audio_bytes)
    if text:
        return text
    text = transcribe_local(audio_bytes)
    if text:
        return text
    return ""


# ============================================================
# TEXT CLEANING
# ============================================================
def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"```.*?```", " Maine code screen par generate kar diya hai. ", text, flags=re.DOTALL)
    text = re.sub(r"`.*?`", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\|.*?\|", "", text)
    text = text.replace("|", " ").replace("¦", " ").replace("│", " ")
    text = re.sub(r'[─┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬▲▼►◄█░▓■□▪▫•●★☆✓✔✕✖\\]', ' ', text)

    emoji_pattern = re.compile(
        "["
        "\U00010000-\U0010ffff"
        "\u2600-\u27BF"
        "\uE000-\uF8FF"
        "\u2011-\u26FF"
        "\u2B50"
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)
    text = re.sub(r'[:;=8][\-o\*\']?[\)\]\(\[dDpP/\:\}\{@\|\\]', '', text)

    text = re.sub(r"\bAI\b", "A.I.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAPI\b", "A.P.I.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUI\b", "U.I.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bStreamlit\b", "Stream lit", text, flags=re.IGNORECASE)

    text = re.sub(r"[*_#>`~]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ============================================================
# TTS
# ============================================================
PRIMARY_VOICE = "en-IN-NeerjaNeural"
TTS_RATE = "+25%"
TTS_PITCH = "+0Hz"

_TTS_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
MAX_CACHE_SIZE = 40
CACHE_MAX_TEXT_LEN = 40


def _cache_key(text: str) -> str:
    return f"{PRIMARY_VOICE}|{TTS_RATE}|{TTS_PITCH}|{text}"


def _cache_get(text: str) -> Optional[bytes]:
    if len(text) > CACHE_MAX_TEXT_LEN:
        return None
    key = _cache_key(text)
    with _CACHE_LOCK:
        if key in _TTS_CACHE:
            _TTS_CACHE.move_to_end(key)
            return _TTS_CACHE[key]
    return None


def _cache_put(text: str, audio: bytes):
    if not audio or len(text) > CACHE_MAX_TEXT_LEN:
        return
    key = _cache_key(text)
    with _CACHE_LOCK:
        _TTS_CACHE[key] = audio
        _TTS_CACHE.move_to_end(key)
        while len(_TTS_CACHE) > MAX_CACHE_SIZE:
            _TTS_CACHE.popitem(last=False)


async def synthesize_audio_async(text: str) -> bytes:
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return b""
    try:
        communicate = edge_tts.Communicate(
            text=spoken_text,
            voice=PRIMARY_VOICE,
            rate=TTS_RATE,
            pitch=TTS_PITCH
        )
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        return buffer.getvalue()
    except Exception as e:
        print(f"[Edge TTS Warning: {e}]")
        return b""


def synthesize_gtts(text: str) -> bytes:
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return b""
    try:
        tts = gTTS(text=spoken_text, lang="en", tld="co.in", slow=False)
        buffer = io.BytesIO()
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        print(f"[gTTS Fallback Error: {e}]")
        return b""


def synthesize_google_tts(text: str) -> Optional[bytes]:
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return None

    cached = _cache_get(spoken_text)
    if cached:
        return cached

    try:
        loop = _get_persistent_loop()
        future = asyncio.run_coroutine_threadsafe(
            synthesize_audio_async(spoken_text), loop
        )
        audio = future.result(timeout=8.0)
        if audio:
            _cache_put(spoken_text, audio)
            return audio
    except Exception as e:
        print(f"[Edge-TTS dispatch error: {e}]")

    audio = synthesize_gtts(spoken_text)
    if audio:
        _cache_put(spoken_text, audio)
    return audio if audio else None


# ============================================================
# 🆕 SILENCE TRIMMING & DECODE HELPERS (For Gapless Playback)
# ============================================================
LEADING_SILENCE_THRESHOLD_DB = -40.0  # dBFS
TRAILING_SILENCE_MS_TO_KEEP = 60      # keep ~60ms natural pause


def decode_and_trim(audio_bytes: bytes) -> Optional[AudioSegment]:
    """
    Decode MP3/WAV bytes → AudioSegment with leading/trailing silence trimmed.
    Keeps a small natural pause (~60ms) so sentences don't run together jarringly.

    Returns None on decode failure.
    """
    if not audio_bytes:
        return None
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))

        # Trim leading silence completely
        leading = detect_leading_silence(
            seg, silence_threshold=LEADING_SILENCE_THRESHOLD_DB
        )
        if leading > 0 and leading < len(seg):
            seg = seg[leading:]

        # Trim trailing silence but keep small natural pause
        trailing = detect_leading_silence(
            seg.reverse(), silence_threshold=LEADING_SILENCE_THRESHOLD_DB
        )
        excess_trailing = trailing - TRAILING_SILENCE_MS_TO_KEEP
        if excess_trailing > 0 and excess_trailing < len(seg):
            seg = seg[:len(seg) - excess_trailing]

        return seg
    except Exception as e:
        print(f"[decode_and_trim Error] {e}")
        return None