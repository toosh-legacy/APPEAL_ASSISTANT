/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { brand: { DEFAULT: "#1d4ed8", dark: "#1e3a8a", light: "#dbeafe" } },
    },
  },
  plugins: [],
};
