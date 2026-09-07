"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { getProviders } from "@/lib/api/system";
import { LuciaMark } from "@/components/lucia/LuciaMark";
import { cn } from "@/lib/utils/cn";
import type { Provider } from "@/types";

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);

  useEffect(() => {
    getProviders().then(setProviders);
  }, []);

  const statusColor = {
    healthy: "bg-status-healthy",
    cooldown: "bg-status-cooldown",
    error: "bg-status-error",
    available: "bg-foreground-muted",
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-foreground-muted hover:text-foreground transition-colors mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to LUCIA
        </Link>

        <LuciaMark size="lg" className="mb-2" />
        <h1 className="text-2xl font-light mb-12">Settings</h1>

        <section className="mb-12">
          <h2 className="text-sm uppercase tracking-[0.2em] text-foreground-subtle mb-6">
            AI Providers
          </h2>
          <div className="space-y-1">
            {providers.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between py-3 px-4 rounded-lg hover:bg-background-elevated transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className={cn("h-1.5 w-1.5 rounded-full", statusColor[p.status])} />
                  <div>
                    <div className="text-sm text-foreground font-medium">{p.name}</div>
                    <div className="text-2xs font-mono text-foreground-subtle mt-0.5">
                      {p.model}
                    </div>
                  </div>
                </div>
                <div className="text-2xs uppercase tracking-wider text-foreground-muted">
                  {p.status}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-sm uppercase tracking-[0.2em] text-foreground-subtle mb-6">
            System
          </h2>
          <div className="space-y-1 text-sm">
            {[
              ["AI Gateway", "Operational"],
              ["Tools", "Operational"],
              ["Gmail", "Connected"],
              ["Memory", "Operational"],
            ].map(([label, status]) => (
              <div
                key={label}
                className="flex items-center justify-between py-3 px-4 rounded-lg hover:bg-background-elevated transition-colors"
              >
                <span className="text-foreground-muted">{label}</span>
                <span className="text-foreground text-xs uppercase tracking-wider">
                  {status}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}