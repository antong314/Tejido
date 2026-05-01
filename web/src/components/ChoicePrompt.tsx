import { useState } from "react";
import { sendCallback, ApiError } from "../api";
import type { Choice } from "../types";

interface Props {
  participantId: string;
  text: string;
  choices: Choice[];
  resolved: boolean;
  resolvedText: string | null;
}

export function ChoicePrompt({
  participantId,
  text,
  choices,
  resolved,
  resolvedText,
}: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick(callback_data: string) {
    setSubmitting(true);
    setError(null);
    try {
      await sendCallback(participantId, callback_data);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Couldn't send your choice. Try again?");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-2">
      <div
        className="whitespace-pre-wrap text-sm text-neutral-800"
        dangerouslySetInnerHTML={{
          __html: renderInlineMarkup(resolved ? resolvedText ?? text : text),
        }}
      />
      {!resolved && (
        <div className="flex flex-wrap gap-2 pt-1">
          {choices.map((c) => (
            <button
              key={c.callback_data}
              type="button"
              disabled={submitting}
              onClick={() => handleClick(c.callback_data)}
              className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-800 hover:bg-neutral-50 disabled:opacity-50"
            >
              {c.label}
            </button>
          ))}
        </div>
      )}
      {error && (
        <div className="text-xs text-red-600">{error}</div>
      )}
    </div>
  );
}

// The backend uses a sliver of HTML — only <b>, <i>, and the **bold**
// shorthand we added on the frontend's reconstructed prompts. Render
// these explicitly; everything else stays as text.
function renderInlineMarkup(s: string): string {
  return escapeHtml(s)
    .replace(/&lt;b&gt;(.+?)&lt;\/b&gt;/g, "<strong>$1</strong>")
    .replace(/&lt;i&gt;(.+?)&lt;\/i&gt;/g, "<em>$1</em>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
