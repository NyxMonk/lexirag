import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// Indic fallbacks: Windows ships Nirmala UI, macOS ships the Devanagari/Bangla/Gurmukhi Sangam fonts.
const indic = [
  "Nirmala UI",
  "Kohinoor Devanagari",
  "Devanagari Sangam MN",
  "Bangla Sangam MN",
  "Gurmukhi Sangam MN",
  "Noto Sans Devanagari",
  "Noto Sans Bengali",
  "Noto Sans Gurmukhi",
];

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "2rem" },
    extend: {
      fontFamily: {
        // The LexiIndic faces (src/fonts.css) only cover Indic code points, so Latin text still uses the brand fonts.
        sans: ["LexiIndic Sans", "Inter Variable", "Inter", "system-ui", ...indic, "sans-serif"],
        serif: ["LexiIndic Serif", "Newsreader Variable", "Georgia", ...indic, "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        surface: "hsl(var(--surface))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        subtle: "0 1px 2px 0 rgb(0 0 0 / 0.04)",
        lifted: "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 4px 16px -4px rgb(0 0 0 / 0.08)",
      },
      letterSpacing: {
        label: "0.08em",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
