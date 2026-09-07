"use client";

import { MessageList } from "./MessageList";
import { Composer } from "./Composer";

export function ChatWorkspace() {
  return (
    <div className="flex flex-col h-full relative lucia-grid-bg lucia-radial-glow overflow-hidden">
      <MessageList />
      <Composer />
    </div>
  );
}