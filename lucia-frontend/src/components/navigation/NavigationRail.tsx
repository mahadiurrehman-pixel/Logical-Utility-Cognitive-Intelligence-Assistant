"use client";

import { useState } from "react";
import {
  MessageSquarePlus,
  MessagesSquare,
  Search,
  Wrench,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";

interface NavItem {
  id: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick?: () => void;
}

interface Props {
  onNewChat?: () => void;
  onOpenSearch?: () => void;
  onOpenTools?: () => void;
  onOpenSettings?: () => void;
}

export function NavigationRail({ onNewChat, onOpenSearch, onOpenTools, onOpenSettings }: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const items: NavItem[] = [
    { id: "new", icon: MessageSquarePlus, label: "New conversation", onClick: onNewChat },
    { id: "search", icon: Search, label: "Search", onClick: onOpenSearch },
    { id: "tools", icon: Wrench, label: "Tools", onClick: onOpenTools },
    { id: "settings", icon: Settings, label: "Settings", onClick: onOpenSettings },
  ];

  return (
    <aside className="fixed left-0 top-0 h-screen w-14 md:w-[60px] border-r border-border bg-background-elevated flex flex-col items-center py-4 z-40">
      <div className="mb-6">
        <div className="relative flex items-center justify-center h-8 w-8">
          <div className="h-2 w-2 rounded-full bg-accent" />
          <div className="absolute h-6 w-6 rounded-full border border-accent/30 animate-pulse-subtle" />
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.id}
              onMouseEnter={() => setHoveredId(item.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={item.onClick}
              className={cn(
                "relative group flex items-center justify-center h-10 w-10 rounded-lg cursor-pointer transition-all duration-200",
                "text-foreground-subtle hover:text-foreground hover:bg-background-panel"
              )}
            >
              <Icon className="h-4 w-4" />

              {hoveredId === item.id && (
                <div className="absolute left-full ml-3 whitespace-nowrap px-2.5 py-1 text-xs bg-background-panel border border-border rounded-md pointer-events-none animate-fade-in z-50">
                  {item.label}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="mt-auto">
        <div className="h-1.5 w-1.5 rounded-full bg-status-healthy" />
      </div>
    </aside>
  );
}