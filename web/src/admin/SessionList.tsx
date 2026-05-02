import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { listSessions, listWorkflowTypes } from "./api";
import type { AdminSession, WorkflowSchema } from "./types";

export function SessionList() {
  const [sessions, setSessions] = useState<AdminSession[] | null>(null);
  const [types, setTypes] = useState<WorkflowSchema[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, t] = await Promise.all([listSessions(), listWorkflowTypes()]);
        if (cancelled) return;
        setSessions(s);
        setTypes(t);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? e.message : "Couldn't reach the server.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const typeLabel = (t: string) => types.find((x) => x.type === t)?.label ?? t;

  return (
    <AdminLayout title="Sessions">
      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {sessions === null && !error && (
        <div className="text-sm text-neutral-500">Loading…</div>
      )}

      {sessions && sessions.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-8 text-center">
          <h2 className="text-base font-medium text-neutral-900">
            No sessions yet
          </h2>
          <p className="mt-1 text-sm text-neutral-600">
            Create your first one to get a participant URL you can share.
          </p>
          <button
            type="button"
            onClick={() => navigate("/admin/sessions/new")}
            className="mt-4 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
          >
            Create a workflow
          </button>
        </div>
      )}

      {sessions && sessions.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
          <table className="min-w-full divide-y divide-neutral-200 text-sm">
            <thead className="bg-neutral-50 text-left text-xs font-medium uppercase tracking-wide text-neutral-500">
              <tr>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Workflow</th>
                <th className="px-4 py-3">Participant URL</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200">
              {sessions.map((s) => {
                const url = `${window.location.origin}/s/${s.id}`;
                return (
                  <tr key={s.id} className="hover:bg-neutral-50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-neutral-900">
                        {s.title || s.id}
                      </div>
                      <div className="text-xs text-neutral-500">{s.id}</div>
                    </td>
                    <td className="px-4 py-3 text-neutral-700">
                      {typeLabel(s.workflow_type)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        title={url}
                        onClick={async () => {
                          await navigator.clipboard.writeText(url);
                        }}
                        className="text-xs text-neutral-600 hover:text-neutral-900"
                      >
                        copy URL
                      </button>
                      <a
                        href={`/s/${s.id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-3 text-xs text-neutral-600 hover:text-neutral-900"
                      >
                        open ↗
                      </a>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() =>
                          navigate(`/admin/sessions/${s.id}`)
                        }
                        className="rounded-md border border-neutral-300 bg-white px-3 py-1 text-xs text-neutral-800 hover:bg-neutral-50"
                      >
                        Manage
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </AdminLayout>
  );
}
