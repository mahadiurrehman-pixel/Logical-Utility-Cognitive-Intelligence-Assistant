"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { getConversations } from "@/lib/api/conversations";
import { useChatStore } from "@/store/chatStore";
import type { Conversation } from "@/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const setConversation = useChatStore((s) => s.setConversation);

  useEffect(() => {
    if (open) getConversations().then(setConversations);
  }, [open]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape" && open) onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-background/80 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg mx-6 bg-background-elevated border border-border rounded-xl shadow-2xl overflow-hidden animate-fade-in-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search className="h-4 w-4 text-foreground-subtle" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations, tools, settings..."
            className="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-foreground-subtle"
          />
          <kbd className="text-2xs font-mono text-foreground-subtle px-1.5 py-0.5 border border-border rounded">
            ESC
          </kbd>
        </div>

        <div className="max-h-[400px] overflow-y-auto py-2">
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-foreground-subtle">
              No results
            </div>
          )}
          {filtered.map((c) => (
            <button
              key={c.id}
              onClick={() => {
                setConversation(c.id);
                onClose();
              }}
              className="w-full px-4 py-2.5 text-left text-sm text-foreground hover:bg-background-panel transition-colors flex items-center gap-2"
            >
              <div className="h-1 w-1 rounded-full bg-accent" />
              {c.title}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}