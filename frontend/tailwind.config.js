/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        novaband: {
          green: '#16A34A',
          mid: '#22C55E',
          dark: '#166534',
          mint: '#BBF7D0',
          light: '#DCFCE7',
        },
      },
    },
  },
  plugins: [],
}
