import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import { createContext, getContext, updateContext } from "./api";

interface Props {
  // Null = creating a new context. Otherwise = editing an existing one.
  contextId: string | null;
}

interface FormValue {
  name: string;
  text: string;
}

const EMPTY: FormValue = { name: "", text: "" };

// Slugify a name into a context id. Same character class the backend's
// _CONTEXT_ID_PATTERN enforces (lowercase letters, digits, dash,
// underscore; must start with [a-z0-9]; max 63 chars). We do the
// derivation client-side so the admin sees a live preview as they type.
function slugifyName(name: string): string {
  let s = name
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-") // anything else → hyphen
    .replace(/-+/g, "-") // collapse runs of hyphens
    .replace(/^[^a-z0-9]+/, "") // strip leading non-alphanumerics
    .replace(/[-_]+$/, ""); // strip trailing hyphens/underscores
  if (s.length > 63) s = s.slice(0, 63).replace(/[-_]+$/, "");
  return s;
}

export function ContextEdit({ contextId }: Props) {
  const isNew = contextId === null;
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
        const c = await getContext(contextId!);
        if (!cancelled) {
          setValue({ name: c.name, text: c.text });
          setLoading(false);
        }
      } catch (e) {
        if (cancelled) return;
        setServerError(
          e instanceof ApiError ? e.message : "Couldn't load context.",
        );
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isNew, contextId]);

  function update<K extends keyof FormValue>(key: K, next: FormValue[K]) {
    setValue((v) => ({ ...v, [key]: next }));
  }

  // Live-derived id preview — only used when creating. When editing, the
  // existing id is immutable (it's in URLs and filenames) so we show that
  // instead.
  const derivedId = isNew ? slugifyName(value.name) : contextId!;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);
    setServerError(null);
    if (!value.name.trim()) {
      setLocalError("Name is required.");
      return;
    }
    if (!value.text.trim()) {
      setLocalError("Context text is required.");
      return;
    }
    if (isNew && !derivedId) {
      // Slugified to nothing — usually means the name is all punctuation.
      setLocalError(
        "Name needs at least one letter or digit to derive an id from.",
      );
      return;
    }
    setSubmitting(true);
    try {
      if (isNew) {
        await createContext({
          id: derivedId,
          name: value.name,
          text: value.text,
        });
        navigate("/admin/contexts");
      } else {
        await updateContext(contextId!, {
          name: value.name,
          text: value.text,
        });
        setStatusMsg("Saved.");
        setTimeout(() => setStatusMsg(null), 2500);
      }
    } catch (e) {
      setServerError(
        e instanceof ApiError ? e.message : "Could not save context.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AdminLayout title={isNew ? "New context" : value.name || contextId!}>
      <div className="mb-4">
        <a
          href="/admin/contexts"
          onClick={(e) => {
            e.preventDefault();
            navigate("/admin/contexts");
          }}
          className="text-xs text-neutral-600 hover:text-neutral-900"
        >
          ← back to context library
        </a>
      </div>

      {loading && <div className="text-sm text-neutral-500">Loading…</div>}

      {!loading && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <section className="rounded-lg border border-neutral-200 bg-white p-5">
            <div className="space-y-4">
              <Field label="Name">
                <input
                  type="text"
                  value={value.name}
                  onChange={(e) => update("name", e.target.value)}
                  disabled={submitting}
                  placeholder="e.g. Bamboo Hill bylaws context"
                  className={inputClass(false)}
                  autoFocus
                />
                {isNew ? (
                  <Hint>
                    Will be saved as{" "}
                    <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-[11px] text-neutral-700">
                      {derivedId || "—"}
                    </code>
                    . The id is derived from the name and used in URLs +
                    filenames; it cannot be changed afterward.
                  </Hint>
                ) : (
                  <Hint>
                    Saved as{" "}
                    <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-[11px] text-neutral-700">
                      {derivedId}
                    </code>
                    . The id is fixed; renaming only changes how this
                    context appears in dropdowns.
                  </Hint>
                )}
              </Field>

              <Field label="Community context">
                <textarea
                  rows={14}
                  value={value.text}
                  onChange={(e) => update("text", e.target.value)}
                  disabled={submitting}
                  placeholder="Shared values, prior decisions, named principles, things the synthesis output should ground itself in. Free-form; markdown OK."
                  className={inputClass(false) + " font-mono text-sm"}
                />
                <Hint>
                  Embedded into the synthesis / proposal / revise system
                  prompt under "COMMUNITY CONTEXT". The output processors
                  use this to ground their language in your community's
                  specific values and history.
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
                  ? "Create context"
                  : "Save changes"}
            </button>
            <button
              type="button"
              onClick={() => navigate("/admin/contexts")}
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
