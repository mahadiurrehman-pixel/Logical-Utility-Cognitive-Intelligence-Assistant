"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils/cn";
import { getProviders } from "@/lib/api/system";
import { Zap } from "lucide-react";
import type { Provider } from "@/types";

export function SystemStatus() {
  const [current, setCurrent] = useState<Provider | null>(null);

  useEffect(() => {
    getProviders().then((p) => {
      setCurrent(p.find((x) => x.status === "healthy") || p[0]);
    });
  }, []);

  if (!current) return null;

  return (
    <div className="fixed bottom-4 right-6 z-20 hidden md:flex items-center gap-2 px-3 py-1.5 bg-[#0d0f14]/80 backdrop-blur-md border border-border/80 rounded-full text-2xs font-mono text-foreground-muted shadow-xl select-none">
      <div className="h-1.5 w-1.5 rounded-full bg-status-healthy animate-pulse-subtle" />
      <span className="text-foreground">{current.name}</span>
      <span className="text-foreground-subtle">·</span>
      <span className="text-accent">{current.model}</span>
      <span className="text-foreground-subtle">·</span>
      <span className="flex items-center gap-0.5 text-emerald-400">
        <Zap className="h-2.5 w-2.5" />
        0.12s
      </span>
    </div>
  );
}