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
    <div className="mb-6 rounded-lg border border-neutral-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">
            Telegram bot
          </h2>
          <p className="mt-1 text-xs text-neutral-600">
            One session at a time. Telegram has a single bot token, so all
            incoming Telegram messages get routed to the chosen session
            until you change it here. The setting persists across restarts.
          </p>
        </div>
        <div className="shrink-0 text-right text-xs">
          <div className="uppercase tracking-wide text-neutral-500">
            Currently
          </div>
          <div className="mt-0.5 font-medium text-neutral-900">
            {bound ? (
              <>
                <span className="mr-1">🤖</span>
                {boundSession?.title || bound}
              </>
            ) : (
              <span className="text-neutral-500">unbound</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <select
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={saving}
          className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:bg-neutral-100"
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
          className="rounded-md bg-neutral-900 px-3 py-2 text-xs font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
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
        <div className="mt-2 rounded-md bg-red-50 p-2 text-xs text-red-700">
          {saveError}
        </div>
      )}
    </div>
  );
}
