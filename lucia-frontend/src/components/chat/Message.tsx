"use client";

import { useState } from "react";
import { Check, Copy, Terminal } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import type { Message as MessageType } from "@/types";
import { StreamingCursor } from "./StreamingCursor";

interface Props {
  message: MessageType;
}

export function Message({ message }: Props) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // 📝 Editorial level Markdown & List Parser
  const parseMarkdown = (text: string) => {
    const lines = text.split("\n");
    return lines.map((line, idx) => {
      let trimmed = line.trim();
      
      // 1. Headers (e.g., ### Title)
      if (trimmed.startsWith("###")) {
        return (
          <h4 key={idx} className="text-base font-semibold text-white mt-5 mb-2 font-sans tracking-wide">
            {trimmed.slice(3).trim()}
          </h4>
        );
      }
      if (trimmed.startsWith("##")) {
        return (
          <h3 key={idx} className="text-lg font-semibold text-white mt-6 mb-3 font-sans tracking-wide">
            {trimmed.slice(2).trim()}
          </h3>
        );
      }
      if (trimmed.startsWith("#")) {
        return (
          <h2 key={idx} className="text-xl font-bold text-white mt-8 mb-4 font-sans tracking-tight">
            {trimmed.slice(1).trim()}
          </h2>
        );
      }

      // 2. Bullet Lists (e.g., - Item)
      if (trimmed.startsWith("-") || trimmed.startsWith("*")) {
        return (
          <li key={idx} className="ml-4 pl-1 list-disc text-[15px] font-light text-foreground/95 mb-1.5 leading-relaxed">
            {parseInlineStyles(trimmed.slice(1).trim())}
          </li>
        );
      }

      // 3. Numbered Lists (e.g., 1. Item)
      if (/^\d+\./.test(trimmed)) {
        const dotIdx = trimmed.indexOf(".");
        return (
          <li key={idx} className="ml-4 pl-1 list-decimal text-[15px] font-light text-foreground/95 mb-1.5 leading-relaxed">
            {parseInlineStyles(trimmed.slice(dotIdx + 1).trim())}
          </li>
        );
      }

      // 4. Horizontal Separator
      if (trimmed === "---") {
        return <hr key={idx} className="my-6 border-border/50" />;
      }

      // Default paragraph
      return trimmed ? (
        <p key={idx} className="text-[15px] font-light text-foreground/90 leading-relaxed mb-3 text-balance">
          {parseInlineStyles(line)}
        </p>
      ) : (
        <div key={idx} className="h-2" />
      );
    });
  };

  // Bold (**text**) and code (`text`) inline parser
  const parseInlineStyles = (line: string) => {
    const boldRegex = /\*\*(.*?)\*\*/g;
    const codeRegex = /`(.*?)`/g;
    
    let parts: React.ReactNode[] = [line];
    
    // Parse Bold
    parts = parts.flatMap((part) => {
      if (typeof part !== "string") return part;
      const subParts = part.split(boldRegex);
      return subParts.map((sub, i) => (i % 2 === 1 ? <strong key={i} className="font-semibold text-white">{sub}</strong> : sub));
    });

    // Parse Inline Code
    parts = parts.flatMap((part) => {
      if (typeof part !== "string") return part;
      const subParts = part.split(codeRegex);
      return subParts.map((sub, i) => (i % 2 === 1 ? <code key={i} className="px-1.5 py-0.5 rounded bg-background-panel border border-border/60 text-xs font-mono text-cyan-300">{sub}</code> : sub));
    });

    return parts;
  };

  const renderFormattedContent = (content: string) => {
    if (isUser) {
      return <p className="text-[15px] font-normal leading-relaxed">{content}</p>;
    }

    const parts = content.split(/(```[\s\S]*?```)/g);

    return (
      <div className="space-y-1">
        {parts.map((part, index) => {
          if (part.startsWith("```") && part.endsWith("```")) {
            const lines = part.slice(3, -3).trim().split("\n");
            const language = lines[0].trim() || "python";
            const code = lines.slice(1).join("\n") || lines[0];

            return (
              <div key={index} className="my-5 rounded-xl border border-border bg-[#0a0c10] overflow-hidden shadow-2xl">
                <div className="flex items-center justify-between px-4 py-2 border-b border-border/60 bg-[#0d1015]">
                  <div className="flex items-center gap-2">
                    <Terminal className="h-3.5 w-3.5 text-accent" />
                    <span className="text-2xs font-mono uppercase text-foreground-muted">{language}</span>
                  </div>
                  <button
                    onClick={() => navigator.clipboard.writeText(code)}
                    className="flex items-center gap-1.5 text-2xs text-foreground-subtle hover:text-foreground transition-colors"
                  >
                    <Copy className="h-3 w-3" />
                    <span>Copy</span>
                  </button>
                </div>
                <pre className="p-4 text-xs font-mono overflow-x-auto text-emerald-300/90 leading-relaxed">
                  <code>{code}</code>
                </pre>
              </div>
            );
          }

          return <div key={index}>{parseMarkdown(part)}</div>;
        })}
      </div>
    );
  };

  return (
    <div
      className={cn(
        "group relative py-6 px-4 md:px-8 transition-colors duration-200 animate-fade-in-up",
        isUser
          ? "bg-transparent"
          : "bg-background-elevated/40 border-l-2 border-accent/60 my-2 rounded-r-2xl"
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          {isUser ? (
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-foreground-subtle" />
              <span className="text-2xs uppercase tracking-[0.2em] font-medium text-foreground-muted">
                You
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-accent animate-pulse-subtle shadow-[0_0_6px_#38bdf8]" />
              <span className="text-2xs uppercase tracking-[0.25em] font-semibold text-accent">
                LUCIA
              </span>
            </div>
          )}
        </div>

        {!isUser && !message.streaming && (
          <button
            onClick={handleCopy}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md hover:bg-background-panel text-foreground-subtle hover:text-foreground"
            title="Copy response"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-status-healthy" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>

      <div className="pl-4">
        {renderFormattedContent(message.content)}
        {message.streaming && <StreamingCursor />}
      </div>

      {!isUser && !message.streaming && message.metadata && (
        <div className="mt-4 pl-4 flex items-center gap-2 text-2xs font-mono text-foreground-subtle select-none">
          <span className="px-1.5 py-0.5 rounded bg-background-panel border border-border">
            {message.metadata.provider || "Groq LPU"}
          </span>
          <span>·</span>
          <span>{message.metadata.model || "llama-3.3-70b"}</span>
          {message.metadata.responseTime && (
            <>
              <span>·</span>
              <span className="text-accent/80">{message.metadata.responseTime.toFixed(2)}s</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}