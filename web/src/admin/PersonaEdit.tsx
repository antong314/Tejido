import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { createPersona, getPersona, updatePersona } from "./api";

// Edit one persona — used for both "create new" (personaId === null) and
// "edit existing" (personaId set). The id field is locked when editing
// because it lives in URLs, filenames, and session.common.ai_persona_id.

interface Props {
  personaId: string | null;
}

interface FormValue {
  id: string;
  name: string;
  description: string;
  prompt: string;
}

const EMPTY: FormValue = { id: "", name: "", description: "", prompt: "" };

export function PersonaEdit({ personaId }: Props) {
  const isNew = personaId === null;
  const [value, setValue] = useState<FormValue>(EMPTY);
  const [loading, setLoading] = useState(!isNew);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isNew) return;
    let cancelled = false;
    (async () => {
      try {
        const p = await getPersona(personaId!);
        if (!cancelled) {
          setValue({
            id: p.id,
            name: p.name,
            description: p.description,
            prompt: p.prompt,
          });
          setLoading(false);
        }
      } catch (e) {
        if (cancelled) return;
        setServerError(
          e instanceof ApiError ? e.message : "Couldn't load persona.",
        );
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isNew, personaId]);

  function update<K extends keyof FormValue>(key: K, next: FormValue[K]) {
    setValue((v) => ({ ...v, [key]: next }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);
    setServerError(null);
    if (isNew && !value.id.trim()) {
      setLocalError("Id is required.");
      return;
    }
    if (!value.name.trim()) {
      setLocalError("Name is required.");
      return;
    }
    if (!value.prompt.trim()) {
      setLocalError("Prompt is required.");
      return;
    }
    setSubmitting(true);
    try {
      if (isNew) {
        await createPersona({
          id: value.id,
          name: value.name,
          description: value.description,
          prompt: value.prompt,
        });
        navigate("/admin/personas");
      } else {
        await updatePersona(personaId!, {
          name: value.name,
          description: value.description,
          prompt: value.prompt,
        });
        setStatusMsg("Saved.");
        setTimeout(() => setStatusMsg(null), 2500);
      }
    } catch (e) {
      setServerError(
        e instanceof ApiError ? e.message : "Could not save persona.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AdminLayout title={isNew ? "New persona" : value.name || personaId!}>
      <div className="mb-4">
        <a
          href="/admin/personas"
          onClick={(e) => {
            e.preventDefault();
            navigate("/admin/personas");
          }}
          className="text-xs text-neutral-600 hover:text-neutral-900"
        >
          ← back to personas
        </a>
      </div>

      {loading && <div className="text-sm text-neutral-500">Loading…</div>}

      {!loading && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <section className="rounded-lg border border-neutral-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-neutral-900">
              Identity
            </h2>
            <div className="mt-4 space-y-4">
              <Field label="Id">
                <input
                  type="text"
                  value={value.id}
                  onChange={(e) =>
                    update(
                      "id",
                      e.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9_-]/g, "_"),
                    )
                  }
                  disabled={!isNew || submitting}
                  placeholder="kebab-or-snake-case-slug"
                  className={inputClass(!isNew)}
                />
                <Hint>
                  Used in URLs and as the filename on disk. Cannot be
                  changed after creation.
                </Hint>
              </Field>
              <Field label="Name">
                <input
                  type="text"
                  value={value.name}
                  onChange={(e) => update("name", e.target.value)}
                  disabled={submitting}
                  placeholder="e.g. Warm community elder"
                  className={inputClass(false)}
                />
                <Hint>Shown in the persona dropdown on session forms.</Hint>
              </Field>
              <Field label="Description">
                <input
                  type="text"
                  value={value.description}
                  onChange={(e) => update("description", e.target.value)}
                  disabled={submitting}
                  placeholder="(optional) one-line summary"
                  className={inputClass(false)}
                />
              </Field>
            </div>
          </section>

          <section className="rounded-lg border border-neutral-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-neutral-900">
              Prompt
            </h2>
            <div className="mt-4">
              <Field label="Persona prompt">
                <textarea
                  rows={14}
                  value={value.prompt}
                  onChange={(e) => update("prompt", e.target.value)}
                  disabled={submitting}
                  placeholder="You are a thoughtful facilitator…"
                  className={inputClass(false) + " font-mono text-sm"}
                />
                <Hint>
                  Free-form. The mechanical scaffolding (probing patterns,
                  pacing, when to wrap up) is fixed in code; this is the
                  "who you are" framing that wraps it. Avoid embedding
                  question-specific content here — that goes on the
                  session form.
                </Hint>
              </Field>
            </div>
          </section>

          {(localError || serverError) && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
              {localError ?? serverError}
            </div>
          )}

          {statusMsg && (
            <div className="rounded-md bg-green-50 p-3 text-sm text-green-800">
              {statusMsg}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
            >
              {submitting
                ? "Saving…"
                : isNew
                  ? "Create persona"
                  : "Save changes"}
            </button>
            <button
              type="button"
              onClick={() => navigate("/admin/personas")}
              disabled={submitting}
              className="text-sm text-neutral-600 hover:text-neutral-900"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </AdminLayout>
  );
}

function inputClass(disabled: boolean): string {
  return [
    "block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm shadow-sm",
    "focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500",
    disabled ? "bg-neutral-100 text-neutral-500 cursor-not-allowed" : "bg-white",
  ].join(" ");
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
