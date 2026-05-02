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
        <p className="text-sm text-neutral-600">
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
            className="text-xs text-neutral-500 hover:text-neutral-900 disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/admin/contexts/new")}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-800"
          >
            + New context
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {contexts === null && !error && (
        <div className="text-sm text-neutral-500">Loading…</div>
      )}

      {contexts && contexts.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-8 text-center">
          <h2 className="text-base font-medium text-neutral-900">
            No contexts yet
          </h2>
          <p className="mt-1 text-sm text-neutral-600">
            Create one for each community you facilitate. Sessions will
            pick from this library.
          </p>
          <button
            type="button"
            onClick={() => navigate("/admin/contexts/new")}
            className="mt-4 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
          >
            Create a context
          </button>
        </div>
      )}

      {contexts && contexts.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
          <ul className="divide-y divide-neutral-200">
            {contexts.map((c) => (
              <li
                key={c.id}
                className="flex cursor-pointer items-start justify-between gap-4 p-4 hover:bg-neutral-50"
                onClick={() => navigate(`/admin/contexts/${c.id}`)}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-medium text-neutral-900">
                      {c.name}
                    </div>
                    <code className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-600">
                      {c.id}
                    </code>
                  </div>
                  <div className="mt-2 line-clamp-2 text-xs text-neutral-500">
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
                    className="rounded-md border border-neutral-300 bg-white px-3 py-1 text-xs text-neutral-800 hover:bg-neutral-50"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(c);
                    }}
                    className="rounded-md border border-red-300 bg-white px-3 py-1 text-xs text-red-700 hover:bg-red-50"
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
