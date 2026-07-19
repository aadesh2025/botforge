import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const rgb = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: rgb("--bg"),
        surface: {
          DEFAULT: rgb("--surface"),
          2: rgb("--surface-2"),
          3: rgb("--surface-3"),
        },
        border: {
          DEFAULT: rgb("--border"),
          strong: rgb("--border-strong"),
        },
        text: rgb("--text"),
        muted: rgb("--muted"),
        faint: rgb("--faint"),
        ember: {
          DEFAULT: rgb("--ember"),
          2: rgb("--ember-2"),
          soft: rgb("--ember-soft"),
        },
        success: rgb("--success"),
        warn: rgb("--warn"),
        error: rgb("--error"),
        info: rgb("--info"),
        ring: rgb("--ring"),
      },
      fontFamily: {
        sans: ["var(--font-body)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.3), 0 1px 3px 0 rgb(0 0 0 / 0.2)",
        pop: "0 12px 32px -8px rgb(0 0 0 / 0.6), 0 2px 8px -2px rgb(0 0 0 / 0.4)",
        "ember-glow": "0 0 0 1px rgb(var(--ember) / 0.4), 0 8px 24px -8px rgb(var(--ember) / 0.35)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "caret-blink": {
          "0%,70%,100%": { opacity: "1" },
          "20%,50%": { opacity: "0.2" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
        "caret-blink": "caret-blink 1.1s ease-in-out infinite",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
export default config;
