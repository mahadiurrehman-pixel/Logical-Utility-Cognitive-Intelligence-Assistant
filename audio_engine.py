"""
LUCIA Audio Engine
------------------
STT:
    1. Groq Whisper (PRIMARY)
    2. faster-whisper local (FALLBACK)

TTS:
    1. Edge-TTS (PRIMARY)
    2. Google gTTS (FALLBACK)

Maintains existing interfaces and clean text preprocessing.
"""

import io
import os
import re
import asyncio
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydub import AudioSegment
import edge_tts
from gtts import gTTS

# ============================================================
# ENVIRONMENT
# ============================================================

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

GROQ_API_KEY = (
    os.getenv("GROQ_API_KEY", "")
    .strip()
    .strip('"')
    .strip("'")
)

# ============================================================
# LOCAL FASTER-WHISPER (Lazy Load)
# ============================================================

_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            print("[LUCIA STT] Loading local faster-whisper model...")
            _whisper_model = WhisperModel(
                "small",
                device="cpu",
                compute_type="int8"
            )
            print("[LUCIA STT] Local faster-whisper model loaded.")
        except Exception as e:
            print(f"[LUCIA STT] Local Whisper unavailable: {e}")
            return None
    return _whisper_model


# ============================================================
# AUDIO CONVERSION
# ============================================================

def convert_to_wav(audio_bytes: bytes) -> bytes:
    if not audio_bytes:
        return b""
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        audio = audio.set_channels(1)
        audio = audio.set_frame_rate(16000)

        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        return wav_buffer.read()
    except Exception as e:
        print(f"[Audio Conversion Error] {e}")
        return audio_bytes


# ============================================================
# STT PIPELINE (Groq Primary -> Local Fallback)
# ============================================================

def transcribe_groq(audio_bytes: bytes) -> str:
    """Primary STT: Groq Whisper Turbo"""
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
    """Fallback STT: faster-whisper local"""
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
            temp_path,
            language=None,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False
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
    """
    Main STT Entry Point.
    Priority:
        1. Groq Whisper (fastest)
        2. faster-whisper (local offline fallback)
    """
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
# TEXT CLEANING FOR TTS
# ============================================================

def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""

    # Remove code blocks
    text = re.sub(r"```.*?```", " Maine code screen par generate kar diya hai. ", text, flags=re.DOTALL)
    text = re.sub(r"`.*?`", "", text)

    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)

    # Remove markdown tables and pipes
    text = re.sub(r"\|.*?\|", "", text)
    text = text.replace("|", " ").replace("¦", " ").replace("│", " ")

    # Remove ASCII boxes & symbols
    text = re.sub(r'[─┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬▲▼►◄█░▓■□▪▫•●★☆✓✔✕✖\\]', ' ', text)

    # Remove emojis
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

    # Pronunciation Tuning
    text = re.sub(r"\bAI\b", "A.I.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAPI\b", "A.P.I.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUI\b", "U.I.", text, flags=re.IGNORECASE)
    text = re.sub(r"\bStreamlit\b", "Stream lit", text, flags=re.IGNORECASE)

    # Clean markdown characters
    text = re.sub(r"[*_#>`~]", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# TTS PIPELINE (Edge-TTS Primary -> gTTS Fallback)
# ============================================================

PRIMARY_VOICE = "en-IN-NeerjaNeural"


async def synthesize_audio_async(text: str) -> bytes:
    """Primary TTS: Microsoft Edge Neural TTS"""
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return b""

    try:
        communicate = edge_tts.Communicate(
            text=spoken_text,
            voice=PRIMARY_VOICE,
            rate="+5%",
            pitch="+0Hz"
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
    """Fallback TTS: Google gTTS"""
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
    """
    Main TTS Entry Point.
    Tries Edge-TTS first; on failure, falls back to gTTS.
    """
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return None

    # 1. Edge-TTS Primary
    try:
        audio = asyncio.run(synthesize_audio_async(spoken_text))
        if audio:
            return audio
    except Exception as e:
        print(f"[Edge-TTS run error: {e}]")

    # 2. gTTS Fallback
    audio = synthesize_gtts(spoken_text)
    return audio if audio else None