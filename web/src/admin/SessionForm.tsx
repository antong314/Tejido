import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { listContexts } from "./api";
import type {
  AdminSession,
  CommonSettings,
  Context,
  FacilitationDepth,
  FieldSchema,
  WorkflowSchema,
} from "./types";

// The two canonical models we expose in the dropdowns. The session JSON can
// hold any model string the admin once typed; the dropdown will surface a
// legacy value as an "other" option so they can see what's set without
// silently coercing it.
const FACILITATOR_MODEL_OPTIONS = ["claude-sonnet-4-6", "claude-opus-4-6"];
const SYNTHESIS_MODEL_OPTIONS = ["claude-opus-4-6", "claude-sonnet-4-6"];

// Depth slider — three discrete stops. The labels and definitions shown to
// the admin must match the actual prompt fragments in
// src/circle/prompts.py::DEPTH_BLOCKS so what they see is what the LLM gets.
const DEPTH_LEVELS: {
  key: FacilitationDepth;
  label: string;
  blurb: string;
}[] = [
  {
    key: "minimal",
    label: "Minimal",
    blurb:
      "Quick check-in. About 2-3 minutes; 3-4 questions. Enough to register a gut reaction, not to probe deeply.",
  },
  {
    key: "medium",
    label: "Medium",
    blurb:
      "Standard depth. 5-10 minutes. Surface their position, explore one or two underlying values or tradeoffs, and reflect once.",
  },
  {
    key: "deep",
    label: "Deep",
    blurb:
      "Extended exploration. 10-20 minutes. Several rounds of probing, edge cases, counterpositions, and uncertainty.",
  },
];

// SessionForm renders all the fields for a session — common settings
// (model names, depth) plus the schema-driven workflow_data fields. The
// task framing / output template / mechanics live on the workflow type
// itself, not on the session, so they're edited at /admin/workflows/<type>.
// Sessions just inherit whatever the workflow type currently resolves to.

export interface SessionFormValue {
  id: string;
  title: string;
  workflow_type: string;
  common: CommonSettings;
  workflow_data: Record<string, unknown>;
}

interface Props {
  schema: WorkflowSchema;
  initial: SessionFormValue;
  // When false, the id field is disabled (used for editing).
  allowEditId: boolean;
  submitLabel: string;
  // The parent form's submit + cancel handlers.
  onSubmit: (value: SessionFormValue) => Promise<void> | void;
  onCancel?: () => void;
  // Surface server-side validation errors to the user.
  serverError?: string | null;
}

export function SessionForm({
  schema,
  initial,
  allowEditId,
  submitLabel,
  onSubmit,
  onCancel,
  serverError,
}: Props) {
  const [value, setValue] = useState<SessionFormValue>(initial);
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // Context Library — fetched once on mount. If the call fails we still
  // let the form render (the dropdown just shows "(none)"; the admin can
  // still save the session and add a context later).
  const [contexts, setContexts] = useState<Context[] | null>(null);
  const [contextsError, setContextsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await listContexts();
        if (!cancelled) setContexts(r);
      } catch (e) {
        if (cancelled) return;
        setContextsError(
          e instanceof ApiError
            ? e.message
            : "Couldn't load contexts. You can still save without one.",
        );
        setContexts([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const currentDepth: FacilitationDepth =
    (value.common.facilitation_depth as FacilitationDepth | undefined) ??
    "medium";
  const depthIndex = Math.max(
    0,
    DEPTH_LEVELS.findIndex((d) => d.key === currentDepth),
  );
  const depthDef = DEPTH_LEVELS[depthIndex] ?? DEPTH_LEVELS[1];

  const facilitatorOptions = useMemo(
    () => withCurrent(FACILITATOR_MODEL_OPTIONS, value.common.facilitator_model),
    [value.common.facilitator_model],
  );
  const synthesisOptions = useMemo(
    () => withCurrent(SYNTHESIS_MODEL_OPTIONS, value.common.synthesis_model),
    [value.common.synthesis_model],
  );

  function setCommon<K extends keyof CommonSettings>(
    key: K,
    next: CommonSettings[K],
  ) {
    setValue((v) => ({ ...v, common: { ...v.common, [key]: next } }));
  }

  function setField(name: string, next: unknown) {
    setValue((v) => ({
      ...v,
      workflow_data: { ...v.workflow_data, [name]: next },
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);
    if (!value.id.trim()) {
      setLocalError("Id is required.");
      return;
    }
    if (!value.title.trim()) {
      setLocalError("Title is required.");
      return;
    }
    for (const f of schema.fields) {
      if (!f.required) continue;
      const v = value.workflow_data[f.name];
      if (
        v == null ||
        (typeof v === "string" && !v.trim()) ||
        (Array.isArray(v) && v.length === 0)
      ) {
        setLocalError(`"${f.label}" is required.`);
        return;
      }
    }
    setSubmitting(true);
    try {
      await onSubmit(value);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Section title="Identity">
        <Field label="Id">
          <input
            type="text"
            value={value.id}
            onChange={(e) =>
              setValue((v) => ({
                ...v,
                id: e.target.value
                  .toLowerCase()
                  .replace(/[^a-z0-9_-]/g, "_"),
              }))
            }
            disabled={!allowEditId || submitting}
            placeholder="kebab-or-snake-case-slug"
            className={inputClass(!allowEditId)}
          />
          <Hint>
            Used in URLs and filenames. Lowercase letters, numbers, dashes,
            underscores. Cannot be changed after creation.
          </Hint>
        </Field>
        <Field label="Title">
          <input
            type="text"
            value={value.title}
            onChange={(e) =>
              setValue((v) => ({ ...v, title: e.target.value }))
            }
            disabled={submitting}
            className={inputClass(false)}
          />
          <Hint>Human-friendly name shown in the admin list.</Hint>
        </Field>
      </Section>

      <Section title={`${schema.label} settings`}>
        {schema.fields.map((f) => (
          <FieldRender
            key={f.name}
            schema={f}
            value={value.workflow_data[f.name]}
            disabled={submitting}
            onChange={(v) => setField(f.name, v)}
          />
        ))}
      </Section>

      <Section title="Common settings">
        <Field label="Facilitator model">
          <select
            value={value.common.facilitator_model ?? FACILITATOR_MODEL_OPTIONS[0]}
            onChange={(e) =>
              setCommon("facilitator_model", e.target.value || undefined)
            }
            disabled={submitting}
            className={inputClass(false)}
          >
            {facilitatorOptions.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
          <Hint>
            Drives the participant-facing facilitator turn. Sonnet is faster
            and cheaper; Opus is stronger on nuance.
          </Hint>
        </Field>
        <Field label="Synthesis / proposal / revise model">
          <select
            value={value.common.synthesis_model ?? SYNTHESIS_MODEL_OPTIONS[0]}
            onChange={(e) =>
              setCommon("synthesis_model", e.target.value || undefined)
            }
            disabled={submitting}
            className={inputClass(false)}
          >
            {synthesisOptions.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
          <Hint>
            Used for the post-conversation analysis (synthesis, proposal, or
            revise). Defaults to Opus since these runs care about depth more
            than latency.
          </Hint>
        </Field>

        <Field label="Community context">
          <div className="flex items-center gap-2">
            <select
              value={value.common.community_context_id ?? ""}
              onChange={(e) =>
                setCommon(
                  "community_context_id",
                  e.target.value || undefined,
                )
              }
              disabled={submitting || contexts === null}
              className={inputClass(false)}
            >
              <option value="">— None (no community context) —</option>
              {(contexts ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => navigate("/admin/contexts")}
              className="shrink-0 rounded-md border border-neutral-300 bg-white px-3 py-2 text-xs text-neutral-700 hover:bg-neutral-50"
            >
              Manage
            </button>
          </div>
          {contextsError && (
            <p className="mt-1 text-xs text-amber-700">{contextsError}</p>
          )}
          <Hint>
            Reusable community-context blob (shared values, prior decisions,
            named principles). Used by the synthesis / proposal / revise
            output processors to ground their output in your community.
            Optional — leave as "None" if this session doesn't need it.
          </Hint>
        </Field>

        <Field label="Workflow prompts">
          <div className="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-700">
            The task framing, output template, and conversation mechanics
            for <strong>{schema.label}</strong> are managed at the workflow
            level — every session of this type inherits them.
          </div>
          <button
            type="button"
            onClick={() => navigate(`/admin/workflows/${schema.type}`)}
            className="mt-2 text-xs font-medium text-neutral-700 hover:text-neutral-900"
          >
            Edit {schema.label.toLowerCase()} prompts →
          </button>
        </Field>

        <Field label="Conversation depth">
          <input
            type="range"
            min={0}
            max={DEPTH_LEVELS.length - 1}
            step={1}
            value={depthIndex}
            onChange={(e) =>
              setCommon(
                "facilitation_depth",
                DEPTH_LEVELS[Number(e.target.value)].key,
              )
            }
            disabled={submitting}
            className="w-full accent-neutral-900"
          />
          <div className="mt-1 flex justify-between text-[10px] uppercase tracking-wide text-neutral-500">
            {DEPTH_LEVELS.map((d, i) => (
              <button
                key={d.key}
                type="button"
                onClick={() => setCommon("facilitation_depth", d.key)}
                disabled={submitting}
                className={
                  i === depthIndex
                    ? "font-semibold text-neutral-900"
                    : "hover:text-neutral-900"
                }
              >
                {d.label}
              </button>
            ))}
          </div>
          <div className="mt-2 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-700">
            <span className="font-medium text-neutral-900">{depthDef.label}.</span>{" "}
            {depthDef.blurb}
          </div>
          <Hint>
            Pacing target injected into the facilitator prompt. Some
            questions are quick gut-checks; others deserve a long
            exploration.
          </Hint>
        </Field>
      </Section>

      {(localError || serverError) && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {localError ?? serverError}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
        >
          {submitting ? "Saving…" : submitLabel}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="text-sm text-neutral-600 hover:text-neutral-900"
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------

// Build the dropdown option list for a model field. Always shows the
// canonical options. If the session is currently set to a non-canonical
// value (e.g. a legacy "claude-sonnet-4-5"), surface it as an extra
// "(unrecognized)" option at the top so the admin sees what's set instead
// of being silently coerced.
function withCurrent(
  canonical: string[],
  current: string | undefined,
): { value: string; label: string }[] {
  const opts = canonical.map((m) => ({ value: m, label: m }));
  if (current && !canonical.includes(current)) {
    return [{ value: current, label: `${current} (unrecognized)` }, ...opts];
  }
  return opts;
}

function inputClass(disabled: boolean): string {
  return [
    "block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm shadow-sm",
    "focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500",
    disabled ? "bg-neutral-100 text-neutral-500 cursor-not-allowed" : "bg-white",
  ].join(" ");
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-neutral-900">{title}</h2>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-wide text-neutral-600">
        {label}
      </span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-neutral-500">{children}</p>;
}

function FieldRender({
  schema,
  value,
  disabled,
  onChange,
}: {
  schema: FieldSchema;
  value: unknown;
  disabled: boolean;
  onChange: (next: unknown) => void;
}) {
  if (schema.type === "text") {
    return (
      <Field label={schema.label + (schema.required ? " *" : "")}>
        <input
          type="text"
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={inputClass(false)}
        />
        {schema.description && <Hint>{schema.description}</Hint>}
      </Field>
    );
  }
  if (schema.type === "long_text") {
    return (
      <Field label={schema.label + (schema.required ? " *" : "")}>
        <textarea
          rows={6}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={inputClass(false) + " font-mono text-sm"}
        />
        {schema.description && <Hint>{schema.description}</Hint>}
      </Field>
    );
  }
  if (schema.type === "list_of_text") {
    const list = Array.isArray(value) ? (value as string[]) : [];
    return (
      <Field label={schema.label + (schema.required ? " *" : "")}>
        <div className="space-y-2">
          {list.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="text"
                value={item}
                onChange={(e) => {
                  const next = [...list];
                  next[i] = e.target.value;
                  onChange(next);
                }}
                disabled={disabled}
                className={inputClass(false)}
              />
              <button
                type="button"
                onClick={() => onChange(list.filter((_, j) => j !== i))}
                disabled={disabled}
                className="text-xs text-neutral-500 hover:text-red-700"
              >
                remove
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => onChange([...list, ""])}
            disabled={disabled}
            className="text-xs font-medium text-neutral-700 hover:text-neutral-900"
          >
            + add item
          </button>
        </div>
        {schema.description && <Hint>{schema.description}</Hint>}
      </Field>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Helpers — initial-value construction.

export function emptyValueForSchema(
  schema: WorkflowSchema,
  id = "",
  title = "",
): SessionFormValue {
  const workflow_data: Record<string, unknown> = {};
  for (const f of schema.fields) {
    if (f.default !== null && f.default !== undefined) {
      workflow_data[f.name] = f.default;
    } else if (f.type === "list_of_text") {
      workflow_data[f.name] = [];
    } else {
      workflow_data[f.name] = "";
    }
  }
  return {
    id,
    title,
    workflow_type: schema.type,
    common: {
      facilitator_model: FACILITATOR_MODEL_OPTIONS[0],
      synthesis_model: SYNTHESIS_MODEL_OPTIONS[0],
      facilitation_depth: "medium",
      community_context_id: "",
    },
    workflow_data,
  };
}

export function valueFromSession(s: AdminSession): SessionFormValue {
  return {
    id: s.id,
    title: s.title,
    workflow_type: s.workflow_type,
    common: { ...s.common },
    workflow_data: { ...s.workflow_data },
  };
}
