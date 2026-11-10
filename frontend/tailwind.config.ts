import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#1c2433", soft: "#4a5568", faint: "#7b8494" },
        paper: { DEFAULT: "#f6f4ef", card: "#ffffff", line: "#e3dfd5" },
        brand: { DEFAULT: "#1f3a5f", dark: "#162a45", tint: "#e8eef6" },
        accent: "#9a6b1f",
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", "Times New Roman", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
