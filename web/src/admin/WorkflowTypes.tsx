import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { listWorkflowTypes } from "./api";
import type { WorkflowSchema } from "./types";

// Workflow types are code-defined (their field schemas + processor
// mappings have runtime implications) but their three editable prompt
// fragments — task framing, output template, mechanics — live as
// admin-managed JSON overrides. This page is the entry point: it lists
// the (small, fixed) set of workflow types and shows whether each has
// any active overrides. Click through to /admin/workflows/<type> to edit.

export function WorkflowTypes() {
  const [workflows, setWorkflows] = useState<WorkflowSchema[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await listWorkflowTypes();
        if (!cancelled) setWorkflows(r);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError
            ? e.message
            : "Couldn't load workflow types.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AdminLayout title="Workflows">
      <p className="mb-4 text-sm text-a-ink-muted">
        Each workflow type ships with a built-in task framing (the "what
        kind of conversation" wrapper), output template (the post-
        conversation processor prompt), and conversation mechanics. Any
        of those can be overridden per workflow. Sessions inherit the
        active values; an empty override falls back to the default.
      </p>

      {error && (
        <div className="mb-4 rounded-md bg-pill-private-bg p-3 text-sm text-pill-private">
          {error}
        </div>
      )}

      {workflows === null && !error && (
        <div className="text-sm text-a-ink-muted">Loading…</div>
      )}

      {workflows && workflows.length > 0 && (
        <ul className="space-y-3">
          {workflows.map((w) => {
            const overrideCount = countOverrides(w);
            return (
              <li
                key={w.type}
                className="cursor-pointer rounded-md border border-a-border bg-a-bg-card p-5 hover:border-a-border-focus hover:shadow-sm"
                onClick={() => navigate(`/admin/workflows/${w.type}`)}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-semibold text-a-ink">
                        {w.label}
                      </h3>
                      <code className="rounded bg-a-bg-subtle px-1.5 py-0.5 font-mono text-[10px] text-a-ink-muted">
                        {w.type}
                      </code>
                      {overrideCount > 0 && (
                        <span
                          title="This workflow has admin-edited prompt overrides"
                          className="rounded-pill bg-pill-pending-bg px-2 py-0.5 text-[10px] font-medium text-pill-pending"
                        >
                          {overrideCount} edited
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-a-ink-muted">
                      {w.description}
                    </p>
                    <p className="mt-2 text-xs text-a-ink-muted">
                      Output processor: <code>{w.processor}</code> ·{" "}
                      Field count: {w.fields.length}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/admin/workflows/${w.type}`);
                    }}
                    className="shrink-0 rounded-md border border-a-border bg-a-bg-card px-3 py-1.5 text-xs text-a-ink hover:bg-a-bg-subtle"
                  >
                    Edit
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </AdminLayout>
  );
}

function countOverrides(w: WorkflowSchema): number {
  let n = 0;
  if (w.task_framing_override.trim()) n += 1;
  if (w.output_template_override.trim()) n += 1;
  if (w.mechanics_override.trim()) n += 1;
  return n;
}
