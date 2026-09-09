"""
LUCIA Desktop Voice Assistant
- Real-Time Sentence Buffering & Multi-threaded Streaming Voice Pipeline
- Parallel TTS Processing with Guaranteed Ordered Playback & Lifecycle Security
- Offline Wake Word (Vosk) + Groq Whisper + Edge-TTS
"""

import os
import sys
import io
import time
import math
import wave
import json
import random
import queue
import threading
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

# Core Imports
from audio_engine import transcribe_audio, synthesize_google_tts, clean_text_for_speech
from tool_router import decide_action, execute_tool
from database import (
    get_all_conversations,
    create_conversation,
    save_message,
    get_recent_messages,
)
from lucia_core import (
    model,
    summary_model,
    build_chat_context,
    update_conversation_summary,
)

# ==========================================
# CONFIGURATION
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
    "System active hai bhai, bolo kya task hai?",
    "Haan yaar bol, kya chal raha hai?",
    "A gayi main! Bolo kya kaam hai?",
    "Ji boss, batao kya dhoondna hai?"
]

# Telemetry Global State
t_start = 0.0

# ==========================================
# SMART SENTENCE BUFFER FOR STREAMING
# ==========================================

class SentenceBuffer:
    """
    Collects tokens from LLM stream and yields complete, natural sentences.
    Handles:
      - Sentence boundary punctuation: . ? ! \n
      - Preserves decimal numbers (3.14) and acronyms (A.I., e.g., vs.)
      - Code block suppression for spoken voice
      - Min-length threshold to avoid micro-fragment stutter
    """
    def __init__(self, min_length: int = 18):
        self.buffer = ""
        self.min_length = min_length
        self.in_code_block = False
        self.code_placeholder_spoken = False
        self.delimiters = [".", "!", "?", "\n", "।"]

    def feed(self, token: str):
        self.buffer += token

        # Track markdown code blocks
        if "```" in self.buffer:
            parts = self.buffer.split("```")
            if len(parts) % 2 == 0:  # Entered a code block
                if not self.in_code_block:
                    self.in_code_block = True
                    if not self.code_placeholder_spoken:
                        self.code_placeholder_spoken = True
                        yield "Maine code screen par generate kar diya hai."
            else:  # Exited code block
                self.in_code_block = False
                self.buffer = parts[-1]

        if self.in_code_block:
            return

        # Parse sentences
        while True:
            first_delim_idx = -1
            first_delim = None
            
            for d in self.delimiters:
                idx = self.buffer.find(d)
                if idx != -1:
                    if first_delim_idx == -1 or idx < first_delim_idx:
                        first_delim_idx = idx
                        first_delim = d
            
            if first_delim_idx == -1:
                break

            sentence_candidate = self.buffer[:first_delim_idx + 1]
            
            # Skip decimal points
            if first_delim == "." and first_delim_idx > 0 and first_delim_idx < len(self.buffer) - 1:
                prev_char = self.buffer[first_delim_idx - 1]
                next_char = self.buffer[first_delim_idx + 1]
                if prev_char.isdigit() and next_char.isdigit():
                    # Temporarily mask the dot
                    self.buffer = self.buffer[:first_delim_idx] + "_" + self.buffer[first_delim_idx + 1:]
                    continue

            # Abbreviation check
            abbrev_match = False
            if first_delim == "." and first_delim_idx > 0:
                if self.buffer[first_delim_idx - 1].isupper():
                    abbrev_match = True
                elif first_delim_idx >= 2 and self.buffer[first_delim_idx - 2:first_delim_idx].lower() in ["eg", "vs", "ie", "dr", "mr", "ms"]:
                    abbrev_match = True
            
            if abbrev_match:
                self.buffer = self.buffer[:first_delim_idx] + "\uFF0E" + self.buffer[first_delim_idx + 1:]
                continue

            sentence = sentence_candidate.strip()
            sentence = sentence.replace("\uFF0E", ".").replace("_", ".")
            self.buffer = self.buffer[first_delim_idx + 1:]

            if len(sentence) >= self.min_length or first_delim in ["\n", "?", "!"]:
                if sentence:
                    yield sentence

    def flush(self):
        if self.in_code_block:
            self.buffer = ""
            return
        remaining = self.buffer.strip()
        self.buffer = ""
        if remaining:
            remaining = remaining.replace("\uFF0E", ".").replace("_", ".")
            yield remaining


# ==========================================
# AUDIO PLAYBACK ENGINE
# ==========================================

def play_audio_bytes(audio_bytes: bytes):
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
            out_stream.write(raw_data[i:i + chunk_size])
        out_stream.stop_stream()
        out_stream.close()
        p.terminate()
        restore_stderr(saved_err)
    except Exception as e:
        print(f"[Playback Error] {e}")


# ==========================================
# CONCURRENT ORDERED VOICE PIPELINE
# ==========================================

def stream_llm_voice_output(token_generator) -> str:
    """
    ⚡ Real-Time Streaming Voice Engine
    - Multi-threaded synthesis to guarantee continuous speech flow.
    - Preserves sentence order via monotonically increasing Sequence IDs.
    - Guaranteed lifecycle: Playback only terminates when ALL sentences have been played.
    """
    global t_start
    text_queue = queue.Queue()
    audio_dict = {}
    audio_lock = threading.Lock()
    audio_available_event = threading.Event()
    
    # Track exactly how many sentences are expected
    playback_completed_event = threading.Event()
    total_sentences_expected = None
    
    first_token_received = False
    full_text_accumulated = []

    # Worker 1: Parallel TTS Synthesizer (Single persistent thread to preserve system resources)
    def tts_worker():
        while True:
            item = text_queue.get()
            if item is None:  # Sentinel
                text_queue.task_done()
                break
                
            seq_id, sentence = item
            
            # Telemetry Log
            if seq_id == 0:
                print(f"\n[LUCIA TTS] Sentence 1 started synthesis: {time.time() - t_start:.2f}s")
                
            try:
                cleaned = clean_text_for_speech(sentence)
                audio_bytes = synthesize_google_tts(cleaned) if cleaned else b""
            except Exception as e:
                print(f"\n[TTS Worker Error] {e}")
                audio_bytes = b""  # Insert blank to prevent playback deadlock
                
            if seq_id == 0:
                print(f"[LUCIA TTS] Sentence 1 synthesis ready: {time.time() - t_start:.2f}s")
                
            with audio_lock:
                audio_dict[seq_id] = audio_bytes
                
            audio_available_event.set()
            text_queue.task_done()

    # Worker 2: Sequential Player
    def playback_worker():
        next_seq_id = 0
        while True:
            # Check if we should exit: we must have processed all expected sentences
            if total_sentences_expected is not None and next_seq_id >= total_sentences_expected:
                break
                
            audio_available_event.wait(timeout=0.1)
            audio_available_event.clear()
            
            while True:
                with audio_lock:
                    if next_seq_id in audio_dict:
                        audio_bytes = audio_dict.pop(next_seq_id)
                    else:
                        break
                
                if next_seq_id == 0:
                    print(f"[LUCIA AUDIO] Sentence 1 playback started: {time.time() - t_start:.2f}s")
                    
                if audio_bytes and len(audio_bytes) > 0:
                    play_audio_bytes(audio_bytes)
                elif audio_bytes == b"":
                    # Log skip for failed TTS to satisfy Error Isolation spec
                    print(f"\n[LUCIA AUDIO] Sentence {next_seq_id} had TTS failure; skipping chunk to prevent deadlock.")
                    
                next_seq_id += 1
                
        playback_completed_event.set()

    # Spawn Threads
    t_tts = threading.Thread(target=tts_worker, daemon=True)
    t_play = threading.Thread(target=playback_worker, daemon=True)
    t_tts.start()
    t_play.start()

    sentence_buf = SentenceBuffer()
    seq_counter = 0

    try:
        for chunk in token_generator:
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            if content:
                if not first_token_received:
                    first_token_received = True
                    print(f"[LUCIA STREAM] First token received: {time.time() - t_start:.2f}s")
                    
                full_text_accumulated.append(content)
                sys.stdout.write(content)
                sys.stdout.flush()

                for sentence in sentence_buf.feed(content):
                    if seq_counter == 0:
                        print(f"\n[LUCIA STREAM] First sentence ready: {time.time() - t_start:.2f}s")
                    text_queue.put((seq_counter, sentence))
                    seq_counter += 1

        for sentence in sentence_buf.flush():
            text_queue.put((seq_counter, sentence))
            seq_counter += 1

    except Exception as e:
        print(f"\n[Stream Processing Error] {e}")

    finally:
        # 1. Inform play worker exactly how many sentences are expected
        total_sentences_expected = seq_counter
        
        # 2. Shutdown TTS worker safely
        text_queue.put(None)
        t_tts.join()
        
        # 3. Trigger final playback check and wait for completion
        audio_available_event.set()
        playback_completed_event.wait()
        t_play.join()
        print()

    return "".join(full_text_accumulated).strip()


# ==========================================
# DESKTOP VOICE UTILITIES
# ==========================================

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
    print("🎙 [Listening...]")
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
    global t_start
    print("\n" + "=" * 60)
    print("🤖 LUCIA DESKTOP BRAIN & REAL-TIME STREAMING VOICE DAEMON")
    print("=" * 60)

    conv_id = get_desktop_conversation_id()
    print(f"📁 Active DB Session ID: #{conv_id}")

    model_path = Path(__file__).resolve().parent / "vosk-model-small-en-us-0.15"
    if not os.path.exists(model_path):
        print(f"❌ Error: {model_path} not found.")
        sys.exit(1)

    print("🔄 Loading Offline Wake Engine ('LUCIA')...")
    vosk_model = VoskModel(str(model_path))
    grammar = '["lucia", "hey lucia", "sun lucia", "ok lucia", "[unk]"]'
    recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE, grammar)

    print("🔊 Pre-caching dynamic wake acknowledgments...")
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

    print("\n⚡ LUCIA is Online • Real-Time Streaming Voice Ready!")
    print("📢 Wake words: 'LUCIA' or 'Hey Lucia'")
    print("─" * 60)
    print("🟢 Waiting for Wake Word... (Press Ctrl+C to stop)\n")

    try:
        while True:
            raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)

            if recognizer.AcceptWaveform(raw_data):
                res = json.loads(recognizer.Result())
                detected_text = res.get("text", "").lower()

                if "lucia" in detected_text:
                    print(f"\n🔥 WAKE DETECTED! ('{detected_text}')")

                    # Instant acknowledgment
                    selected_phrase, selected_audio = random.choice(cached_acks)
                    print(f"🗣️ LUCIA: '{selected_phrase}'")
                    play_audio_bytes(selected_audio)

                    # Record speech
                    wav_bytes = record_command(stream)

                    # Reset timer for logging metrics
                    t_start = time.time()

                    # Transcribe
                    user_text = transcribe_audio(wav_bytes)
                    print(f"[LUCIA STT] Transcription ready: {time.time() - t_start:.2f}s")

                    if not user_text or user_text.startswith("⚠️"):
                        print("⚠️ No command heard.")
                        play_audio_bytes(synthesize_google_tts("Aawaz samajh nahi aayi bhai."))
                        print("\n🟢 Waiting for 'LUCIA'...\n" + "─" * 60)
                        recognizer.Reset()
                        continue

                    print(f"👤 USER: \"{user_text}\"")

                    if is_stop_command(user_text):
                        print("🤫 Stop command received.")
                        play_audio_bytes(chup_audio)
                        recognizer.Reset()
                        print("\n🟢 Waiting for 'LUCIA'...\n" + "─" * 60)
                        continue

                    save_message(conv_id, "user", user_text)

                    # Tool decision
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

                    # Real-time streaming voice output
                    if not action_done:
                        print("🤖 LUCIA (Live Voice Stream): ", end="", flush=True)

                        recent = get_recent_messages(conv_id, limit=6)
                        recent_msgs = []
                        for r, c in recent:
                            if r == "user":
                                recent_msgs.append(HumanMessage(content=c))
                            elif r == "assistant":
                                recent_msgs.append(AIMessage(content=c))

                        context = build_chat_context(conv_id, recent_msgs, tool_result=tool_result, decision=decision)

                        # Stream tokens and overlap TTS synthesis & audio playback in real-time
                        token_stream = model.stream(context)
                        reply_text = stream_llm_voice_output(token_stream)

                        save_message(conv_id, "assistant", reply_text)
                        update_conversation_summary(conv_id)

                    recognizer.Reset()
                    print("\n🟢 Back to Listening for 'LUCIA'...\n" + "─" * 60)

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