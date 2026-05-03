import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ApiError } from "../api";
import { outputUrl } from "./api";

// Modal viewer for a synthesis / proposal / revise output. Fetches the
// markdown content over the same `/api/admin/sessions/{id}/outputs/{name}`
// route used for the "open in new tab" link, then renders it via
// react-markdown + remark-gfm. Wrapped in Tailwind's `prose` for typography.

interface Props {
  sessionId: string;
  filename: string;
  onClose: () => void;
}

export function OutputViewer({ sessionId, filename, onClose }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Fetch the file content as text (the raw markdown — react-markdown
  // does the rendering client-side, which keeps the API surface unchanged).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(outputUrl(sessionId, filename));
        if (!r.ok) {
          throw new ApiError(
            r.status,
            "fetch_failed",
            `Couldn't load ${filename}`,
          );
        }
        const text = await r.text();
        if (!cancelled) setContent(text);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "Couldn't load file.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, filename]);

  // Close on Escape and click-outside. Focus-trapping is intentionally
  // skipped — this is admin-only and short-lived; no need to wire a
  // dependency for it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleCopy() {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
    } catch {
      /* clipboard blocked — silently no-op; "Open ↗" gives them a fallback */
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[oklch(20%_0.01_260/0.4)] p-4"
      onClick={(e) => {
        // Click on the backdrop (not the dialog itself) closes.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="flex h-full max-h-[90vh] w-full max-w-[680px] animate-modal-in flex-col overflow-hidden rounded-lg border border-a-border bg-a-bg-card shadow-modal"
      >
        <header className="flex items-center justify-between gap-4 border-b border-a-border px-5 py-3">
          <div className="min-w-0">
            <div className="truncate font-mono text-[12px] text-a-ink-muted">
              {filename}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              disabled={!content}
              className="rounded-sm border border-a-border bg-a-bg-card px-3 py-1.5 text-[11px] font-medium text-a-ink transition-colors hover:bg-a-bg-subtle disabled:opacity-50"
            >
              Copy markdown
            </button>
            <a
              href={outputUrl(sessionId, filename)}
              target="_blank"
              rel="noreferrer"
              className="rounded-sm border border-a-border bg-a-bg-card px-3 py-1.5 text-[11px] font-medium text-a-ink transition-colors hover:bg-a-bg-subtle"
            >
              Open raw ↗
            </a>
            <button
              type="button"
              onClick={onClose}
              className="rounded-sm bg-a-accent px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-a-accent-dark"
            >
              Close
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-a-bg-subtle px-9 py-7">
          {error && (
            <div className="rounded-md bg-pill-private-bg p-3 text-[13px] text-pill-private">
              {error}
            </div>
          )}
          {!error && content === null && (
            <div className="text-[13px] text-a-ink-muted">Loading…</div>
          )}
          {content !== null && (
            <article
              // Custom typography for the synthesis/proposal/revise output.
              // h1 is DM Serif Display (matches the brand), h2 is Inter
              // Tight uppercase to read like section labels in a report.
              className={[
                "prose prose-sm prose-neutral max-w-none text-a-ink",
                "prose-h1:font-p-display prose-h1:text-[24px] prose-h1:font-normal prose-h1:tracking-[-0.3px] prose-h1:leading-tight prose-h1:mb-5 prose-h1:mt-0",
                "prose-h2:font-admin prose-h2:text-[14px] prose-h2:font-semibold prose-h2:uppercase prose-h2:tracking-[0.07em] prose-h2:mb-2 prose-h2:mt-6",
                "prose-h3:text-[14px] prose-h3:font-semibold prose-h3:mb-2 prose-h3:mt-5",
                "prose-p:text-[14px] prose-p:leading-[1.75] prose-p:my-3.5",
                "prose-li:text-[14px] prose-li:leading-[1.7] prose-li:my-1.5",
                "prose-strong:text-a-ink",
                "prose-hr:border-a-border prose-hr:my-5",
              ].join(" ")}
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </article>
          )}
        </div>
      </div>
    </div>
  );
}
