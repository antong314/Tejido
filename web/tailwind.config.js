/** @type {import('tailwindcss').Config} */
import typography from "@tailwindcss/typography";

// Design tokens — colors, radii, shadows, fonts, animations — defined as
// CSS custom properties in src/tejido-tokens.css and exposed here as
// Tailwind utility classes (e.g. bg-p-accent, rounded-pill, font-admin).
// Defining them in BOTH places keeps the runtime light and supports both
// className-driven and inline-style use.
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Participant palette — warm.
        "p-bg": "var(--p-bg)",
        "p-bg-card": "var(--p-bg-card)",
        "p-bg-subtle": "var(--p-bg-subtle)",
        "p-ink": "var(--p-ink)",
        "p-ink-muted": "var(--p-ink-muted)",
        "p-ink-faint": "var(--p-ink-faint)",
        "p-border": "var(--p-border)",
        "p-border-focus": "var(--p-border-focus)",
        "p-accent": "var(--p-accent)",
        "p-accent-dark": "var(--p-accent-dark)",
        "p-accent-tint": "var(--p-accent-tint)",
        "p-bubble-user": "var(--p-bubble-user)",
        "p-bubble-text": "var(--p-bubble-text)",

        // Admin palette — cool.
        "a-bg": "var(--a-bg)",
        "a-bg-card": "var(--a-bg-card)",
        "a-bg-subtle": "var(--a-bg-subtle)",
        "a-ink": "var(--a-ink)",
        "a-ink-muted": "var(--a-ink-muted)",
        "a-ink-faint": "var(--a-ink-faint)",
        "a-border": "var(--a-border)",
        "a-border-focus": "var(--a-border-focus)",
        "a-accent": "var(--a-accent)",
        "a-accent-dark": "var(--a-accent-dark)",
        "a-accent-tint": "var(--a-accent-tint)",

        // Status / permission pills.
        "pill-complete": "var(--pill-complete)",
        "pill-complete-bg": "var(--pill-complete-bg)",
        "pill-active": "var(--pill-active)",
        "pill-active-bg": "var(--pill-active-bg)",
        "pill-pending": "var(--pill-pending)",
        "pill-pending-bg": "var(--pill-pending-bg)",
        "pill-private": "var(--pill-private)",
        "pill-private-bg": "var(--pill-private-bg)",
      },

      borderRadius: {
        // Override Tailwind defaults to align with our token scale.
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        pill: "var(--radius-pill)",
      },

      boxShadow: {
        card: "var(--shadow-card)",
        modal: "var(--shadow-modal)",
        float: "var(--shadow-float)",
      },

      fontFamily: {
        "p-display": ["DM Serif Display", "serif"],
        participant: ["DM Sans", "system-ui", "sans-serif"],
        admin: ["Inter Tight", "system-ui", "sans-serif"],
        // Re-affirm a sensible mono stack so we can opt in via font-mono.
        mono: ["ui-monospace", "Cascadia Code", "Fira Mono", "monospace"],
      },

      keyframes: {
        tejidoBounce: {
          "0%, 80%, 100%": { transform: "translateY(0)", opacity: "0.4" },
          "40%": { transform: "translateY(-5px)", opacity: "1" },
        },
        tejidoFadeIn: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        tejidoModalIn: {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },

      animation: {
        // Three named instances for the typing dots so each can have its
        // own delay class.
        "bounce-dot-1": "tejidoBounce 1.2s 0ms ease-in-out infinite",
        "bounce-dot-2": "tejidoBounce 1.2s 150ms ease-in-out infinite",
        "bounce-dot-3": "tejidoBounce 1.2s 300ms ease-in-out infinite",
        "fade-in": "tejidoFadeIn 0.2s ease-out",
        "modal-in": "tejidoModalIn 0.15s ease-out",
      },
    },
  },
  // The `prose` family of classes from @tailwindcss/typography handles
  // markdown-rendered content (headings, paragraphs, lists, hr, quotes,
  // tables) with sensible defaults so we don't have to hand-style each
  // element from react-markdown's output.
  plugins: [typography],
};
