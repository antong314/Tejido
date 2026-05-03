import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { OutputViewer } from "./OutputViewer";
import { ParticipantList } from "./ParticipantList";
import {
  SessionForm,
  valueFromSession,
  type SessionFormValue,
} from "./SessionForm";
import {
  deleteSession,
  getSession,
  listOutputs,
  listWorkflowTypes,
  outputUrl,
  runProcessor,
  updateSession,
} from "./api";
import type {
  AdminSession,
  OutputFileEntry,
  WorkflowSchema,
} from "./types";

interface Props {
  sessionId: string;
}

export function EditSession({ sessionId }: Props) {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [schema, setSchema] = useState<WorkflowSchema | null>(null);
  const [outputs, setOutputs] = useState<OutputFileEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  // Filename of the output the user is currently viewing in the modal,
  // or null when the modal is closed.
  const [viewerFilename, setViewerFilename] = useState<string | null>(null);

  // Polling handle for the post-Run "watch outputs dir for the new file"
  // loop. Held in a ref so unmount can cancel it cleanly.
  const pollHandleRef = useRef<number | null>(null);

  function stopPolling() {
    if (pollHandleRef.current !== null) {
      window.clearInterval(pollHandleRef.current);
      pollHandleRef.current = null;
    }
  }

  // Cancel any in-flight poll if the user navigates away mid-run.
  useEffect(() => {
    return () => stopPolling();
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, types, outs] = await Promise.all([
          getSession(sessionId),
          listWorkflowTypes(),
          listOutputs(sessionId),
        ]);
        if (cancelled) return;
        setSession(s);
        setSchema(types.find((t) => t.type === s.workflow_type) ?? null);
        setOutputs(outs);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? e.message : "Couldn't load session.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  async function handleSubmit(value: SessionFormValue) {
    setServerError(null);
    setStatusMsg(null);
    try {
      const updated = await updateSession(sessionId, {
        title: value.title,
        common: value.common,
        workflow_data: value.workflow_data,
      });
      setSession(updated);
      setStatusMsg("Saved.");
      setTimeout(() => setStatusMsg(null), 2500);
    } catch (e) {
      setServerError(
        e instanceof ApiError ? e.message : "Could not save.",
      );
    }
  }

  async function handleDelete() {
    const ok = window.confirm(
      `Delete session "${sessionId}"? Past participant data under data/${sessionId}/ stays on disk.`,
    );
    if (!ok) return;
    try {
      await deleteSession(sessionId);
      navigate("/admin");
    } catch (e) {
      setServerError(
        e instanceof ApiError ? e.message : "Could not delete.",
      );
    }
  }

  async function handleRun() {
    if (!schema) return;
    setServerError(null);
    setStatusMsg(null);
    stopPolling();

    // Snapshot the current output filenames so we can detect the new one
    // when it lands. Comparing filenames (not list length) handles the
    // edge case where another tab triggered a run in parallel.
    const knownBefore = new Set(outputs.map((o) => o.filename));

    setRunning(true);
    try {
      await runProcessor(sessionId, schema.processor);
    } catch (e) {
      setRunning(false);
      setServerError(e instanceof ApiError ? e.message : "Run failed.");
      return;
    }
    setStatusMsg(
      `Running ${schema.processor}… the output will appear below as soon as it lands.`,
    );

    // Poll the outputs endpoint until a new file appears or we hit the
    // timeout. 3-second cadence is fine — the run is admin-only and a
    // typical synthesis takes 15-60s. Opus on a big bylaws session can
    // push past two minutes; 5 minutes leaves comfortable headroom.
    const POLL_MS = 3000;
    const TIMEOUT_MS = 5 * 60 * 1000;
    const startedAt = Date.now();

    pollHandleRef.current = window.setInterval(async () => {
      let fresh: OutputFileEntry[] = [];
      try {
        fresh = await listOutputs(sessionId);
      } catch {
        // Transient — try again on the next tick.
        return;
      }
      const newOnes = fresh.filter((o) => !knownBefore.has(o.filename));
      if (newOnes.length > 0) {
        stopPolling();
        setOutputs(fresh);
        setRunning(false);
        setStatusMsg(
          `Done — ${schema.processor} produced ${newOnes[0].filename}.`,
        );
        window.setTimeout(() => setStatusMsg(null), 6000);
        return;
      }
      if (Date.now() - startedAt > TIMEOUT_MS) {
        stopPolling();
        setRunning(false);
        setStatusMsg(
          `${schema.processor} is taking longer than 5 minutes. ` +
            `Check the server log; refresh this page to pick it up when it lands.`,
        );
      }
    }, POLL_MS);
  }

  return (
    <AdminLayout title={session?.title ?? sessionId}>
      {error && (
        <div className="mb-4 rounded-md bg-pill-private-bg p-3 text-[13px] text-pill-private">
          {error}
        </div>
      )}

      {!session && !error && (
        <div className="text-[13px] text-a-ink-muted">Loading…</div>
      )}

      {session && schema && (
        <div className="space-y-4">
          <div className="rounded-md border border-a-border bg-a-bg-card px-5 py-4 shadow-card">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-[13px] font-semibold text-a-ink">
                  Participant URL
                </h2>
                <div className="mt-1 break-all font-mono text-[13px] tracking-[-0.2px] text-a-ink">
                  {window.location.origin}/s/{session.id}
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={() =>
                    navigator.clipboard.writeText(
                      `${window.location.origin}/s/${session.id}`,
                    )
                  }
                  className="rounded-sm border border-a-border bg-a-bg-card px-3 py-1.5 text-[11px] font-medium text-a-ink transition-colors hover:bg-a-bg-subtle"
                >
                  Copy
                </button>
                <a
                  href={`/s/${session.id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-sm border border-a-border bg-a-bg-card px-3 py-1.5 text-[11px] font-medium text-a-ink transition-colors hover:bg-a-bg-subtle"
                >
                  Open ↗
                </a>
              </div>
            </div>
          </div>

          <ParticipantList sessionId={sessionId} />

          <div className="rounded-md border border-a-border bg-a-bg-card px-5 py-4 shadow-card">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-[13px] font-semibold text-a-ink">
                  Run {schema.processor}
                </h2>
                <p className="mt-1 text-[12px] leading-[1.5] text-a-ink-muted">
                  Generates the {schema.processor} output for every
                  participant who has reached{" "}
                  <code className="rounded-sm bg-a-bg-subtle px-1 py-0.5 font-mono text-[11px]">
                    complete
                  </code>
                  .
                </p>
              </div>
              <button
                type="button"
                onClick={handleRun}
                disabled={running}
                className="shrink-0 rounded-sm bg-a-accent px-4 py-2 text-[12px] font-medium text-white transition-colors hover:bg-a-accent-dark disabled:cursor-default disabled:opacity-50"
              >
                {running ? "Running…" : `Run ${schema.processor}`}
              </button>
            </div>

            {outputs.length > 0 && (
              <div className="mt-4 border-t border-a-border pt-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.07em] text-a-ink-faint">
                  Past outputs
                </div>
                <ul>
                  {outputs.map((o, i) => (
                    <li
                      key={o.filename}
                      className={[
                        "flex items-center justify-between gap-3 py-1.5",
                        i < outputs.length - 1
                          ? "border-b border-a-border"
                          : "",
                      ].join(" ")}
                    >
                      <button
                        type="button"
                        onClick={() => setViewerFilename(o.filename)}
                        className="truncate text-left font-mono text-[12px] text-a-accent transition-colors hover:text-a-accent-dark"
                        title="View rendered markdown"
                      >
                        {o.filename}
                      </button>
                      <div className="flex shrink-0 items-center gap-3">
                        <span className="text-[11px] text-a-ink-faint">
                          {(o.bytes / 1024).toFixed(1)} kB
                        </span>
                        <a
                          href={outputUrl(session.id, o.filename)}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-a-ink-faint transition-colors hover:text-a-ink"
                          title="Open the raw .md file in a new tab"
                        >
                          raw ↗
                        </a>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {statusMsg && (
            <div className="rounded-md bg-pill-complete-bg p-3 text-[13px] text-pill-complete">
              {statusMsg}
            </div>
          )}

          <SessionForm
            schema={schema}
            initial={valueFromSession(session)}
            allowEditId={false}
            submitLabel="Save changes"
            onSubmit={handleSubmit}
            serverError={serverError}
          />

          <div className="rounded-md border border-[oklch(85%_0.06_15)] bg-[oklch(99%_0.01_15)] px-5 py-4">
            <h3 className="text-[13px] font-semibold text-pill-private">
              Danger zone
            </h3>
            <p className="mt-1 text-[12px] leading-[1.5] text-pill-private/80">
              Deleting only removes the session config. Participant data
              under{" "}
              <code className="rounded-sm bg-[oklch(96%_0.02_15)] px-1 py-0.5 font-mono text-[11px]">
                data/{session.id}/
              </code>{" "}
              stays on disk so you can still run the processors against
              it later.
            </p>
            <button
              type="button"
              onClick={handleDelete}
              className="mt-3 rounded-sm border border-[oklch(80%_0.10_15)] bg-a-bg-card px-3 py-1.5 text-[12px] font-medium text-pill-private transition-colors hover:bg-pill-private-bg"
            >
              Delete session
            </button>
          </div>
        </div>
      )}

      {viewerFilename && (
        <OutputViewer
          sessionId={sessionId}
          filename={viewerFilename}
          onClose={() => setViewerFilename(null)}
        />
      )}
    </AdminLayout>
  );
}
