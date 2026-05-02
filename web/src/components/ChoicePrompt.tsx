import { useState } from "react";
import { sendCallback, ApiError } from "../api";
import type { Choice, ParseMode } from "../types";

interface Props {
  sessionId: string;
  participantId: string;
  text: string;
  parseMode: ParseMode;
  choices: Choice[];
  resolved: boolean;
  resolvedText: string | null;
}

export function ChoicePrompt({
  sessionId,
  participantId,
  text,
  parseMode,
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
      await sendCallback(sessionId, participantId, callback_data);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Couldn't send your choice. Try again?");
    } finally {
      setSubmitting(false);
    }
  }

  // Single-choice prompts feel like a primary CTA (e.g. "I'm ready, let's
  // begin") — render them with weight. Multi-choice prompts are framed
  // as choices, so the buttons are equal-weight pills.
  const isPrimaryCta = !resolved && choices.length === 1;

  return (
    <div className="space-y-4">
      <div
        className="whitespace-pre-wrap"
        dangerouslySetInnerHTML={{
          __html: renderInlineMarkup(
            resolved ? resolvedText ?? text : text,
            parseMode === "html",
          ),
        }}
      />
      {!resolved && (
        <div
          className={
            isPrimaryCta ? "pt-2" : "flex flex-wrap gap-2 pt-1"
          }
        >
          {choices.map((c) =>
            isPrimaryCta ? (
              <button
                key={c.callback_data}
                type="button"
                disabled={submitting}
                onClick={() => handleClick(c.callback_data)}
                className="rounded-full bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-neutral-800 disabled:opacity-50"
              >
                {c.label}
              </button>
            ) : (
              <button
                key={c.callback_data}
                type="button"
                disabled={submitting}
                onClick={() => handleClick(c.callback_data)}
                className="rounded-full border border-neutral-300 bg-white px-3.5 py-1.5 text-sm text-neutral-800 hover:border-neutral-400 hover:bg-neutral-50 disabled:opacity-50"
              >
                {c.label}
              </button>
            ),
          )}
        </div>
      )}
      {error && <div className="text-xs text-red-600">{error}</div>}
    </div>
  );
}

function renderInlineMarkup(s: string, allowHtml: boolean): string {
  if (allowHtml) {
    const escaped = s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    // Note the `s` (dotAll) flag — `<b>...</b>` can span newlines.
    return escaped
      .replace(/&lt;b&gt;(.+?)&lt;\/b&gt;/gs, "<strong>$1</strong>")
      .replace(/&lt;i&gt;(.+?)&lt;\/i&gt;/gs, "<em>$1</em>");
  }
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
