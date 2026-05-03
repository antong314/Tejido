import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { listParticipants } from "./api";
import { PhasePill } from "./PhasePill";
import type { ParticipantSummary } from "./types";

interface Props {
  sessionId: string;
}

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
    <div className="rounded-md border border-a-border bg-a-bg-card p-5 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[13px] font-semibold text-a-ink">
            Participants
          </h2>
          <p className="mt-1 text-[12px] text-a-ink-muted">
            Click a row to view that participant's transcript and
            permission choices.
          </p>
        </div>
        <button
          type="button"
          onClick={reload}
          disabled={refreshing}
          className="text-[11px] text-a-accent transition-colors hover:text-a-accent-dark disabled:opacity-50"
        >
          {refreshing ? "Refreshing…" : "Refresh ↺"}
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-sm bg-pill-private-bg p-3 text-[13px] text-pill-private">
          {error}
        </div>
      )}

      {list === null && !error && (
        <div className="mt-3 text-[13px] text-a-ink-muted">Loading…</div>
      )}

      {list && list.length === 0 && (
        <div className="mt-3 text-[13px] text-a-ink-muted">
          Nobody has joined yet.
        </div>
      )}

      {list && list.length > 0 && (
        <div className="mt-4 overflow-hidden rounded-md border border-a-border">
          <table className="min-w-full text-[12px]">
            <thead>
              <tr className="bg-a-bg-subtle">
                {[
                  ["Name", "left"],
                  ["Phase", "left"],
                  ["Joined", "left"],
                  ["Total time", "right"],
                  ["Turns", "right"],
                  ["Words", "right"],
                  ["Points / Adds", "right"],
                ].map(([h, align]) => (
                  <th
                    key={h}
                    className={[
                      "border-b border-a-border px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.07em] text-a-ink-faint",
                      align === "right" ? "text-right" : "text-left",
                    ].join(" ")}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.map((p, i) => (
                <tr
                  key={p.participant_id}
                  onClick={() =>
                    navigate(
                      `/admin/sessions/${sessionId}/participants/${p.participant_id}`,
                    )
                  }
                  className={[
                    "cursor-pointer transition-colors hover:bg-a-bg-subtle",
                    i < list.length - 1 ? "border-b border-a-border" : "",
                  ].join(" ")}
                >
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-a-ink">
                      {p.participant_name}
                    </div>
                    <div className="font-mono text-[10px] text-a-ink-faint">
                      {p.participant_id.slice(0, 8)}…
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <PhasePill phase={p.phase} />
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-a-ink-muted">
                    {fmtTime(p.started_at)}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-[11px] text-a-ink-muted">
                    {fmtDuration(p.started_at, p.completed_at)}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-[11px] text-a-ink-muted">
                    {p.num_turns}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-[11px] text-a-ink-muted">
                    {p.participant_word_count.toLocaleString()}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-[11px] text-a-ink-muted">
                    {p.num_extracted_points} / {p.num_additions}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
