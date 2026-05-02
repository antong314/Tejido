import { useMemo, useState } from "react";
import type {
  AdminSession,
  CommonSettings,
  FieldSchema,
  WorkflowSchema,
} from "./types";

// SessionForm renders all the fields for a session — common settings (model
// names, persona) plus the schema-driven workflow_data fields. It works for
// both create and edit; the parent decides what to do on submit.

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

  const personaPlaceholder = useMemo(
    () => schema.default_persona,
    [schema.default_persona],
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
          <input
            type="text"
            value={value.common.facilitator_model ?? ""}
            onChange={(e) =>
              setCommon("facilitator_model", e.target.value || undefined)
            }
            disabled={submitting}
            className={inputClass(false)}
          />
        </Field>
        <Field label="Synthesis / proposal / revise model">
          <input
            type="text"
            value={value.common.synthesis_model ?? ""}
            onChange={(e) =>
              setCommon("synthesis_model", e.target.value || undefined)
            }
            disabled={submitting}
            className={inputClass(false)}
          />
        </Field>
        <Field label="AI persona">
          <textarea
            rows={4}
            value={value.common.ai_persona ?? ""}
            onChange={(e) =>
              setCommon("ai_persona", e.target.value)
            }
            disabled={submitting}
            placeholder={personaPlaceholder}
            className={inputClass(false)}
          />
          <div className="mt-1 flex items-center justify-between">
            <Hint>
              Free-form. The mechanical scaffolding (probing patterns,
              when to wrap up, etc.) is fixed in code; this is the
              persona / tone wrapper added on top. Empty = use the
              workflow default shown as placeholder above.
            </Hint>
            {value.common.ai_persona ? (
              <button
                type="button"
                onClick={() => setCommon("ai_persona", "")}
                className="ml-3 shrink-0 text-xs text-neutral-500 hover:text-neutral-900"
              >
                reset to default
              </button>
            ) : null}
          </div>
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
      ai_persona: "",
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
