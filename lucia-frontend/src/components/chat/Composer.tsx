"use client";

import { useRef, useState, KeyboardEvent, DragEvent, useEffect } from "react";
import { Mic, Plus, ArrowUp, Command, Square, Volume2, VolumeX } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useChatStore } from "@/store/chatStore";
import { useFileUpload } from "@/hooks/useFileUpload";
import { AttachmentPreview } from "./AttachmentPreview";
import { SUPPORTED_EXTENSIONS } from "@/types/attachments";

export function Composer() {
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const { uploads, addFiles, removeUpload, clearAll, getReadyAttachmentIds } = useFileUpload();
  
  const sendMessage = useChatStore((s) => s.sendMessage);
  const activity = useChatStore((s) => s.activity);
  const enableVoice = useChatStore((s) => s.enableVoice);
  const setEnableVoice = useChatStore((s) => s.setEnableVoice);
  
  async function handleSend() {
    if ((!input.trim() && uploads.length === 0) || activity.active) return;
    
    const attachmentIds = getReadyAttachmentIds();
    const hasPending = uploads.some((u) => u.status === "uploading");
    
    if (hasPending) {
      alert("Please wait for attachments to finish uploading");
      return;
    }
    
    const text = input.trim() || (attachmentIds.length > 0 ? "Analyze the attached file(s)." : "");
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    
    await sendMessage(text, attachmentIds);
    clearAll();
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
  
  // File picker
  function handleFileButtonClick() {
    fileInputRef.current?.click();
  }
  
  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
      e.target.value = "";
    }
  }
  
  // Drag & drop
  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes("Files")) {
      setIsDragOver(true);
    }
  }
  
  function handleDragLeave(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }
  
  function handleDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  }
  
  // Voice recording (existing)
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        const formData = new FormData();
        formData.append("file", audioBlob, "recording.wav");
        
        setInput("Transcribing your audio...");
        try {
          const res = await fetch("http://localhost:8000/audio/transcribe", {
            method: "POST", body: formData,
          });
          const data = await res.json();
          setInput(data.text || "");
          if (data.text && textareaRef.current) textareaRef.current.focus();
        } catch {
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
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
    }
  }
  
  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 md:left-[280px]">
      <div className="bg-gradient-to-t from-background via-background/95 to-transparent pt-6 pb-6 px-6">
        <div className="max-w-3xl mx-auto">
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "relative rounded-2xl transition-all duration-300",
              "bg-[#0d0f14]/90 backdrop-blur-xl border",
              isDragOver
                ? "border-accent border-dashed ring-2 ring-accent/40"
                : focused
                ? "border-accent/50 shadow-[0_0_25px_-5px_rgba(56,189,248,0.25)] ring-1 ring-accent/30"
                : "border-border/80 hover:border-border-strong shadow-2xl"
            )}
          >
            {/* Drag overlay message */}
            {isDragOver && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 rounded-2xl z-10 pointer-events-none">
                <div className="text-accent font-medium text-sm">
                  Drop files to attach
                </div>
              </div>
            )}
            
            {/* Attachment previews */}
            <AttachmentPreview uploads={uploads} onRemove={removeUpload} />
            
            <div className="flex items-end gap-2 px-3 py-2.5">
              {/* Attach button */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={SUPPORTED_EXTENSIONS.join(",")}
                onChange={handleFileChange}
                className="hidden"
              />
              <button
                type="button"
                onClick={handleFileButtonClick}
                className="p-2 rounded-xl text-foreground-subtle hover:text-accent hover:bg-background-panel transition-colors"
                title="Attach file"
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
                placeholder={isRecording ? "Listening..." : "Ask LUCIA anything or drop a file..."}
                rows={1}
                disabled={isRecording}
                className="flex-1 bg-transparent resize-none outline-none py-2 text-[15px] text-foreground placeholder:text-foreground-subtle max-h-[180px] leading-relaxed font-light"
              />
              
              <div className="flex items-center gap-1.5 pb-0.5">
                <button
                  type="button"
                  onClick={() => setEnableVoice(!enableVoice)}
                  className={cn(
                    "p-2 rounded-xl transition-all",
                    enableVoice
                      ? "text-accent hover:bg-accent/10"
                      : "text-foreground-subtle hover:text-foreground hover:bg-background-panel"
                  )}
                  title={enableVoice ? "Mute Voice" : "Unmute Voice"}
                >
                  {enableVoice ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
                </button>
                
                <button
                  type="button"
                  onClick={isRecording ? stopRecording : startRecording}
                  className={cn(
                    "p-2 rounded-xl transition-all",
                    isRecording
                      ? "bg-status-error/25 text-status-error border border-status-error/40 animate-pulse"
                      : "text-foreground-subtle hover:text-foreground hover:bg-background-panel"
                  )}
                  title={isRecording ? "Stop" : "Mic Input"}
                >
                  {isRecording ? <Square className="h-4 w-4 fill-status-error" /> : <Mic className="h-4 w-4" />}
                </button>
                
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={(!input.trim() && uploads.length === 0) || activity.active || isRecording}
                  className={cn(
                    "p-2 rounded-xl transition-all duration-200",
                    (input.trim() || uploads.length > 0) && !activity.active && !isRecording
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
              <span>Return to send · Drop files to attach</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}