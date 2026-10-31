import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        border: "hsl(var(--border))",
        surface: "#1C1C1C",
        elevated: "#242424",
        gold: {
          300: "#D8C08D",
          400: "#C6A76B",
          500: "#B5965C",
          600: "#92784D",
        },
        bronze: "#92784D",
        slate: {
          50: "#171717",
          100: "#151515",
          200: "#33302A",
          300: "#454137",
          400: "#625D53",
          500: "#817B71",
          600: "#A6A29A",
          700: "#C3BFB5",
          800: "#DDD9D0",
          900: "#F5F2EB",
        },
        emerald: {
          50: "#18221C",
          200: "#2C4637",
          700: "#C6A76B",
          800: "#91B49A",
          900: "#B8D1BE",
          950: "#D5E5D8",
        },
        amber: {
          50: "#282319",
          200: "#4B4129",
          800: "#C9AE73",
          900: "#D9C38F",
          950: "#E9D9AF",
        },
        rose: {
          50: "#281C1D",
          200: "#503537",
          800: "#C9878B",
          900: "#DDA4A7",
        },
        blue: {
          50: "#1E2226",
          800: "#A6B5C0",
          900: "#C1CBD2",
        },
      },
    },
  },
  plugins: [],
};

export default config;
