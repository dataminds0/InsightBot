/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#F5F8FA",
        surface: "#FFFFFF",
        text: "#172C3C",
        muted: "#506474",
        brand: {
          DEFAULT: "#0B6C70",
          hover: "#09575A",
          light: "#E6F4F5",
        },
        border: "#D2DCE3",
        positive: "#24734D",
        negative: "#AD3548",
        warning: "#8D5D0C",
        focus: "#006FD6",
      },
      fontFamily: {
        sans: ['"Noto Sans Arabic"', "system-ui", "-apple-system", "sans-serif"],
      },
      lineHeight: {
        reader: "1.8",
      },
    },
  },
  plugins: [],
};
