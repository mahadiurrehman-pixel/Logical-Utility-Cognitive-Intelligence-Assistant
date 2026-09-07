"use client";

import { useEffect, useState } from "react";
import { cn, formatTime, formatRelativeDate } from "@/lib/utils/cn";
import { getConversations } from "@/lib/api/conversations";
import { apiFetch } from "@/lib/api/client";
import { useChatStore } from "@/store/chatStore";
import type { Conversation, Message } from "@/types";

export function ConversationList() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const currentId = useChatStore((s) => s.currentConversationId);
  const setConversation = useChatStore((s) => s.setConversation);
  const addMessage = useChatStore((s) => s.addMessage);
  const clearMessages = useChatStore((s) => s.clearMessages);

  useEffect(() => {
    getConversations().then(setConversations);
  }, []);

  async function handleSelect(id: string) {
    setConversation(id);
    clearMessages();
    try {
      const msgs = await apiFetch<Message[]>(`/conversations/${id}/messages`);
      msgs.forEach((m) => addMessage(m));
    } catch (e) {
      console.error("Failed to load messages", e);
    }
  }

  const grouped = conversations.reduce<Record<string, Conversation[]>>((acc, c) => {
    const key = formatRelativeDate(c.updatedAt);
    if (!acc[key]) acc[key] = [];
    acc[key].push(c);
    return acc;
  }, {});

  return (
    <aside className="hidden md:flex flex-col fixed left-[60px] top-0 h-screen w-[220px] border-r border-border bg-background overflow-y-auto z-30">
      <div className="p-4 pb-6">
        <div className="text-2xs uppercase tracking-[0.2em] text-foreground-subtle font-medium">
          Conversations
        </div>
      </div>

      <div className="flex-1 px-3 pb-6">
        {Object.entries(grouped).map(([group, convs]) => (
          <div key={group} className="mb-5">
            <div className="px-2 mb-1 text-2xs uppercase tracking-wider text-foreground-subtle">
              {group}
            </div>
            <div className="space-y-0.5">
              {convs.map((c) => (
                <button
                  key={c.id}
                  onClick={() => handleSelect(c.id)}
                  className={cn(
                    "w-full text-left px-2 py-1.5 rounded-md text-sm transition-all group",
                    currentId === c.id
                      ? "bg-background-panel text-foreground"
                      : "text-foreground-muted hover:bg-background-panel/50 hover:text-foreground"
                  )}
                >
                  <div className="flex items-center gap-2">
                    {currentId === c.id && (
                      <div className="h-1 w-1 rounded-full bg-accent flex-shrink-0" />
                    )}
                    <span className="truncate flex-1">{c.title}</span>
                    <span className="text-2xs font-mono text-foreground-subtle opacity-0 group-hover:opacity-100 transition-opacity">
                      {formatTime(c.updatedAt)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}