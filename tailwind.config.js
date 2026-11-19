/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./frontend/**/*.{html,js}"],
  theme: {
    extend: {
      colors: {
        // Brand accent: #52E4A0. Dark text is used on 300/400 fills so
        // primary buttons stay readable in both themes.
        primary: {
          50: "#e9fdf4",
          100: "#c9fbe6",
          200: "#96f5d1",
          300: "#63eaba",
          400: "#52E4A0",
          500: "#2ecf87",
          600: "#19a96a",
          700: "#148456",
          800: "#126947",
          900: "#10553b",
          950: "#062e20",
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
      },
      maxWidth: {
        app: "64rem",
      },
    },
  },
  plugins: [],
};
