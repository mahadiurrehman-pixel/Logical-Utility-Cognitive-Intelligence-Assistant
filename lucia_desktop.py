"""
LUCIA Desktop Voice Assistant
- Real-Time Sentence Buffering & Multi-threaded Streaming Voice Pipeline
- Persistent AudioPlayer (no PyAudio reinit → zero inter-chunk gaps)
- Automatic silence trimming (Edge-TTS trailing pause removed)
- Parallel TTS with strict ordered playback
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
import atexit
import re
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
from vosk import Model as VoskModel, KaldiRecognizer
restore_stderr(saved_err)

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from audio_engine import (
    transcribe_audio,
    synthesize_google_tts,
    clean_text_for_speech,
    decode_and_trim,
    shutdown_tts_loop,
)
from audio_player import get_player, shutdown_player
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

STOP_WORDS = ["chup", "stop", "khamosh", "bas", "band", "quiet",
              "chup ho jao", "band ho jao", "sleep"]

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

t_start = 0.0

# ==========================================
# SMART SENTENCE CONSOLIDATION BUFFER
# ==========================================

class SentenceBuffer:
    """
    Groups multiple short sentences/clauses into a single, cohesive speech chunk.
    Only yields a chunk when it reaches a meaningful size (min 80 characters) 
    or when a hard newline or end-of-stream (flush) is reached.
    
    This keeps natural punctuation intact so Edge-TTS can produce seamless, 
    flowing human speech, preventing micro-fragments from triggering disjointed audio gaps.
    """
    def __init__(self, min_chunk_len: int = 80, max_chunk_len: int = 250):
        self.buffer = ""
        self.min_chunk_len = min_chunk_len
        self.max_chunk_len = max_chunk_len
        self.in_code_block = False
        self.code_placeholder_spoken = False

    def feed(self, token: str):
        self.buffer += token

        # Handle markdown code blocks
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

        # Parse sentences with length-aware consolidation
        while True:
            # Find earliest logical punctuation (. ! ? \n ।) followed by space or end of string
            match = re.search(r'([.!?\n।])(\s|$)', self.buffer)
            if not match:
                break

            delim_idx = match.start(1)
            delim = match.group(1)
            candidate = self.buffer[:delim_idx + 1]

            # Security: Skip decimal points (3.14)
            if delim == "." and 0 < delim_idx < len(self.buffer) - 1:
                prev_char = self.buffer[delim_idx - 1]
                next_char = self.buffer[delim_idx + 1]
                if prev_char.isdigit() and next_char.isdigit():
                    self.buffer = self.buffer[:delim_idx] + "_" + self.buffer[delim_idx + 1:]
                    continue

            # Security: Skip abbreviations (e.g. vs. / e.g.)
            abbrev_match = False
            if delim == "." and delim_idx > 0:
                if self.buffer[delim_idx - 1].isupper():
                    abbrev_match = True
                elif delim_idx >= 2 and self.buffer[delim_idx - 2:delim_idx].lower() in [
                    "eg", "vs", "ie", "dr", "mr", "ms"
                ]:
                    abbrev_match = True
            if abbrev_match:
                self.buffer = self.buffer[:delim_idx] + "\uFF0E" + self.buffer[delim_idx + 1:]
                continue

            candidate_clean = candidate.strip().replace("\uFF0E", ".").replace("_", ".")
            
            # ⚡ Dynamic Consolidation: If the accumulated sentence is too short, 
            # we do NOT yield it. We let it merge with the next clause/sentence.
            # We only yield if it's a hard newline (\n) or exceeds max_chunk_len.
            if len(candidate_clean) < self.min_chunk_len and delim != "\n" and len(self.buffer) < self.max_chunk_len:
                break

            # Yield the consolidated chunk
            self.buffer = self.buffer[match.end():]
            yield candidate_clean

    def flush(self):
        if self.in_code_block:
            self.buffer = ""
            return
        remaining = self.buffer.strip()
        self.buffer = ""
        if remaining:
            yield remaining.replace("\uFF0E", ".").replace("_", ".")

# ==========================================
# STREAMING VOICE PIPELINE
# ==========================================
def stream_llm_voice_output(token_generator) -> str:
    """
    Real-time voice output with gapless playback:
    - TTS worker synthesizes chunks in background
    - Playback worker decodes + trims silence + plays via persistent AudioPlayer
    - Strict ordering via seq_id
    - No PyAudio reinit between chunks
    """
    global t_start
    player = get_player()

    text_queue = queue.Queue(maxsize=16)
    audio_dict = {}
    audio_lock = threading.Lock()
    audio_available_event = threading.Event()
    playback_completed_event = threading.Event()

    total_sentences_expected = [None]
    first_token_received = [False]
    full_text_accumulated = []

    # TTS Worker
    def tts_worker():
        while True:
            item = text_queue.get()
            if item is None:
                text_queue.task_done()
                break

            seq_id, sentence = item
            if seq_id == 0:
                print(f"\n[LUCIA TTS] chunk={seq_id} synthesis start: {time.time() - t_start:.2f}s")

            try:
                cleaned = clean_text_for_speech(sentence)
                audio_bytes = synthesize_google_tts(cleaned) if cleaned else b""
            except Exception as e:
                print(f"\n[TTS Worker Error] chunk={seq_id}: {e}")
                audio_bytes = b""

            print(f"[TTS] queued chunk={seq_id} chars={len(sentence)} audio_bytes={len(audio_bytes)}")

            with audio_lock:
                audio_dict[seq_id] = audio_bytes
            audio_available_event.set()
            text_queue.task_done()

    # Playback Worker with silence trimming
    def playback_worker():
        next_seq_id = 0
        while True:
            if total_sentences_expected[0] is not None and next_seq_id >= total_sentences_expected[0]:
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
                    print(f"[LUCIA AUDIO] chunk={next_seq_id} playback start: {time.time() - t_start:.2f}s")

                if audio_bytes:
                    # ⚡ Trim leading/trailing silence, then play as raw PCM (fastest path)
                    seg = decode_and_trim(audio_bytes)
                    if seg is not None and len(seg) > 0:
                        print(f"[TTS] playing chunk={next_seq_id} duration={len(seg)}ms")
                        player.play_raw_pcm(
                            seg.raw_data,
                            width=seg.sample_width,
                            channels=seg.channels,
                            rate=seg.frame_rate,
                        )
                    else:
                        print(f"[TTS] chunk={next_seq_id} produced empty/invalid audio; skipping")
                else:
                    print(f"[TTS] chunk={next_seq_id} synthesis failed; skipping")

                next_seq_id += 1

        playback_completed_event.set()

    t_tts = threading.Thread(target=tts_worker, daemon=True, name="TTSWorker")
    t_play = threading.Thread(target=playback_worker, daemon=True, name="PlayWorker")
    t_tts.start()
    t_play.start()

    sentence_buf = SentenceBuffer()
    seq_counter = 0

    try:
        for chunk in token_generator:
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            if not content:
                continue

            if not first_token_received[0]:
                first_token_received[0] = True
                print(f"\n[LUCIA STREAM] First token: {time.time() - t_start:.2f}s")

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
        total_sentences_expected[0] = seq_counter
        text_queue.put(None)
        t_tts.join(timeout=2.0)
        audio_available_event.set()
        playback_completed_event.wait(timeout=30.0)
        t_play.join(timeout=1.0)
        print()

    return "".join(full_text_accumulated).strip()


# ==========================================
# UTILITIES
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
        elif speech_detected:
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
# MAIN DAEMON
# ==========================================
def main():
    global t_start
    print("\n" + "=" * 60)
    print("🤖 LUCIA DESKTOP DAEMON (Gapless Streaming Voice)")
    print("=" * 60)

    conv_id = get_desktop_conversation_id()
    print(f"📁 Active DB Session ID: #{conv_id}")

    model_path = Path(__file__).resolve().parent / "vosk-model-small-en-us-0.15"
    if not os.path.exists(model_path):
        print(f"❌ Error: {model_path} not found.")
        sys.exit(1)

    print("🔄 Loading Vosk wake engine...")
    vosk_model = VoskModel(str(model_path))
    grammar = '["lucia", "hey lucia", "sun lucia", "ok lucia", "[unk]"]'
    recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE, grammar)

    print("🔊 Initializing persistent audio player...")
    player = get_player()
    atexit.register(shutdown_player)
    atexit.register(shutdown_tts_loop)

    print("🔊 Pre-caching wake acknowledgments...")
    cached_acks = []
    for phrase in WAKE_PHRASES:
        audio = synthesize_google_tts(phrase)
        if audio:
            cached_acks.append((phrase, audio))
    if not cached_acks:
        cached_acks = [("Haan bhai?", synthesize_google_tts("Haan bhai?"))]

    chup_audio = synthesize_google_tts("Theek hai bhai, main chup hoon.")

    saved_err = suppress_stderr()
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE,
        input=True, frames_per_buffer=CHUNK_SIZE
    )
    restore_stderr(saved_err)

    print("\n⚡ LUCIA is Online • Gapless Voice Ready!")
    print("📢 Wake words: 'LUCIA' or 'Hey Lucia'")
    print("─" * 60)
    print("🟢 Waiting for wake word... (Ctrl+C to stop)\n")

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
                    player.play(selected_audio)

                    wav_bytes = record_command(stream)
                    t_start = time.time()

                    user_text = transcribe_audio(wav_bytes)
                    print(f"[LUCIA STT] Transcription ready: {time.time() - t_start:.2f}s")

                    if not user_text or user_text.startswith("⚠️"):
                        print("⚠️ No command heard.")
                        player.play(synthesize_google_tts("Aawaz samajh nahi aayi bhai.") or b"")
                        print("\n🟢 Waiting for 'LUCIA'...\n" + "─" * 60)
                        recognizer.Reset()
                        continue

                    print(f"👤 USER: \"{user_text}\"")

                    if is_stop_command(user_text):
                        print("🤫 Stop command received.")
                        player.play(chup_audio or b"")
                        recognizer.Reset()
                        print("\n🟢 Waiting for 'LUCIA'...\n" + "─" * 60)
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
                            player.play(synthesize_google_tts(reply_text) or b"")
                            action_done = True

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
                        token_stream = model.stream(context)
                        reply_text = stream_llm_voice_output(token_stream)

                        if reply_text:
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