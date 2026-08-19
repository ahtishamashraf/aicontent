import type { Config } from "tailwindcss";

/**
 * A calm, restrained palette. Score colours are chosen so that their text
 * pairing clears WCAG 2.2 AA (4.5:1) on the surfaces they are used with, and so
 * that the three bands remain distinguishable without relying on hue alone —
 * every band is also labelled in words.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#15181d",
          soft: "#3d434e",
          muted: "#5c6472",
        },
        surface: {
          DEFAULT: "#ffffff",
          sunken: "#f6f7f9",
          raised: "#ffffff",
        },
        line: {
          DEFAULT: "#dfe3e8",
          strong: "#c3cad3",
        },
        brand: {
          DEFAULT: "#1f5f8b",
          hover: "#194e73",
          soft: "#eaf2f8",
        },
        // Band colours. Deliberately not red/green: the result is not a verdict.
        band: {
          human: "#2f6b4f",
          humanSoft: "#e8f2ec",
          uncertain: "#8a6412",
          uncertainSoft: "#fbf2df",
          ai: "#8c4a2f",
          aiSoft: "#fbeee8",
        },
        danger: {
          DEFAULT: "#a4262c",
          soft: "#fdecec",
        },
        success: {
          DEFAULT: "#2f6b4f",
          soft: "#e8f2ec",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      borderRadius: {
        card: "0.875rem",
        pill: "1.25rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(21, 24, 29, 0.04), 0 8px 24px -12px rgba(21, 24, 29, 0.12)",
        focus: "0 0 0 3px rgba(31, 95, 139, 0.35)",
      },
      maxWidth: {
        prose: "68ch",
      },
    },
  },
  plugins: [],
};

export default config;
