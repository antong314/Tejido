import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { TelegramCard } from "./TelegramCard";
import { listSessions, listWorkflowTypes } from "./api";
import type { AdminSession, WorkflowSchema } from "./types";

export function SessionList() {
  const [sessions, setSessions] = useState<AdminSession[] | null>(null);
  const [types, setTypes] = useState<WorkflowSchema[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Tracked here (not just in TelegramCard) so we can put a 🤖 badge on
  // the bound row in the table below.
  const [boundTelegramId, setBoundTelegramId] = useState<string | null>(null);
  const handleBindingChange = useCallback(
    (id: string | null) => setBoundTelegramId(id),
    [],
  );

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
        <div className="mb-4 rounded-md bg-pill-private-bg p-3 text-[13px] text-pill-private">
          {error}
        </div>
      )}

      {sessions !== null && sessions.length > 0 && (
        <TelegramCard
          sessions={sessions}
          onBindingChange={handleBindingChange}
        />
      )}

      {sessions === null && !error && (
        <div className="text-[13px] text-a-ink-muted">Loading…</div>
      )}

      {sessions && sessions.length === 0 && (
        <div className="rounded-md border border-dashed border-a-border bg-a-bg-card p-8 text-center">
          <h2 className="text-[15px] font-medium text-a-ink">
            No sessions yet
          </h2>
          <p className="mt-1 text-[13px] text-a-ink-muted">
            Create your first one to get a participant URL you can share.
          </p>
          <button
            type="button"
            onClick={() => navigate("/admin/sessions/new")}
            className="mt-4 rounded-sm bg-a-accent px-4 py-2 text-[12px] font-medium text-white transition-colors hover:bg-a-accent-dark"
          >
            Create a workflow
          </button>
        </div>
      )}

      {sessions && sessions.length > 0 && (
        <div className="overflow-hidden rounded-md border border-a-border bg-a-bg-card shadow-card">
          <table className="min-w-full text-[13px]">
            <thead>
              <tr className="bg-a-bg-subtle">
                {["Title", "Workflow", "Participant URL", ""].map((h) => (
                  <th
                    key={h}
                    className="border-b border-a-border px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-[0.07em] text-a-ink-faint"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sessions.map((s, i) => {
                const url = `${window.location.origin}/s/${s.id}`;
                return (
                  <tr
                    key={s.id}
                    className={[
                      "transition-colors hover:bg-a-bg-subtle",
                      i < sessions.length - 1 ? "border-b border-a-border" : "",
                    ].join(" ")}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="font-medium text-a-ink">
                          {s.title || s.id}
                        </div>
                        {boundTelegramId === s.id && (
                          <span
                            title="Telegram bot is bound to this session"
                            className="rounded-sm bg-[oklch(93%_0.04_220)] px-1.5 py-0.5 text-[10px] font-semibold text-[oklch(45%_0.14_220)]"
                          >
                            🤖 Telegram
                          </span>
                        )}
                      </div>
                      <div className="font-mono text-[11px] text-a-ink-faint">
                        {s.id}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-a-ink-muted">
                      {typeLabel(s.workflow_type)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        title={url}
                        onClick={async () => {
                          await navigator.clipboard.writeText(url);
                        }}
                        className="text-[12px] text-a-ink-muted transition-colors hover:text-a-ink"
                      >
                        copy URL
                      </button>
                      <a
                        href={`/s/${s.id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-3 text-[12px] text-a-ink-muted transition-colors hover:text-a-ink"
                      >
                        open ↗
                      </a>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => navigate(`/admin/sessions/${s.id}`)}
                        className="rounded-sm border border-a-border bg-a-bg-card px-3 py-1 text-[11px] font-medium text-a-ink transition-colors hover:bg-a-bg-subtle"
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
