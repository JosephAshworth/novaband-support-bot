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
          dark: '#15803D',
          light: '#DCFCE7',
        },
      },
    },
  },
  plugins: [],
}
