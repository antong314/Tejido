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

// Visual treatment per permission choice. Detected by the callback_data
// suffix so this works for both per-point (perm:N:attributed) and
// addition-permission (addperm:attributed) callbacks. By name = sage
// green; Anonymous = amber; Private = muted red. Each carries a small
// glyph so the choices read at a glance without color alone.
type PermissionVariant = "attributed" | "anonymous" | "private";

const PERMISSION_VISUALS: Record<
  PermissionVariant,
  { glyph: string; classes: string }
> = {
  attributed: {
    glyph: "●",
    classes:
      "border-pill-complete bg-pill-complete-bg text-pill-complete hover:bg-[oklch(89%_0.05_155)]",
  },
  anonymous: {
    glyph: "◐",
    classes:
      "border-pill-pending bg-pill-pending-bg text-pill-pending hover:bg-[oklch(90%_0.05_80)]",
  },
  private: {
    glyph: "○",
    classes:
      "border-pill-private bg-pill-private-bg text-pill-private hover:bg-[oklch(91%_0.04_15)]",
  },
};

function permissionVariantOf(callback_data: string): PermissionVariant | null {
  if (
    callback_data.startsWith("perm:") ||
    callback_data.startsWith("addperm:")
  ) {
    if (callback_data.endsWith(":attributed")) return "attributed";
    if (callback_data.endsWith(":anonymous")) return "anonymous";
    if (callback_data.endsWith(":private")) return "private";
  }
  return null;
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
  // begin") — render as a pill terracotta button.
  // Multi-choice with permission semantics — render as the three big
  // color-coded option buttons in a row.
  // Other multi-choice (yes/no) — neutral pill buttons.
  const isPrimaryCta = !resolved && choices.length === 1;
  const isPermissionGroup =
    !resolved &&
    choices.length === 3 &&
    choices.every((c) => permissionVariantOf(c.callback_data) !== null);

  // Render the resolved-state text directly without surrounding chrome.
  // For a question_callout-style display (the "I'm ready" prompt), we
  // intentionally skip rendering an empty text div so the button sits
  // alone without an empty leading paragraph.
  const displayText = resolved ? resolvedText ?? text : text;
  const hasText = displayText && displayText.trim().length > 0;

  return (
    <div className="space-y-4">
      {hasText && (
        <div
          className="whitespace-pre-wrap"
          dangerouslySetInnerHTML={{
            __html: renderInlineMarkup(displayText, parseMode === "html"),
          }}
        />
      )}

      {!resolved && isPrimaryCta && (
        <div className="pt-2">
          {choices.map((c) => (
            <button
              key={c.callback_data}
              type="button"
              disabled={submitting}
              onClick={() => handleClick(c.callback_data)}
              className="rounded-pill bg-p-accent px-7 py-3 text-[14px] font-medium text-white shadow-sm transition-all hover:bg-p-accent-dark active:scale-[0.98] disabled:cursor-default disabled:opacity-50"
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {!resolved && !isPrimaryCta && isPermissionGroup && (
        <div className="flex gap-2 pt-1">
          {choices.map((c) => {
            const v = permissionVariantOf(c.callback_data)!;
            const visual = PERMISSION_VISUALS[v];
            return (
              <button
                key={c.callback_data}
                type="button"
                disabled={submitting}
                onClick={() => handleClick(c.callback_data)}
                className={[
                  "flex flex-1 flex-col items-center gap-1 rounded-md border-[1.5px] px-2 py-3 text-[13px] font-medium",
                  "transition-all active:scale-[0.97] disabled:cursor-default disabled:opacity-50",
                  visual.classes,
                ].join(" ")}
              >
                <span className="text-[16px] leading-none">{visual.glyph}</span>
                <span>{c.label}</span>
              </button>
            );
          })}
        </div>
      )}

      {!resolved && !isPrimaryCta && !isPermissionGroup && (
        // Generic multi-choice (yes/no, etc.) — neutral pills, equal weight.
        <div className="flex flex-wrap gap-2 pt-1">
          {choices.map((c) => (
            <button
              key={c.callback_data}
              type="button"
              disabled={submitting}
              onClick={() => handleClick(c.callback_data)}
              className="rounded-pill border-[1.5px] border-p-border bg-p-bg-card px-4 py-2 text-[13px] font-medium text-p-ink transition-all hover:border-p-border-focus active:scale-[0.97] disabled:cursor-default disabled:opacity-50"
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {error && <div className="text-xs text-pill-private">{error}</div>}
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
