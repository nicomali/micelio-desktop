/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        santander: {
          red: '#EC0000',
          dark: '#990000',
          soft: '#FF3B3B',
        },
      },
    },
  },
  plugins: [],
};
