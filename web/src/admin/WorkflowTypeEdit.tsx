import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { getWorkflowType, updateWorkflowType } from "./api";
import type { WorkflowSchema } from "./types";

interface Props {
  workflowType: string;
}

// Three editable prompt fragments per workflow type. Each textarea shows
// the current override (or the default as placeholder if no override).
// Save sends a PATCH with whichever fields changed; "Reset to default"
// clears the override (PATCH with empty string).

interface FieldDraft {
  override: string;  // what the user has typed
  initial: string;   // what was last saved to the server
}

const SLOTS_HINT_OUTPUT = (
  "Available variables: {QUESTION}, {TRANSCRIPTS}, {COMMUNITY_CONTEXT}. "
  + "(For document_revision the question slot is the framing + document.)"
);

export function WorkflowTypeEdit({ workflowType }: Props) {
  const [schema, setSchema] = useState<WorkflowSchema | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // One draft per editable fragment.
  const [taskFraming, setTaskFraming] = useState<FieldDraft>({ override: "", initial: "" });
  const [outputTemplate, setOutputTemplate] = useState<FieldDraft>({ override: "", initial: "" });
  const [mechanics, setMechanics] = useState<FieldDraft>({ override: "", initial: "" });

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const w = await getWorkflowType(workflowType);
        if (cancelled) return;
        setSchema(w);
        setTaskFraming({
          override: w.task_framing_override,
          initial: w.task_framing_override,
        });
        setOutputTemplate({
          override: w.output_template_override,
          initial: w.output_template_override,
        });
        setMechanics({
          override: w.mechanics_override,
          initial: w.mechanics_override,
        });
      } catch (e) {
        if (cancelled) return;
        setLoadError(
          e instanceof ApiError ? e.message : "Couldn't load this workflow.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workflowType]);

  if (loadError) {
    return (
      <AdminLayout title="Workflows">
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {loadError}
        </div>
      </AdminLayout>
    );
  }

  if (!schema) {
    return (
      <AdminLayout title="Workflows">
        <div className="text-sm text-neutral-500">Loading…</div>
      </AdminLayout>
    );
  }

  const dirty =
    taskFraming.override !== taskFraming.initial ||
    outputTemplate.override !== outputTemplate.initial ||
    mechanics.override !== mechanics.initial;

  async function handleSave() {
    setSaveError(null);
    setSaving(true);
    try {
      // Only send the fields the user actually changed.
      const body: Record<string, string> = {};
      if (taskFraming.override !== taskFraming.initial)
        body.task_framing = taskFraming.override;
      if (outputTemplate.override !== outputTemplate.initial)
        body.output_template = outputTemplate.override;
      if (mechanics.override !== mechanics.initial)
        body.mechanics_override = mechanics.override;

      const updated = await updateWorkflowType(workflowType, body);
      setSchema(updated);
      setTaskFraming({
        override: updated.task_framing_override,
        initial: updated.task_framing_override,
      });
      setOutputTemplate({
        override: updated.output_template_override,
        initial: updated.output_template_override,
      });
      setMechanics({
        override: updated.mechanics_override,
        initial: updated.mechanics_override,
      });
      setStatusMsg("Saved.");
      window.setTimeout(() => setStatusMsg(null), 2500);
    } catch (e) {
      setSaveError(
        e instanceof ApiError ? e.message : "Could not save changes.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminLayout title={schema.label}>
      <div className="mb-4">
        <a
          href="/admin/workflows"
          onClick={(e) => {
            e.preventDefault();
            navigate("/admin/workflows");
          }}
          className="text-xs text-neutral-600 hover:text-neutral-900"
        >
          ← back to workflows
        </a>
      </div>

      <div className="mb-6 rounded-lg border border-neutral-200 bg-white p-5">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-neutral-900">
            {schema.label}
          </h2>
          <code className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-600">
            {schema.type}
          </code>
        </div>
        <p className="mt-1 text-sm text-neutral-600">{schema.description}</p>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
          <Meta label="Output processor">
            <code>{schema.processor}</code>
          </Meta>
          <Meta label="Form fields">{schema.fields.length}</Meta>
        </dl>
      </div>

      <div className="space-y-6">
        <PromptField
          label="Task framing"
          description={
            "The 'what kind of conversation are we having' wrapper around "
            + "every facilitator turn. Workflow-specific framing — for "
            + "document_revision, e.g., this is what tells the AI to anchor "
            + "the conversation in the doc."
          }
          draft={taskFraming}
          onChange={setTaskFraming}
          defaultValue={schema.default_task_framing}
          disabled={saving}
          rows={6}
        />
        <PromptField
          label="Output template"
          description={
            "The system prompt for the post-conversation processor "
            + `(${schema.processor}). Long and tightly tuned. ${SLOTS_HINT_OUTPUT}`
          }
          draft={outputTemplate}
          onChange={setOutputTemplate}
          defaultValue={schema.default_output_template}
          disabled={saving}
          rows={16}
        />
        <PromptField
          label="Conversation mechanics"
          description={
            "How to facilitate: probing patterns, pacing, when to wrap up, "
            + "when to emit [READY_FOR_PERMISSIONS]. The system default is "
            + "shared across workflow types and is usually fine; override "
            + "this only if you want workflow-specific style (e.g. shorter "
            + "probes for a quick check)."
          }
          draft={mechanics}
          onChange={setMechanics}
          defaultValue={schema.default_mechanics}
          disabled={saving}
          rows={14}
        />
      </div>

      {(saveError || statusMsg) && (
        <div
          className={
            "mt-6 rounded-md p-3 text-sm "
            + (saveError ? "bg-red-50 text-red-700" : "bg-green-50 text-green-800")
          }
        >
          {saveError ?? statusMsg}
        </div>
      )}

      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !dirty}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
        >
          {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
        <button
          type="button"
          onClick={() => navigate("/admin/workflows")}
          disabled={saving}
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          Back
        </button>
      </div>
    </AdminLayout>
  );
}

// ---------------------------------------------------------------------------

function PromptField({
  label,
  description,
  draft,
  onChange,
  defaultValue,
  disabled,
  rows,
}: {
  label: string;
  description: string;
  draft: FieldDraft;
  onChange: (next: FieldDraft) => void;
  defaultValue: string;
  disabled: boolean;
  rows: number;
}) {
  const usingDefault = !draft.override.trim();
  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-neutral-900">{label}</h3>
          <p className="mt-1 text-xs text-neutral-600">{description}</p>
        </div>
        <span
          className={
            "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium "
            + (usingDefault
              ? "bg-neutral-100 text-neutral-600"
              : "bg-amber-100 text-amber-800")
          }
        >
          {usingDefault ? "Using default" : "Overridden"}
        </span>
      </div>

      <textarea
        rows={rows}
        value={draft.override}
        onChange={(e) =>
          onChange({ override: e.target.value, initial: draft.initial })
        }
        disabled={disabled}
        placeholder={defaultValue}
        className="mt-3 block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-xs leading-relaxed text-neutral-800 shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:bg-neutral-100"
      />

      <div className="mt-2 flex items-center justify-between">
        <details className="text-xs text-neutral-600">
          <summary className="cursor-pointer hover:text-neutral-900">
            Show default ({defaultValue.length.toLocaleString()} chars)
          </summary>
          <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border border-neutral-200 bg-neutral-50 p-3 font-sans text-xs text-neutral-700">
            {defaultValue}
          </pre>
        </details>
        {draft.override && (
          <button
            type="button"
            onClick={() => onChange({ override: "", initial: draft.initial })}
            disabled={disabled}
            className="text-xs text-neutral-500 hover:text-neutral-900"
          >
            Reset to default
          </button>
        )}
      </div>
    </section>
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
