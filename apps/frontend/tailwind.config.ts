import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        surface: "var(--surface)",
        border: "var(--border)",
        bullish: "#22c55e",
        bearish: "#ef4444",
        accent: "#3b82f6",
      },
    },
  },
  plugins: [],
};

export default config;
