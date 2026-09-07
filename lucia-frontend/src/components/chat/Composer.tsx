"use client";

import { useRef, useState, KeyboardEvent } from "react";
import { Mic, Plus, ArrowUp, Command, Square, Volume2, VolumeX } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useChatStore } from "@/store/chatStore";

export function Composer() {
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const sendMessage = useChatStore((s) => s.sendMessage);
  const activity = useChatStore((s) => s.activity);
  
  // 🔊 Voice states from Zustand store
  const enableVoice = useChatStore((s) => s.enableVoice);
  const setEnableVoice = useChatStore((s) => s.setEnableVoice);

  async function handleSend() {
    if (!input.trim() || activity.active) return;
    const text = input;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendMessage(text);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleInput() {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }

  // ==========================================
  // 🎙️ LIVE BROWSER AUDIO RECORDING
  // ==========================================
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        const formData = new FormData();
        formData.append("file", audioBlob, "recording.wav");

        setInput("Transcribing your audio...");
        try {
          const res = await fetch("http://localhost:8000/audio/transcribe", {
            method: "POST",
            body: formData,
          });
          const data = await res.json();
          if (data.text) {
            setInput(data.text);
            if (textareaRef.current) textareaRef.current.focus();
          } else {
            setInput("");
          }
        } catch (err) {
          console.error("Transcription failed", err);
          setInput("");
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Mic access denied", err);
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 md:left-[280px]">
      <div className="bg-gradient-to-t from-background via-background/95 to-transparent pt-6 pb-6 px-6">
        <div className="max-w-3xl mx-auto">
          <div
            className={cn(
              "relative rounded-2xl transition-all duration-300",
              "bg-[#0d0f14]/90 backdrop-blur-xl border",
              focused
                ? "border-accent/50 shadow-[0_0_25px_-5px_rgba(56,189,248,0.25)] ring-1 ring-accent/30"
                : "border-border/80 hover:border-border-strong shadow-2xl"
            )}
          >
            <div className="flex items-end gap-2 px-3 py-2.5">
              <button
                type="button"
                className="p-2 rounded-xl text-foreground-subtle hover:text-foreground hover:bg-background-panel transition-colors"
                title="Attach file/context"
              >
                <Plus className="h-4 w-4" />
              </button>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onInput={handleInput}
                onKeyDown={handleKeyDown}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                placeholder={isRecording ? "Listening to your voice..." : "Ask LUCIA anything..."}
                rows={1}
                disabled={isRecording}
                className="flex-1 bg-transparent resize-none outline-none py-2 text-[15px] text-foreground placeholder:text-foreground-subtle max-h-[180px] leading-relaxed font-light"
              />

              <div className="flex items-center gap-1.5 pb-0.5">
                {/* 🔊 Voice Toggle Button (Mute/Unmute) */}
                <button
                  type="button"
                  onClick={() => setEnableVoice(!enableVoice)}
                  className={cn(
                    "p-2 rounded-xl transition-all duration-200",
                    enableVoice
                      ? "text-accent hover:bg-accent/10 shadow-[0_0_8px_rgba(56,189,248,0.2)]"
                      : "text-foreground-subtle hover:text-foreground hover:bg-background-panel"
                  )}
                  title={enableVoice ? "Mute Voice Output" : "Unmute Voice Output"}
                >
                  {enableVoice ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
                </button>

                {/* 🎙️ Voice Mic Trigger */}
                <button
                  type="button"
                  onClick={isRecording ? stopRecording : startRecording}
                  className={cn(
                    "p-2 rounded-xl transition-all relative",
                    isRecording
                      ? "bg-status-error/25 text-status-error border border-status-error/40 animate-pulse"
                      : "text-foreground-subtle hover:text-foreground hover:bg-background-panel"
                  )}
                  title={isRecording ? "Stop Recording" : "Mic Input"}
                >
                  {isRecording ? <Square className="h-4 w-4 fill-status-error" /> : <Mic className="h-4 w-4" />}
                </button>

                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!input.trim() || activity.active || isRecording}
                  className={cn(
                    "p-2 rounded-xl transition-all duration-200",
                    input.trim() && !activity.active && !isRecording
                      ? "bg-accent text-background hover:bg-accent/90 shadow-[0_0_12px_#38bdf8]"
                      : "text-foreground-subtle bg-background-panel cursor-not-allowed opacity-50"
                  )}
                >
                  <ArrowUp className="h-4 w-4 stroke-[2.5]" />
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between px-4 py-1.5 border-t border-border/40 text-2xs font-mono text-foreground-subtle">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1">
                  <Command className="h-2.5 w-2.5" />K to search
                </span>
              </div>
              <span>Return to send · Shift+Return for newline</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}