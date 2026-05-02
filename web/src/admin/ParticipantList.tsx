import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { listParticipants } from "./api";
import type { ParticipantSummary } from "./types";

interface Props {
  sessionId: string;
}

const PHASE_LABEL: Record<string, string> = {
  not_started: "not started",
  awaiting_consent: "awaiting consent",
  in_conversation: "in conversation",
  in_permissions: "in permissions",
  awaiting_addition: "awaiting addition",
  in_addition_permissions: "addition permissions",
  complete: "complete",
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (Number.isNaN(s) || Number.isNaN(e)) return "—";
  const mins = Math.max(0, Math.round((e - s) / 60000));
  return mins < 1 ? "<1 min" : `${mins} min`;
}

export function ParticipantList({ sessionId }: Props) {
  const [list, setList] = useState<ParticipantSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function reload() {
    setRefreshing(true);
    setError(null);
    try {
      setList(await listParticipants(sessionId));
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Couldn't load participants.",
      );
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await listParticipants(sessionId);
        if (!cancelled) setList(r);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? e.message : "Couldn't load participants.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">
            Participants
          </h2>
          <p className="mt-1 text-xs text-neutral-600">
            Click a row to view that participant's transcript and
            permission choices.
          </p>
        </div>
        <button
          type="button"
          onClick={reload}
          disabled={refreshing}
          className="text-xs text-neutral-500 hover:text-neutral-900 disabled:opacity-50"
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {list === null && !error && (
        <div className="mt-3 text-sm text-neutral-500">Loading…</div>
      )}

      {list && list.length === 0 && (
        <div className="mt-3 text-sm text-neutral-500">
          Nobody has joined yet.
        </div>
      )}

      {list && list.length > 0 && (
        <div className="mt-4 overflow-hidden rounded-md border border-neutral-200">
          <table className="min-w-full divide-y divide-neutral-200 text-sm">
            <thead className="bg-neutral-50 text-left text-xs font-medium uppercase tracking-wide text-neutral-500">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Phase</th>
                <th className="px-3 py-2">Joined</th>
                <th className="px-3 py-2 text-right">Total time</th>
                <th className="px-3 py-2 text-right">Turns</th>
                <th className="px-3 py-2 text-right">Points / Adds</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200">
              {list.map((p) => {
                const isComplete = p.phase === "complete";
                return (
                  <tr
                    key={p.participant_id}
                    onClick={() =>
                      navigate(
                        `/admin/sessions/${sessionId}/participants/${p.participant_id}`,
                      )
                    }
                    className="cursor-pointer hover:bg-neutral-50"
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium text-neutral-900">
                        {p.participant_name}
                      </div>
                      <div className="font-mono text-xs text-neutral-500">
                        {p.participant_id.slice(0, 8)}…
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          isComplete
                            ? "rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800"
                            : "text-xs text-neutral-700"
                        }
                      >
                        {PHASE_LABEL[p.phase] ?? p.phase}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-neutral-600">
                      {fmtTime(p.started_at)}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-neutral-600">
                      {fmtDuration(p.started_at, p.completed_at)}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-neutral-600">
                      {p.num_turns}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-neutral-600">
                      {p.num_extracted_points} / {p.num_additions}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
