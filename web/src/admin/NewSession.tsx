import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { navigate } from "../router";
import { AdminLayout } from "./AdminLayout";
import {
  SessionForm,
  emptyValueForSchema,
  type SessionFormValue,
} from "./SessionForm";
import { createSession, listWorkflowTypes } from "./api";
import type { WorkflowSchema } from "./types";

type Step = { kind: "loading" } | { kind: "pick" } | { kind: "form"; schema: WorkflowSchema };

export function NewSession() {
  const [types, setTypes] = useState<WorkflowSchema[]>([]);
  const [step, setStep] = useState<Step>({ kind: "loading" });
  const [error, setError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const t = await listWorkflowTypes();
        if (cancelled) return;
        setTypes(t);
        setStep({ kind: "pick" });
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? e.message : "Couldn't load workflow types.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(value: SessionFormValue) {
    setServerError(null);
    try {
      await createSession({
        id: value.id,
        title: value.title,
        workflow_type: value.workflow_type,
        common: value.common,
        workflow_data: value.workflow_data,
      });
      navigate(`/admin/sessions/${value.id}`);
    } catch (e) {
      setServerError(
        e instanceof ApiError ? e.message : "Could not create session.",
      );
    }
  }

  return (
    <AdminLayout title="New workflow">
      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {step.kind === "loading" && (
        <div className="text-sm text-neutral-500">Loading…</div>
      )}

      {step.kind === "pick" && (
        <div>
          <h2 className="text-base font-medium text-neutral-900">
            Pick a workflow type
          </h2>
          <p className="mt-1 text-sm text-neutral-600">
            Each type uses a different AI persona, asks different questions,
            and produces a different output. You can edit any of these
            details afterward.
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {types.map((t) => (
              <button
                key={t.type}
                type="button"
                onClick={() => setStep({ kind: "form", schema: t })}
                className="rounded-lg border border-neutral-200 bg-white p-4 text-left hover:border-neutral-400 hover:shadow-sm"
              >
                <div className="text-sm font-semibold text-neutral-900">
                  {t.label}
                </div>
                <div className="mt-1 text-xs text-neutral-600">
                  {t.description}
                </div>
                <div className="mt-3 text-xs text-neutral-500">
                  → {t.processor}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {step.kind === "form" && (
        <div>
          <button
            type="button"
            onClick={() => setStep({ kind: "pick" })}
            className="mb-4 text-xs text-neutral-600 hover:text-neutral-900"
          >
            ← back to picker
          </button>
          <h2 className="text-base font-medium text-neutral-900">
            New {step.schema.label}
          </h2>
          <p className="mt-1 mb-5 text-sm text-neutral-600">
            {step.schema.description}
          </p>
          <SessionForm
            schema={step.schema}
            initial={emptyValueForSchema(step.schema)}
            allowEditId
            submitLabel="Create"
            onSubmit={handleSubmit}
            onCancel={() => navigate("/admin")}
            serverError={serverError}
          />
        </div>
      )}
    </AdminLayout>
  );
}
