/** @type {import('tailwindcss').Config} */
import typography from "@tailwindcss/typography";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {},
  },
  // The `prose` family of classes from @tailwindcss/typography handles
  // markdown-rendered content (headings, paragraphs, lists, hr, quotes,
  // tables) with sensible defaults so we don't have to hand-style each
  // element from react-markdown's output.
  plugins: [typography],
};
