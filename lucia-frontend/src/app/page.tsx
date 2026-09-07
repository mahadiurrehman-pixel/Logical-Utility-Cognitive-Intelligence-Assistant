"use client";

import { useState } from "react";
import { NavigationRail } from "@/components/navigation/NavigationRail";
import { ConversationList } from "@/components/conversation/ConversationList";
import { ChatWorkspace } from "@/components/chat/ChatWorkspace";
import { CommandPalette } from "@/components/command/CommandPalette";
import { SystemStatus } from "@/components/system/SystemStatus";
import { useCommandPalette } from "@/hooks/useCommandPalette";
import { useChatStore } from "@/store/chatStore";
import { Settings, Wrench, X, Shield, Cpu, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export default function Home() {
  const { open, openPalette, closePalette } = useCommandPalette();
  const clearMessages = useChatStore((s) => s.clearMessages);
  const setConversation = useChatStore((s) => s.setConversation);
  
  // Drawer states
  const [activePanel, setActivePanel] = useState<"tools" | "settings" | null>(null);

  function handleNewChat() {
    clearMessages();
    setConversation(null);
  }

  const navigationRailProps = {
    onNewChat: handleNewChat,
    onOpenSearch: openPalette,
    onOpenTools: () => setActivePanel("tools"),
    onOpenSettings: () => setActivePanel("settings"),
  } as any;

  return (
    <main className="h-screen bg-background text-foreground overflow-hidden relative">
      {/* 1. Sidebar Nav Rail */}
      <NavigationRail {...navigationRailProps} />
      
      {/* 2. Slide-out Settings & Tools Panel */}
      <div 
        className={cn(
          "fixed top-0 right-0 h-screen w-80 border-l border-border bg-background-elevated/95 backdrop-blur-md shadow-2xl z-50 transition-transform duration-300 ease-in-out",
          activePanel ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div className="flex items-center gap-2">
            {activePanel === "tools" ? <Wrench className="h-4 w-4 text-accent" /> : <Settings className="h-4 w-4 text-accent" />}
            <span className="text-xs uppercase tracking-[0.2em] text-foreground font-semibold">
              {activePanel === "tools" ? "Systems & Tools" : "Lucia Console"}
            </span>
          </div>
          <button 
            onClick={() => setActivePanel(null)}
            className="p-1 rounded bg-background hover:bg-background-panel text-foreground-subtle hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto h-[calc(100vh-64px)] space-y-6 text-sm">
          {activePanel === "tools" ? (
            <>
              <div>
                <h3 className="text-2xs uppercase tracking-wider text-foreground-subtle mb-3">Available Utilities</h3>
                <div className="space-y-2">
                  {[
                    ["🌐 Web Grounding", "Operational", "duckduckgo"],
                    ["📧 Gmail Reader", "Connected", "oauth-v2"],
                    ["📂 Secure FileSystem", "Locked", "~/Desktop"],
                    ["💻 Terminal Executor", "Sandbox", "bash/py3"],
                  ].map(([label, status, details]) => (
                    <div key={label} className="p-3 rounded-lg bg-background border border-border">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-foreground">{label}</span>
                        <span className="text-2xs text-status-healthy font-mono">{status}</span>
                      </div>
                      <span className="text-2xs text-foreground-subtle font-mono">{details}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="space-y-4">
                <div>
                  <h3 className="text-2xs uppercase tracking-wider text-foreground-subtle mb-3">Gateway Failover Chain</h3>
                  <div className="space-y-1.5 text-xs font-mono">
                    {["Groq Primary (Llama 3.3)", "Groq MDI (Llama 3.3)", "Groq UNI (Llama 3.3)", "HuggingFace (Qwen)", "Gemini (Flash-Lite)"].map((p, idx) => (
                      <div key={p} className="flex items-center justify-between p-2.5 rounded bg-background border border-border">
                        <span className="text-foreground-muted">{idx + 1}. {p}</span>
                        <div className="h-1.5 w-1.5 rounded-full bg-status-healthy" />
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-2 border-t border-border">
                  <h3 className="text-2xs uppercase tracking-wider text-foreground-subtle mb-3">Security Constraints</h3>
                  <div className="space-y-2 text-2xs text-foreground-muted leading-relaxed font-light">
                    <p className="flex items-start gap-2"><Shield className="h-3.5 w-3.5 text-accent flex-shrink-0 mt-0.5" /> <span>Filesystem manipulation locked strictly to allowed home folders.</span></p>
                    <p className="flex items-start gap-2"><Cpu className="h-3.5 w-3.5 text-accent flex-shrink-0 mt-0.5" /> <span>Dangerous system/escalation shell patterns are compiled & filtered.</span></p>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 3. Conversations Sidebar */}
      <ConversationList />
      
      {/* 4. Chat Area */}
      <div className="h-full pl-14 md:pl-[280px]">
        <ChatWorkspace />
      </div>
      
      {/* 5. Telemetry & Palette */}
      <SystemStatus />
      <CommandPalette open={open} onClose={closePalette} />
    </main>
  );
}