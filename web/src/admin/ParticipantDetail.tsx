import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { getParticipant } from "./api";
import { PhasePill } from "./PhasePill";
import type { ParticipantDetail as DetailT } from "./types";

interface Props {
  sessionId: string;
  participantId: string;
}

const PERMISSION_BADGE: Record<
  "attributed" | "anonymous" | "private",
  { label: string; bg: string; color: string }
> = {
  attributed: {
    label: "By name",
    bg: "bg-pill-complete-bg",
    color: "text-pill-complete",
  },
  anonymous: {
    label: "Anonymous",
    bg: "bg-pill-pending-bg",
    color: "text-pill-pending",
  },
  private: {
    label: "Private",
    bg: "bg-pill-private-bg",
    color: "text-pill-private",
  },
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function ParticipantDetail({ sessionId, participantId }: Props) {
  const [data, setData] = useState<DetailT | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await getParticipant(sessionId, participantId);
        if (!cancelled) setData(r);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? e.message : "Couldn't load participant.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, participantId]);

  return (
    <AdminLayout title={data?.participant_name ?? "Participant"}>
      <div className="mb-4">
        <a
          href={`/admin/sessions/${sessionId}`}
          onClick={(e) => {
            e.preventDefault();
            navigate(`/admin/sessions/${sessionId}`);
          }}
          className="text-[12px] text-a-ink-muted transition-colors hover:text-a-ink"
        >
          ← back to session
        </a>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-pill-private-bg p-3 text-[13px] text-pill-private">
          {error}
        </div>
      )}

      {!data && !error && (
        <div className="text-[13px] text-a-ink-muted">Loading…</div>
      )}

      {data && (
        <div className="space-y-4">
          {/* Sensitive content notice. The participant chose what to
              share with the group via the permissions walk-through;
              this admin view shows the FULL transcript regardless.
              Reading it without need is a small breach of the trust
              contract — flag the weight before they scroll. */}
          <div className="rounded-sm border border-[oklch(88%_0.05_260)] bg-[oklch(97%_0.01_260)] px-3.5 py-2.5 text-[12px] leading-[1.5] text-a-ink-muted">
            <strong className="text-a-ink">Private transcript.</strong>{" "}
            This is what the participant said in their private
            conversation. Open this only with their awareness.
          </div>

          <header className="rounded-md border border-a-border bg-a-bg-card px-5 py-4 shadow-card">
            <h1 className="font-p-display text-[22px] font-normal leading-tight text-a-ink">
              {data.participant_name}
            </h1>
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-[12px] sm:grid-cols-4">
              <Meta label="Phase">
                <PhasePill phase={data.phase} />
              </Meta>
              <Meta label="Status">{data.status || "—"}</Meta>
              <Meta label="Started">{fmtTime(data.started_at)}</Meta>
              <Meta label="Completed">{fmtTime(data.completed_at)}</Meta>
            </dl>
            <details className="mt-3 text-[12px] text-a-ink-muted">
              <summary className="cursor-pointer transition-colors hover:text-a-ink">
                Question shown to this participant
              </summary>
              <pre className="mt-2 whitespace-pre-wrap rounded-sm bg-a-bg-subtle p-3 font-sans text-[12px] leading-[1.55] text-a-ink">
                {data.question}
              </pre>
            </details>
          </header>

          <section className="rounded-md border border-a-border bg-a-bg-card px-5 py-4 shadow-card">
            <h2 className="text-[13px] font-semibold text-a-ink">
              Transcript
            </h2>
            {data.transcript.length === 0 ? (
              <div className="mt-3 text-[13px] text-a-ink-muted">
                No turns recorded.
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                {data.transcript.map((turn, i) => (
                  <Turn key={i} turn={turn} />
                ))}
              </div>
            )}
          </section>

          <section className="rounded-md border border-a-border bg-a-bg-card px-5 py-4 shadow-card">
            <h2 className="text-[13px] font-semibold text-a-ink">
              Extracted points ({data.extracted_points.length})
            </h2>
            <p className="mt-1 text-[12px] text-a-ink-muted">
              Each was reviewed by the participant during the
              permissions walk-through. The badge shows the choice they
              made.
            </p>
            {data.extracted_points.length === 0 ? (
              <div className="mt-3 text-[13px] text-a-ink-muted">
                No points extracted yet.
              </div>
            ) : (
              <ul className="mt-4 space-y-2">
                {data.extracted_points.map((p) => (
                  <PermissionedItem
                    key={p.index}
                    text={p.point}
                    permission={p.permission}
                    prefix={`${p.index + 1}.`}
                  />
                ))}
              </ul>
            )}
          </section>

          {data.additions.length > 0 && (
            <section className="rounded-md border border-a-border bg-a-bg-card px-5 py-4 shadow-card">
              <h2 className="text-[13px] font-semibold text-a-ink">
                Additions ({data.additions.length})
              </h2>
              <ul className="mt-4 space-y-2">
                {data.additions.map((a, i) => (
                  <PermissionedItem
                    key={i}
                    text={a.content}
                    permission={a.permission}
                  />
                ))}
              </ul>
            </section>
          )}

          <details className="rounded-sm border border-a-border bg-a-bg-subtle p-3 text-[11px] text-a-ink-muted">
            <summary className="cursor-pointer">
              Internal — participant_id (storage key)
            </summary>
            <code className="mt-1 block break-all font-mono">
              {data.participant_id}
            </code>
          </details>
        </div>
      )}
    </AdminLayout>
  );
}

function Meta({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-[10px] font-semibold uppercase tracking-[0.07em] text-a-ink-faint">
        {label}
      </dt>
      <dd className="mt-1 text-[12px] text-a-ink">{children}</dd>
    </div>
  );
}

function Turn({ turn }: { turn: DetailT["transcript"][number] }) {
  const isUser = turn.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[85%]">
        <div className="mb-1 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.05em] text-a-ink-faint">
          <span>{isUser ? "Participant" : "Facilitator"}</span>
          {turn.via === "voice" && (
            <span className="rounded-sm bg-a-bg-subtle px-1.5 py-0.5">
              voice
            </span>
          )}
          {turn.detected_language && (
            <span className="rounded-sm bg-a-bg-subtle px-1.5 py-0.5">
              {turn.detected_language}
            </span>
          )}
          {turn.timestamp && (
            <span className="font-mono normal-case tracking-normal">
              {fmtTime(turn.timestamp)}
            </span>
          )}
        </div>
        <div
          className={[
            "whitespace-pre-wrap px-3.5 py-2.5 text-[13px] leading-[1.65]",
            isUser
              ? "rounded-[16px_16px_4px_16px] bg-a-ink text-white"
              : "rounded-[4px_16px_16px_16px] border border-a-border bg-a-bg-subtle text-a-ink",
          ].join(" ")}
        >
          {turn.content}
        </div>
      </div>
    </div>
  );
}

function PermissionedItem({
  text,
  permission,
  prefix,
}: {
  text: string;
  permission: "attributed" | "anonymous" | "private" | null;
  prefix?: string;
}) {
  const badge = permission ? PERMISSION_BADGE[permission] : null;
  return (
    <li className="flex items-start gap-3">
      {prefix && (
        <span className="shrink-0 pt-0.5 font-mono text-[11px] text-a-ink-faint">
          {prefix}
        </span>
      )}
      <div className="flex-1 text-[13px] leading-[1.55] text-a-ink">
        {text}
      </div>
      <span
        className={[
          "shrink-0 rounded-pill px-2 py-0.5 text-[10px] font-semibold tracking-[0.03em]",
          badge ? `${badge.bg} ${badge.color}` : "bg-a-bg-subtle text-a-ink-muted",
        ].join(" ")}
      >
        {badge?.label ?? "unset"}
      </span>
    </li>
  );
}
