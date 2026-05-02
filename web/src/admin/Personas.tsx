import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { deletePersona, listPersonas } from "./api";
import type { Persona } from "./types";

// Personas list — managed independently of any session. The "+ New persona"
// button drops you into PersonaEdit; clicking a row does the same. Delete is
// allowed even for personas referenced by a session: the runtime falls back
// to the workflow default if a referenced id no longer resolves.

export function Personas() {
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function reload() {
    setRefreshing(true);
    setError(null);
    try {
      setPersonas(await listPersonas());
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Couldn't load personas.",
      );
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await listPersonas();
        if (!cancelled) setPersonas(r);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? e.message : "Couldn't load personas.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleDelete(p: Persona) {
    const ok = window.confirm(
      `Delete persona "${p.name}"?\n\nSessions referencing it will fall back to the workflow default.`,
    );
    if (!ok) return;
    try {
      await deletePersona(p.id);
      reload();
    } catch (e) {
      alert(
        e instanceof ApiError
          ? e.message
          : "Could not delete persona.",
      );
    }
  }

  return (
    <AdminLayout title="Personas">
      <div className="mb-4 flex items-start justify-between gap-4">
        <p className="text-sm text-neutral-600">
          Reusable facilitator voices. A session picks one of these (or
          inherits its workflow's default). Editing a persona affects every
          session referencing it on the next conversation turn.
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
            onClick={() => navigate("/admin/personas/new")}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-800"
          >
            + New persona
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {personas === null && !error && (
        <div className="text-sm text-neutral-500">Loading…</div>
      )}

      {personas && personas.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-8 text-center">
          <h2 className="text-base font-medium text-neutral-900">
            No personas yet
          </h2>
          <p className="mt-1 text-sm text-neutral-600">
            Personas are usually seeded automatically. Create one to get
            going.
          </p>
          <button
            type="button"
            onClick={() => navigate("/admin/personas/new")}
            className="mt-4 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
          >
            Create a persona
          </button>
        </div>
      )}

      {personas && personas.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
          <ul className="divide-y divide-neutral-200">
            {personas.map((p) => (
              <li
                key={p.id}
                className="flex cursor-pointer items-start justify-between gap-4 p-4 hover:bg-neutral-50"
                onClick={() => navigate(`/admin/personas/${p.id}`)}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-medium text-neutral-900">
                      {p.name}
                    </div>
                    <code className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-600">
                      {p.id}
                    </code>
                  </div>
                  {p.description && (
                    <div className="mt-0.5 text-xs text-neutral-600">
                      {p.description}
                    </div>
                  )}
                  <div className="mt-2 line-clamp-2 text-xs text-neutral-500">
                    {p.prompt}
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/admin/personas/${p.id}`);
                    }}
                    className="rounded-md border border-neutral-300 bg-white px-3 py-1 text-xs text-neutral-800 hover:bg-neutral-50"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(p);
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
