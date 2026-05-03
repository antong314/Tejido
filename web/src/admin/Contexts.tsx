import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { deleteContext, listContexts } from "./api";
import type { Context } from "./types";

// Context Library — reusable community-context blobs that sessions
// reference instead of pasting the same text per-session.
//
// Deleting a context that's currently referenced by a session is allowed:
// the runtime resolver falls back to "" (no community context), which is
// a valid session state. We intentionally don't block deletion or warn
// here — sessions without a context just produce slightly thinner
// synthesis output.

export function Contexts() {
  const [contexts, setContexts] = useState<Context[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function reload() {
    setRefreshing(true);
    setError(null);
    try {
      setContexts(await listContexts());
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Couldn't load contexts.",
      );
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await listContexts();
        if (!cancelled) setContexts(r);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? e.message : "Couldn't load contexts.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleDelete(c: Context) {
    const ok = window.confirm(
      `Delete context "${c.name}"?\n\nSessions referencing it will fall back to "no community context" — they'll still run, just without that grounding.`,
    );
    if (!ok) return;
    try {
      await deleteContext(c.id);
      reload();
    } catch (e) {
      alert(
        e instanceof ApiError ? e.message : "Could not delete context.",
      );
    }
  }

  return (
    <AdminLayout title="Context Library">
      <div className="mb-4 flex items-start justify-between gap-4">
        <p className="text-sm text-a-ink-muted">
          Reusable community-context blobs (shared values, prior decisions,
          named principles). Sessions reference one of these instead of
          pasting the same text into every session form. Used by the
          synthesis / proposal / revise output processors to ground the
          output in your community.
        </p>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={reload}
            disabled={refreshing}
            className="text-xs text-a-ink-muted hover:text-a-ink disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/admin/contexts/new")}
            className="rounded-md bg-a-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-a-accent-dark"
          >
            + New context
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-pill-private-bg p-3 text-sm text-pill-private">
          {error}
        </div>
      )}

      {contexts === null && !error && (
        <div className="text-sm text-a-ink-muted">Loading…</div>
      )}

      {contexts && contexts.length === 0 && (
        <div className="rounded-md border border-dashed border-a-border bg-a-bg-card p-8 text-center">
          <h2 className="text-base font-medium text-a-ink">
            No contexts yet
          </h2>
          <p className="mt-1 text-sm text-a-ink-muted">
            Create one for each community you facilitate. Sessions will
            pick from this library.
          </p>
          <button
            type="button"
            onClick={() => navigate("/admin/contexts/new")}
            className="mt-4 rounded-md bg-a-accent px-4 py-2 text-sm font-medium text-white hover:bg-a-accent-dark"
          >
            Create a context
          </button>
        </div>
      )}

      {contexts && contexts.length > 0 && (
        <div className="overflow-hidden rounded-md border border-a-border bg-a-bg-card">
          <ul className="divide-y divide-a-border">
            {contexts.map((c) => (
              <li
                key={c.id}
                className="flex cursor-pointer items-start justify-between gap-4 p-4 hover:bg-a-bg-subtle"
                onClick={() => navigate(`/admin/contexts/${c.id}`)}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-medium text-a-ink">
                      {c.name}
                    </div>
                    <code className="rounded bg-a-bg-subtle px-1.5 py-0.5 font-mono text-[10px] text-a-ink-muted">
                      {c.id}
                    </code>
                  </div>
                  <div className="mt-2 line-clamp-2 text-xs text-a-ink-muted">
                    {c.text}
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/admin/contexts/${c.id}`);
                    }}
                    className="rounded-md border border-a-border bg-a-bg-card px-3 py-1 text-xs text-a-ink hover:bg-a-bg-subtle"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(c);
                    }}
                    className="rounded-md border border-[oklch(80%_0.10_15)] bg-a-bg-card px-3 py-1 text-xs text-pill-private hover:bg-pill-private-bg"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </AdminLayout>
  );
}
