"use client";

import { LuciaMark } from "./LuciaMark";
import { Play, Mail, Terminal, Search } from "lucide-react";
import { useChatStore } from "@/store/chatStore";

export function LuciaEmptyState() {
  const sendMessage = useChatStore((s) => s.sendMessage);

  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  const prompts = [
    {
      icon: Play,
      title: "Play Music",
      desc: "YouTube par LoFi chill beats chalao",
      query: "YouTube par LoFi music chalao",
    },
    {
      icon: Mail,
      title: "Check Inbox",
      desc: "Gmail se unread emails check karo",
      query: "Mere unread emails check karo aur summary do",
    },
    {
      icon: Terminal,
      title: "Python Sandbox",
      desc: "Desktop par Python OOP class script run karo",
      query: "Desktop par Python learning/lucia_test folder ke andar test.py run karo",
    },
    {
      icon: Search,
      title: "Live Web Intel",
      desc: "What is RAG in Generative AI?",
      query: "What is RAG architecture in Generative AI?",
    },
  ];

  return (
    <div className="flex flex-col items-center justify-center min-h-[75vh] max-w-2xl mx-auto px-6 text-center animate-fade-in-up">
      <div className="relative mb-6">
        <div className="absolute inset-0 rounded-full bg-accent/15 blur-2xl transform scale-150" />
        <LuciaMark size="lg" withLabel={false} />
      </div>

      <div className="text-2xs font-mono uppercase tracking-[0.3em] text-accent mb-2">
        Personal Intelligence System
      </div>

      <h1 className="text-3xl md:text-4xl font-light text-foreground tracking-tight text-balance">
        {greeting}, <span className="font-normal text-white">Mahadi</span>.
      </h1>
      <p className="mt-2 text-sm md:text-base text-foreground-muted font-light max-w-md">
        I'm active in the background. What are we building or automating today?
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-10 w-full text-left">
        {prompts.map((p, i) => {
          const Icon = p.icon;
          return (
            <button
              key={i}
              onClick={() => sendMessage(p.query)}
              className="group relative flex items-start gap-3.5 p-4 rounded-xl border border-border/80 bg-background-elevated/60 hover:bg-background-panel hover:border-accent/40 transition-all duration-200"
            >
              <div className="p-2 rounded-lg bg-background border border-border group-hover:border-accent/30 group-hover:text-accent text-foreground-subtle transition-colors">
                <Icon className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-foreground group-hover:text-white transition-colors">
                  {p.title}
                </div>
                <div className="text-2xs text-foreground-muted truncate mt-0.5 font-light">
                  {p.desc}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}