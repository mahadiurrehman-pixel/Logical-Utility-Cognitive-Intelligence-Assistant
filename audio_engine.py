"""
LUCIA Audio Engine
- Groq Whisper Turbo STT (~150ms)
- Microsoft Neural TTS with Zero Symbol/Table/Pipe Noise
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
# 1. SPEECH-TO-TEXT
# ==========================================
recognizer = sr.Recognizer()

def transcribe_audio(audio_bytes):
    if not audio_bytes:
        return ""

    if raw_groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=raw_groq_key)
            transcription = client.audio.transcriptions.create(
                file=("command.wav", audio_bytes, "audio/wav"),
                model="whisper-large-v3-turbo",
                response_format="text"
            )
            text = str(transcription).strip()
            if text:
                return text
        except Exception as e:
            print(f"[Groq Whisper Fallback]: {e}")

    try:
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
        wav_io = io.BytesIO()
        audio_segment.export(wav_io, format="wav")
        wav_io.seek(0)

        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text.strip()
    except Exception as e:
        print(f"[STT Error]: {e}")
        return ""


# ==========================================
# 2. ADVANCED SPEECH SANITIZER (No "Vertical Bar" / Graph Noise)
# ==========================================
def clean_text_for_speech(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1. Code blocks replace karein
    text = re.sub(r'```[\s\S]*?```', 'Maine code screen par generate kar diya hai.', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'http\S+|www\.\S+', '', text)

    # 2. Remove Markdown Table Separators (e.g. |---|---| or |:---:|)
    text = re.sub(r'\|[-:\s|]+\|', ' ', text)

    # 3. 🔥 ALL PIPE & VERTICAL BAR CHARACTERS REMOVE
    # Is se TTS kabhi bhi "vertical bar" nahi bolega!
    text = text.replace("|", " ").replace("¦", " ").replace("│", " ")

    # 4. Remove Box Drawing, Graphs & ASCII art symbols
    ascii_graph_pattern = re.compile(r'[─┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬▲▼►◄█░▓■□▪▫•●★☆✓✔✕✖\\]')
    text = ascii_graph_pattern.sub(' ', text)

    # 5. Remove Emojis
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

    # 6. Clean Markdown symbols (*, #, _, ~, >, +, -, bullet points)
    text = re.sub(r'[\*\#\_\~\>\+\(\)\[\]\{\}\^\=\<\>]', ' ', text)

    # 7. Pronunciation tuning
    text = re.sub(r'\bAI\b', 'A.I.', text, flags=re.IGNORECASE)
    text = re.sub(r'\bAPI\b', 'A.P.I.', text, flags=re.IGNORECASE)
    text = re.sub(r'\bUI\b', 'U.I.', text, flags=re.IGNORECASE)
    text = re.sub(r'\bStreamlit\b', 'Stream lit', text, flags=re.IGNORECASE)

    # 8. Extra spaces normalize karein
    return re.sub(r'\s+', ' ', text).strip()


# ==========================================
# 3. NATURAL FEMALE NEURAL VOICE
# ==========================================
PRIMARY_VOICE = "en-IN-NeerjaNeural"

async def _fetch_edge_audio(text):
    communicate = edge_tts.Communicate(
        text=text,
        voice=PRIMARY_VOICE,
        rate="+5%",
        pitch="+0Hz"
    )
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])

    data = buffer.getvalue()
    if not data:
        raise ValueError("Empty audio received from Edge TTS")
    return data


def synthesize_google_tts(text):
    try:
        spoken_text = clean_text_for_speech(text)
        if not spoken_text:
            return None

        # 1. Edge TTS
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                audio_bytes = loop.run_until_complete(_fetch_edge_audio(spoken_text))
                return audio_bytes
            finally:
                loop.close()
        except Exception:
            pass

        # 2. Fallback
        tts = gTTS(text=spoken_text, lang='en', tld='co.in', slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return audio_buffer.getvalue()

    except Exception as e:
        print(f"[TTS Failed]: {e}")
        return None