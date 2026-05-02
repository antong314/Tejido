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
      className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-900/40 p-4"
      onClick={(e) => {
        // Click on the backdrop (not the dialog itself) closes.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="flex h-full max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-neutral-300 bg-white shadow-xl"
      >
        <header className="flex items-center justify-between gap-4 border-b border-neutral-200 px-5 py-3">
          <div className="min-w-0">
            <div className="truncate font-mono text-xs text-neutral-600">
              {filename}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              disabled={!content}
              className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs text-neutral-800 hover:bg-neutral-50 disabled:opacity-50"
            >
              Copy markdown
            </button>
            <a
              href={outputUrl(sessionId, filename)}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs text-neutral-800 hover:bg-neutral-50"
            >
              Open raw ↗
            </a>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-800"
            >
              Close
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-neutral-50 px-6 py-5">
          {error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          {!error && content === null && (
            <div className="text-sm text-neutral-500">Loading…</div>
          )}
          {content !== null && (
            <article className="prose prose-sm prose-neutral max-w-none prose-headings:mb-3 prose-headings:mt-6 prose-headings:font-semibold prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-p:my-3 prose-li:my-1 prose-hr:my-6">
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
