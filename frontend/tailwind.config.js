/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/**/*.{js,jsx,ts,tsx,vue,html}',
    '../templates/**/*.html',
    '../static/js/**/*.js'
  ],
  theme: {
    extend: {}
  },
  plugins: []
};
