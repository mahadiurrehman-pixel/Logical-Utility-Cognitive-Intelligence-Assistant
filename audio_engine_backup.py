"""
LUCIA Audio Engine
- Native Async Edge-TTS for FastAPI (Ultra-low latency ~200ms)
- Synchronous Wrapper for Desktop Daemon
- Google Speech Recognition for accurate Roman Urdu
"""
import io
import os
import re
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import edge_tts
import speech_recognition as sr
from pydub import AudioSegment
from gtts import gTTS

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

raw_groq_key = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")

# ==========================================
# 1. ACCURATE SPEECH-TO-TEXT (Google STT)
# ==========================================
recognizer = sr.Recognizer()

def transcribe_audio(audio_bytes):
    if not audio_bytes:
        return ""

    # Primary: Google STT (Perfect for Roman Urdu)
    try:
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
        wav_io = io.BytesIO()
        audio_segment.export(wav_io, format="wav")
        wav_io.seek(0)

        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text.strip()
    except Exception as google_err:
        print(f"[Google STT Warning]: {google_err}")

    # Fallback: Groq Whisper
    if raw_groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=raw_groq_key)
            transcription = client.audio.transcriptions.create(
                file=("command.wav", audio_bytes, "audio/wav"),
                model="whisper-large-v3-turbo",
                response_format="text"
            )
            return str(transcription).strip()
        except Exception:
            pass
            
    return ""


# ==========================================
# 2. TEXT CLEANING FOR NATURAL SPEECH
# ==========================================
def clean_text_for_speech(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', 'Maine code screen par generate kar diya hai.', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'http\S+|www\.\S+', '', text)

    # Remove markdown tables & vertical bars
    text = re.sub(r'\|[-:\s|]+\|', ' ', text)
    text = text.replace("|", " ").replace("¦", " ").replace("│", " ")

    # Remove box & graph characters
    ascii_graph_pattern = re.compile(r'[─┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬▲▼►◄█░▓■□▪▫•●★☆✓✔✕✖\\]')
    text = ascii_graph_pattern.sub(' ', text)

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
    text = emoji_pattern.sub(r'', text)
    text = re.sub(r'[:;=8][\-o\*\']?[\)\]\(\[dDpP/\:\}\{@\|\\]', '', text)
    text = re.sub(r'[\*\#\_\~\>\+\(\)\[\]\{\}\^\=\<\>]', ' ', text)

    # Pronunciation tuning
    text = re.sub(r'\bAI\b', 'A.I.', text, flags=re.IGNORECASE)
    text = re.sub(r'\bAPI\b', 'A.P.I.', text, flags=re.IGNORECASE)
    text = re.sub(r'\bUI\b', 'U.I.', text, flags=re.IGNORECASE)
    text = re.sub(r'\bStreamlit\b', 'Stream lit', text, flags=re.IGNORECASE)

    return re.sub(r'\s+', ' ', text).strip()


# ==========================================
# 3. HIGH-SPEED NEURAL VOICE ENGINE
# ==========================================
PRIMARY_VOICE = "en-IN-NeerjaNeural"

async def synthesize_audio_async(text: str) -> bytes:
    """
    ⚡ Native Async Audio Synthesis (Designed for FastAPI web server).
    Generates high quality MP3 in ~200ms!
    """
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return b""

    try:
        communicate = edge_tts.Communicate(
            text=spoken_text,
            voice=PRIMARY_VOICE,
            rate="+10%",  # ⚡ Crisp & snappy speed
            pitch="+0Hz"
        )
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])

        return buffer.getvalue()
    except Exception as e:
        print(f"[Async Edge-TTS Error]: {e}")
        # Fast fallback
        tts = gTTS(text=spoken_text, lang='en', tld='co.in', slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        return buf.getvalue()


def synthesize_google_tts(text: str) -> bytes:
    """
    Synchronous wrapper for Desktop voice daemon.
    """
    spoken_text = clean_text_for_speech(text)
    if not spoken_text:
        return None

    try:
        # Run async function cleanly in sync context
        return asyncio.run(synthesize_audio_async(spoken_text))
    except Exception as e:
        print(f"[Sync TTS Wrapper Error]: {e}")
        try:
            tts = gTTS(text=spoken_text, lang='en', tld='co.in', slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            return buf.getvalue()
        except Exception:
            return None