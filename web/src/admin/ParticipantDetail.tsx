import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { getParticipant } from "./api";
import type { ParticipantDetail as DetailT } from "./types";

interface Props {
  sessionId: string;
  participantId: string;
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

const PERMISSION_BADGE: Record<
  "attributed" | "anonymous" | "private",
  { label: string; cls: string }
> = {
  attributed: {
    label: "By name",
    cls: "bg-emerald-100 text-emerald-800",
  },
  anonymous: {
    label: "Anonymous",
    cls: "bg-amber-100 text-amber-800",
  },
  private: {
    label: "Private",
    cls: "bg-red-100 text-red-800",
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
          className="text-xs text-neutral-600 hover:text-neutral-900"
        >
          ← back to session
        </a>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!data && !error && (
        <div className="text-sm text-neutral-500">Loading…</div>
      )}

      {data && (
        <div className="space-y-6">
          <header className="rounded-lg border border-neutral-200 bg-white p-5">
            <h1 className="text-lg font-semibold text-neutral-900">
              {data.participant_name}
            </h1>
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
              <Meta label="Phase">
                <span
                  className={
                    data.phase === "complete"
                      ? "rounded-full bg-green-100 px-2 py-0.5 text-green-800"
                      : "text-neutral-700"
                  }
                >
                  {PHASE_LABEL[data.phase] ?? data.phase}
                </span>
              </Meta>
              <Meta label="Status">{data.status || "—"}</Meta>
              <Meta label="Started">{fmtTime(data.started_at)}</Meta>
              <Meta label="Completed">{fmtTime(data.completed_at)}</Meta>
            </dl>
            <details className="mt-3 text-xs text-neutral-600">
              <summary className="cursor-pointer hover:text-neutral-900">
                Question shown to this participant
              </summary>
              <pre className="mt-2 whitespace-pre-wrap rounded bg-neutral-50 p-3 font-sans">
                {data.question}
              </pre>
            </details>
          </header>

          <section className="rounded-lg border border-neutral-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-neutral-900">
              Transcript
            </h2>
            {data.transcript.length === 0 ? (
              <div className="mt-3 text-sm text-neutral-500">
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

          <section className="rounded-lg border border-neutral-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-neutral-900">
              Extracted points ({data.extracted_points.length})
            </h2>
            <p className="mt-1 text-xs text-neutral-600">
              Each was reviewed by the participant during the permissions
              walk-through. The badge shows the choice they made.
            </p>
            {data.extracted_points.length === 0 ? (
              <div className="mt-3 text-sm text-neutral-500">
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
            <section className="rounded-lg border border-neutral-200 bg-white p-5">
              <h2 className="text-sm font-semibold text-neutral-900">
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

          <details className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-600">
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
      <dt className="font-medium uppercase tracking-wide text-neutral-500">
        {label}
      </dt>
      <dd className="mt-0.5 text-neutral-800">{children}</dd>
    </div>
  );
}

function Turn({ turn }: { turn: DetailT["transcript"][number] }) {
  const isUser = turn.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[85%]">
        <div className="mb-0.5 flex items-center gap-2 text-[10px] uppercase tracking-wide text-neutral-500">
          <span>{isUser ? "Participant" : "Facilitator"}</span>
          {turn.via === "voice" && (
            <span className="rounded-full bg-neutral-100 px-1.5 py-0.5">
              voice
            </span>
          )}
          {turn.detected_language && (
            <span className="rounded-full bg-neutral-100 px-1.5 py-0.5">
              {turn.detected_language}
            </span>
          )}
          {turn.timestamp && (
            <span className="font-mono">{fmtTime(turn.timestamp)}</span>
          )}
        </div>
        <div
          className={[
            "rounded-2xl px-4 py-3 text-[14px] leading-relaxed whitespace-pre-wrap",
            isUser
              ? "bg-neutral-900 text-white"
              : "bg-neutral-50 border border-neutral-200 text-neutral-800",
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
        <span className="shrink-0 pt-1 font-mono text-xs text-neutral-500">
          {prefix}
        </span>
      )}
      <div className="flex-1 text-sm text-neutral-800">{text}</div>
      <span
        className={
          (badge?.cls ?? "bg-neutral-100 text-neutral-600") +
          " shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
        }
      >
        {badge?.label ?? "unset"}
      </span>
    </li>
  );
}
