import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // LUCIA Design Tokens
        background: {
          DEFAULT: "hsl(var(--lucia-bg))",
          elevated: "hsl(var(--lucia-bg-elevated))",
          panel: "hsl(var(--lucia-bg-panel))",
        },
        foreground: {
          DEFAULT: "hsl(var(--lucia-fg))",
          muted: "hsl(var(--lucia-fg-muted))",
          subtle: "hsl(var(--lucia-fg-subtle))",
        },
        accent: {
          DEFAULT: "hsl(var(--lucia-accent))",
          glow: "hsl(var(--lucia-accent-glow))",
        },
        border: {
          DEFAULT: "hsl(var(--lucia-border))",
          strong: "hsl(var(--lucia-border-strong))",
        },
        status: {
          healthy: "hsl(var(--lucia-status-healthy))",
          warning: "hsl(var(--lucia-status-warning))",
          error: "hsl(var(--lucia-status-error))",
          cooldown: "hsl(var(--lucia-status-cooldown))",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "SF Mono", "monospace"],
      },
      fontSize: {
        "2xs": "0.6875rem",
      },
      animation: {
        "pulse-subtle": "pulse-subtle 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fade-in 0.4s ease-out",
        "fade-in-up": "fade-in-up 0.5s cubic-bezier(0.22, 1, 0.36, 1)",
        "cursor-blink": "cursor-blink 1.1s ease-in-out infinite",
        "activity-flow": "activity-flow 1.8s ease-in-out infinite",
      },
      keyframes: {
        "pulse-subtle": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "cursor-blink": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.2" },
        },
        "activity-flow": {
          "0%, 100%": { transform: "scaleX(0.3)", opacity: "0.4" },
          "50%": { transform: "scaleX(1)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;