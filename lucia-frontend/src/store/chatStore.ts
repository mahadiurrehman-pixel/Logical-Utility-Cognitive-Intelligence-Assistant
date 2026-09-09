import { create } from "zustand";
import type { Message, ActivityState } from "@/types";
import { streamChat } from "@/lib/api/chat";
import { createConversation } from "@/lib/api/conversations";

// Global reference to prevent audio overlap
let activeAudio: HTMLAudioElement | null = null;

interface ChatState {
  currentConversationId: string | null;
  messages: Message[];
  activity: ActivityState;
  enableVoice: boolean;
  setConversation: (id: string | null) => void;
  addMessage: (m: Message) => void;
  updateStreamingMessage: (id: string, content: string) => void;
  completeStreamingMessage: (id: string, metadata?: any) => void;
  setActivity: (a: ActivityState) => void;
  setEnableVoice: (v: boolean) => void;
  clearMessages: () => void;
  sendMessage: (text: string, attachmentIds?: string[]) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  currentConversationId: null,
  messages: [],
  activity: { active: false },
  enableVoice: true,

  setConversation: (id) => set({ currentConversationId: id, messages: [] }),
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),

  setEnableVoice: (enableVoice) => {
    set({ enableVoice });
    if (!enableVoice && activeAudio) {
      activeAudio.pause();
      activeAudio = null;
    }
  },

  updateStreamingMessage: (id, content) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + content } : m
      ),
    })),

  completeStreamingMessage: (id, metadata) => {
    const msg = get().messages.find((m) => m.id === id);
    if (!msg) return;

    const wasStreaming = msg.streaming;

    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, streaming: false, metadata: metadata || m.metadata } : m
      ),
    }));

    if (wasStreaming && get().enableVoice) {
      if (activeAudio) {
        activeAudio.pause();
        activeAudio = null;
      }

      const cleanContent = msg.content.trim();
      if (cleanContent) {
        const url = `http://localhost:8000/audio/synthesize?text=${encodeURIComponent(cleanContent)}`;
        const audio = new Audio(url);
        activeAudio = audio;
        audio.play().catch((e) => console.log("Autoplay blocked or interrupted", e));
      }
    }
  },

  setActivity: (activity) => set({ activity }),
  clearMessages: () => set({ messages: [] }),

  sendMessage: async (text: string, attachmentIds: string[] = []) => {
    const trimmed = text.trim();
    if (!trimmed && attachmentIds.length === 0) return;
    if (get().activity.active) return;

    if (activeAudio) {
      activeAudio.pause();
      activeAudio = null;
    }

    let convId = get().currentConversationId;

    if (!convId) {
      const newConv = await createConversation(trimmed.slice(0, 20) || "New Conversation");
      set({ currentConversationId: newConv.id });
      convId = newConv.id;
    }

    const userMsgId = crypto.randomUUID();
    const luciaMsgId = crypto.randomUUID();

    get().addMessage({
      id: userMsgId,
      role: "user",
      content: trimmed || `[Attached ${attachmentIds.length} file(s)]`,
      timestamp: new Date().toISOString(),
    });

    set({ activity: { active: true, status: "thinking" } });

    get().addMessage({
      id: luciaMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      streaming: true,
    });

    await streamChat({
      message: trimmed,
      conversationId: convId,
      attachmentIds,
      onToken: (token) => get().updateStreamingMessage(luciaMsgId, token),
      onActivity: (act) => {
        set({ activity: act });
        if (act.conversationId) set({ currentConversationId: act.conversationId });
      },
      onMetadata: (metadata) => get().completeStreamingMessage(luciaMsgId, metadata),
      onComplete: () => get().completeStreamingMessage(luciaMsgId),
      onError: () => set({ activity: { active: false } }),
    });
  },
}));