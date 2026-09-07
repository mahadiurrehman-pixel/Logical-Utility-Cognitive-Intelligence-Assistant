import { cn } from "@/lib/utils/cn";

interface Props {
  className?: string;
  size?: "sm" | "md" | "lg";
  withLabel?: boolean;
}

export function LuciaMark({ className, size = "md", withLabel = true }: Props) {
  const orbSizes = {
    sm: "h-3.5 w-3.5",
    md: "h-5 w-5",
    lg: "h-8 w-8",
  };

  const fontSizes = {
    sm: "text-xs tracking-[0.2em]",
    md: "text-sm tracking-[0.25em]",
    lg: "text-xl tracking-[0.3em]",
  };

  return (
    <div className={cn("inline-flex items-center gap-3 select-none", className)}>
      <div className={cn("relative flex items-center justify-center", orbSizes[size])}>
        {/* Outer subtle radar ring */}
        <div className="absolute inset-0 rounded-full border border-accent/30 animate-pulse-subtle" />
        
        {/* Glowing halo */}
        <div className="absolute inset-1 rounded-full bg-accent/20 blur-[2px]" />
        
        {/* Core quantum node */}
        <div className="relative h-2 w-2 rounded-full bg-accent shadow-[0_0_8px_#38bdf8]" />
      </div>

      {withLabel && (
        <span className={cn("font-medium text-foreground font-sans", fontSizes[size])}>
          LUCIA
        </span>
      )}
    </div>
  );
}