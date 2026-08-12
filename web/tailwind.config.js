/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    borderRadius: {
      none: "0px",
      DEFAULT: "0px",
      full: "9999px",
    },
    extend: {
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        accent: "var(--accent)",
        crit: "var(--crit)",
        high: "var(--high)",
        med: "var(--med)",
        low: "var(--low)",
        ok: "var(--ok)",
        bad: "var(--bad)",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Inter",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          '"SF Mono"',
          "Menlo",
          "monospace",
        ],
      },
      boxShadow: {
        none: "none",
      },
    },
  },
  plugins: [],
};
