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
          purple: '#6B21A8',
          pink: '#DB2777',
          light: '#F3E8FF',
        },
      },
    },
  },
  plugins: [],
}
