"use client";

import { cn } from "@/lib/utils/cn";
import type { ActivityState } from "@/types";

interface Props {
  activity: ActivityState;
}

export function LuciaActivity({ activity }: Props) {
  if (!activity.active) return null;

  const label = {
    thinking: "thinking",
    processing: "processing",
    "using-tool": activity.detail || "using tool",
    "switching-model": "switching model",
  }[activity.status || "thinking"];

  return (
    <div className="flex items-center gap-3 py-2 animate-fade-in">
      <div className="text-2xs uppercase tracking-[0.2em] text-foreground-muted font-medium">
        LUCIA
      </div>
      <div className="flex items-center gap-2">
        <div className="relative h-1 w-8 overflow-hidden rounded-full bg-border">
          <div className="absolute inset-y-0 left-0 w-full bg-accent origin-left animate-activity-flow" />
        </div>
        <span className="text-xs text-foreground-muted italic">{label}</span>
      </div>
    </div>
  );
}