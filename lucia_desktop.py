"""
LUCIA Desktop Voice Assistant (Zero-Lag & Instant Speech Generation)
- Reverted to 100% Accurate Google STT for Roman Urdu
- Generates speech instantly for the whole response (Removes streaming gaps)
- Groq Llama 3.3 70B
"""
import os
import sys
import io
import time
import math
import wave
import json
import random
from pathlib import Path
import numpy as np
from dotenv import load_dotenv

def suppress_stderr():
    try:
        null_fd = os.open(os.devnull, os.O_WRONLY)
        stderr_fd = sys.stderr.fileno()
        saved_stderr = os.dup(stderr_fd)
        os.dup2(null_fd, stderr_fd)
        os.close(null_fd)
        return saved_stderr
    except Exception:
        return None

def restore_stderr(saved_stderr):
    try:
        if saved_stderr is not None:
            stderr_fd = sys.stderr.fileno()
            os.dup2(saved_stderr, stderr_fd)
            os.close(saved_stderr)
    except Exception:
        pass

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

saved_err = suppress_stderr()
import pyaudio
from pydub import AudioSegment
from vosk import Model as VoskModel, KaldiRecognizer
restore_stderr(saved_err)

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# Project Modules
from audio_engine import transcribe_audio, synthesize_google_tts
from tool_router import decide_action, execute_tool
from database import (
    get_all_conversations,
    create_conversation,
    save_message,
    get_recent_messages,
)

# Core Brain Import
from lucia_core import (
    model,
    summary_model,
    build_chat_context,
    update_conversation_summary,
    execute_llm_with_retry
)

# ==========================================
# CONFIGURATION CONSTANTS
# ==========================================
CHUNK_SIZE = 2048
SAMPLE_RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16

SILENCE_THRESHOLD = 320
SILENCE_DURATION = 0.6
MAX_RECORD_SECONDS = 6.0

STOP_WORDS = ["chup", "stop", "khamosh", "bas", "band", "quiet", "chup ho jao", "band ho jao", "sleep"]

WAKE_PHRASES = [
    "Haan bhai, bolo kya scene hai?",
    "Ji janab, hukum karein!",
    "Bolo boss, kya help chahiye?",
    "Ji bhai, sun rahi hoon, batayein!",
    "System active hai bhai, bolo kya kholna hai?",
    "Haan yaar bol, kya scene chal raha hai?",
    "A gayi main! Bolo kya task hai?",
    "Ji boss, batao kya dhoondna hai?"
]

# ==========================================
# AUDIO PLAYBACK ENGINE
# ==========================================
def play_audio_bytes(audio_bytes):
    if not audio_bytes:
        return
    try:
        saved_err = suppress_stderr()
        sound = AudioSegment.from_file(io.BytesIO(audio_bytes))
        p = pyaudio.PyAudio()
        out_stream = p.open(
            format=p.get_format_from_width(sound.sample_width),
            channels=sound.channels,
            rate=sound.frame_rate,
            output=True
        )
        chunk_size = 1024
        raw_data = sound.raw_data
        for i in range(0, len(raw_data), chunk_size):
            out_stream.write(raw_data[i:i+chunk_size])
        
        out_stream.stop_stream()
        out_stream.close()
        p.terminate()
        restore_stderr(saved_err)
    except Exception as e:
        print(f"[Playback Error]: {e}")


def get_desktop_conversation_id():
    conversations = get_all_conversations()
    for conv_id, title, _ in conversations:
        if "Desktop Voice" in title:
            return conv_id
    return create_conversation(title="🎙️ Desktop Voice Session")


def is_stop_command(text: str) -> bool:
    clean = text.lower().strip()
    return any(w in clean for w in STOP_WORDS)


def record_command(stream):
    print("🎙️ [Listening...]")
    frames = []
    silent_chunks = 0
    speech_detected = False
    start_time = time.time()
    chunks_for_silence = int(SILENCE_DURATION / (CHUNK_SIZE / SAMPLE_RATE))
    
    while True:
        raw_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        frames.append(raw_chunk)
        
        audio_chunk = np.frombuffer(raw_chunk, dtype=np.int16)
        sum_sq = np.sum(audio_chunk.astype(np.float64) ** 2)
        rms = math.sqrt(sum_sq / len(audio_chunk)) if len(audio_chunk) > 0 else 0
        
        if rms > SILENCE_THRESHOLD:
            speech_detected = True
            silent_chunks = 0
        else:
            if speech_detected:
                silent_chunks += 1
        
        if speech_detected and silent_chunks >= chunks_for_silence:
            break
        if (time.time() - start_time) >= MAX_RECORD_SECONDS:
            break
    
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b''.join(frames))
    
    return wav_buffer.getvalue()


# ==========================================
# MAIN DAEMON LOOP
# ==========================================
def main():
    print("\n" + "="*55)
    print("🤖 LUCIA DESKTOP BRAIN & VOICE DAEMON (ZERO-LAG)")
    print("="*55)
    
    conv_id = get_desktop_conversation_id()
    print(f"📁 Active DB Session ID: #{conv_id}")
    
    model_path = Path(__file__).resolve().parent / "vosk-model-small-en-us-0.15"
    if not os.path.exists(model_path):
        print(f"❌ Error: {model_path} nahi mila.")
        sys.exit(1)
        
    print("🔄 Loading Custom 'LUCIA' Wake Engine...")
    vosk_model = VoskModel(str(model_path))
    grammar = '["lucia", "hey lucia", "sun lucia", "ok lucia", "[unk]"]'
    recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE, grammar)
    
    print("🔊 Pre-caching dynamic acknowledgment voices...")
    cached_acks = []
    for phrase in WAKE_PHRASES:
        audio_bytes = synthesize_google_tts(phrase)
        if audio_bytes:
            cached_acks.append((phrase, audio_bytes))
            
    if not cached_acks:
        cached_acks = [("Haan bhai?", synthesize_google_tts("Haan bhai?"))]
        
    chup_audio = synthesize_google_tts("Theek hai bhai, main chup hoon.")
    
    saved_err = suppress_stderr()
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )
    restore_stderr(saved_err)
    
    print("\n⚡ LUCIA is Online • Natural Voice Ready!")
    print("📢 Wake words: 'LUCIA' or 'Hey Lucia'")
    print("─"*55)
    print("🟢 Waiting for Wake Word... (Press Ctrl+C to stop)\n")
    
    try:
        while True:
            raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            
            if recognizer.AcceptWaveform(raw_data):
                res = json.loads(recognizer.Result())
                detected_text = res.get("text", "").lower()
                
                if "lucia" in detected_text:
                    print(f"\n🔥 WAKE DETECTED! ('{detected_text}')")
                    
                    selected_phrase, selected_audio = random.choice(cached_acks)
                    print(f"🗣️ LUCIA: '{selected_phrase}'")
                    play_audio_bytes(selected_audio)
                    
                    wav_bytes = record_command(stream)
                    
                    user_text = transcribe_audio(wav_bytes)
                    
                    if not user_text or user_text.startswith("⚠️"):
                        print("⚠️ No command heard.")
                        play_audio_bytes(synthesize_google_tts("Aawaz samajh nahi aayi bhai."))
                        print("\n🟢 Waiting for 'LUCIA'...\n" + "─"*55)
                        recognizer.Reset()
                        continue
                    
                    print(f"👤 USER: \"{user_text}\"")
                    
                    if is_stop_command(user_text):
                        print("🤫 Stop command received.")
                        play_audio_bytes(chup_audio)
                        recognizer.Reset()
                        print("\n🟢 Waiting for 'LUCIA'...\n" + "─"*55)
                        continue
                    
                    save_message(conv_id, "user", user_text)
                    
                    decision = decide_action(user_text, summary_model)
                    tool_result = None
                    action_done = False
                    
                    if decision.get("action") in ["tool", "tool_sequence"] or "tools" in decision:
                        print(f"⚙️ Executing Tool: {decision.get('tool')}")
                        tool_result = execute_tool(decision)
                        
                        tool_name = decision.get("tool")
                        if tool_name != "web_search":
                            reply_text = tool_result.get("message", "Done bhai, kaam kar diya!")
                            print(f"🤖 LUCIA: \"{reply_text}\"")
                            save_message(conv_id, "assistant", reply_text)
                            play_audio_bytes(synthesize_google_tts(reply_text))
                            action_done = True
                    
                    if not action_done:
                        print("🧠 LUCIA is thinking...")
                        
                        recent = get_recent_messages(conv_id, limit=6)
                        recent_msgs = []
                        for r, c in recent:
                            if r == "user":
                                recent_msgs.append(HumanMessage(content=c))
                            elif r == "assistant":
                                recent_msgs.append(AIMessage(content=c))
                        
                        context = build_chat_context(conv_id, recent_msgs, tool_result=tool_result, decision=decision)
                        
                        try:
                            # ⚡ Snappy execution with Llama 3.3's instant generation (<0.3s)
                            response = execute_llm_with_retry(model.invoke, context)
                            reply_text = response.content.strip()
                            
                            print(f"🤖 LUCIA: \"{reply_text}\"")
                            save_message(conv_id, "assistant", reply_text)
                            update_conversation_summary(conv_id)
                            
                            # Synthesize and play at once
                            tts_bytes = synthesize_google_tts(reply_text)
                            play_audio_bytes(tts_bytes)
                        except Exception as err:
                            print(f"[Groq Error]: {err}")
                            play_audio_bytes(synthesize_google_tts("Server par load hai bhai, dobara bolein."))
                    
                    recognizer.Reset()
                    print("\n🟢 Back to Listening for 'LUCIA'...\n" + "─"*55)

    except KeyboardInterrupt:
        print("\n👋 Desktop Daemon stopped.")
    finally:
        saved_err = suppress_stderr()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        restore_stderr(saved_err)

if __name__ == "__main__":
    main()