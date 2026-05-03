import { useState } from "react";
import { join, ApiError } from "../api";

interface Props {
  sessionId: string;
  onJoined: (participantId: string, displayName: string) => void;
}

// First screen every participant sees. Just a name + submit. The visual
// language sets the tone for the whole flow: warm, unhurried, generous
// whitespace, terracotta accent. The wordmark + rule above the headline
// is the brand mark — small but consistent across the participant
// surfaces.

export function NameEntry({ sessionId, onJoined }: Props) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [focused, setFocused] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Please enter a name.");
      return;
    }
    setSubmitting(true);
    try {
      const r = await join(sessionId, name.trim());
      onJoined(r.participant_id, r.display_name);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError("Couldn't reach the server. Try again?");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex h-full items-center justify-center bg-p-bg px-4">
      <div className="w-full max-w-[400px] rounded-xl border border-p-border bg-p-bg-card px-11 py-12 shadow-float">
        {/* Wordmark + terracotta rule. The same brand mark appears on
            every participant card. Small, calm, present. */}
        <div className="mb-9">
          <div className="font-p-display text-[22px] leading-none text-p-ink">
            tejido
          </div>
          <div className="mt-1 h-[2px] w-7 rounded-sm bg-p-accent" />
        </div>

        <h1 className="font-p-display text-[28px] font-normal leading-tight tracking-[-0.4px] text-p-ink">
          Before we begin —
        </h1>
        <p className="mt-2.5 mb-8 text-[14px] leading-[1.6] text-p-ink-muted">
          A private, AI-facilitated conversation. About 10 minutes. What you
          say is yours until you say otherwise.
        </p>

        <form onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-2 block text-[12px] font-medium uppercase tracking-[0.07em] text-p-ink-muted">
              What should we call you?
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              autoComplete="off"
              autoFocus
              disabled={submitting}
              className={[
                "block w-full rounded-md bg-p-bg px-3.5 py-2.5 text-[15px] text-p-ink",
                "border-[1.5px] outline-none transition-[border-color,box-shadow]",
                focused
                  ? "border-p-border-focus shadow-[0_0_0_3px_var(--p-accent-tint)]"
                  : "border-p-border",
                submitting && "opacity-50",
              ]
                .filter(Boolean)
                .join(" ")}
            />
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="mt-5 w-full rounded-md bg-p-accent px-4 py-3 text-[15px] font-medium text-white transition-colors hover:bg-p-accent-dark disabled:cursor-default disabled:opacity-50"
          >
            {submitting ? "Joining…" : "Begin"}
          </button>

          {error && (
            <div className="mt-3 rounded-sm bg-pill-private-bg px-3 py-2.5 text-[13px] text-pill-private">
              {error}
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
