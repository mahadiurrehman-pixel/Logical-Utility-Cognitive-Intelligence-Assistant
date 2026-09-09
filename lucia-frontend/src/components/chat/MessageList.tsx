"use client";

import { useEffect, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import { Message } from "./Message";
import { LuciaActivity } from "@/components/lucia/LuciaActivity";
import { LuciaEmptyState } from "@/components/lucia/LuciaEmptyState";

export function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const activity = useChatStore((s) => s.activity);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, activity.active]);

  if (messages.length === 0 && !activity.active) {
    return <LuciaEmptyState />;
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto pb-32">
        {messages.map((m, idx) => (
          <Message key={`msg-${m.id}-${idx}`} message={m} />
        ))}
        {activity.active && (
          <div className="px-6 md:px-8 py-4">
            <LuciaActivity activity={activity} />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}