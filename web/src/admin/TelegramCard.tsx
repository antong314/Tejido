import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { getTelegramStatus, setTelegramBinding } from "./api";
import type { AdminSession, TelegramStatus } from "./types";

interface Props {
  // The same list of sessions the surrounding page already loaded —
  // passed in so we don't re-fetch.
  sessions: AdminSession[];
  // Bubble the current binding up so the parent can badge the matching
  // session row. null = unbound, undefined = not yet loaded.
  onBindingChange?: (boundSessionId: string | null) => void;
}

// Single-source-of-truth control for which session the Telegram bot is
// pointed at. Only one binding is possible per process (Telegram has one
// bot token / one poller); this card is where you switch it.
//
// If the running process doesn't own a TelegramManager (e.g. someone
// started `circle.web` instead of `circle.run`), the backend reports
// available: false and we hide the card entirely.

export function TelegramCard({ sessions, onBindingChange }: Props) {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await getTelegramStatus();
        if (cancelled) return;
        setStatus(r);
        setDraft(r.bound_session_id ?? "");
        onBindingChange?.(r.bound_session_id);
      } catch (e) {
        if (cancelled) return;
        setLoadError(
          e instanceof ApiError ? e.message : "Couldn't reach the server.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onBindingChange]);

  if (loadError) {
    return (
      <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
        {loadError}
      </div>
    );
  }

  // Either still loading, or this process doesn't run Telegram. In the
  // latter case the card has nothing useful to show — hide it.
  if (status === null) return null;
  if (!status.available) return null;

  const dirty = (status.bound_session_id ?? "") !== draft;

  async function handleApply() {
    setSaveError(null);
    setSaving(true);
    try {
      const next = await setTelegramBinding(draft || null);
      setStatus(next);
      setDraft(next.bound_session_id ?? "");
      onBindingChange?.(next.bound_session_id);
    } catch (e) {
      setSaveError(
        e instanceof ApiError ? e.message : "Could not update binding.",
      );
    } finally {
      setSaving(false);
    }
  }

  const bound = status.bound_session_id;
  const boundSession = bound ? sessions.find((s) => s.id === bound) : null;

  return (
    <div className="mb-4 rounded-md border border-a-border bg-a-bg-card px-5 py-4 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[13px] font-semibold text-a-ink">
            Telegram bot
          </h2>
          <p className="mt-1 text-[12px] leading-[1.55] text-a-ink-muted">
            One session at a time. Telegram has a single bot token, so all
            incoming Telegram messages get routed to the chosen session
            until you change it here. The setting persists across restarts.
          </p>
        </div>
        <div className="shrink-0 text-right text-[11px]">
          <div className="font-semibold uppercase tracking-[0.07em] text-a-ink-faint">
            Currently
          </div>
          <div className="mt-1 text-[13px] font-medium text-a-ink">
            {bound ? (
              <>
                <span className="mr-1">🤖</span>
                {boundSession?.title || bound}
              </>
            ) : (
              <span className="text-a-ink-faint">unbound</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <select
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={saving}
          className="flex-1 rounded-sm border border-a-border bg-a-bg-card px-3 py-2 text-[13px] text-a-ink outline-none focus:border-a-border-focus disabled:bg-a-bg-subtle"
        >
          <option value="">— Unbound (Telegram off) —</option>
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title || s.id} ({s.id})
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleApply}
          disabled={saving || !dirty}
          className="rounded-sm bg-a-accent px-4 py-2 text-[12px] font-medium text-white transition-colors hover:bg-a-accent-dark disabled:cursor-default disabled:opacity-50"
        >
          {saving
            ? "Applying…"
            : dirty
              ? draft
                ? "Bind"
                : "Unbind"
              : "Applied"}
        </button>
      </div>

      {saveError && (
        <div className="mt-2 rounded-sm bg-pill-private-bg p-2 text-[12px] text-pill-private">
          {saveError}
        </div>
      )}
    </div>
  );
}
