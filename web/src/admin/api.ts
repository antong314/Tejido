// REST client for /api/admin endpoints.

import { ApiError } from "../api";
import type {
  AdminSession,
  OutputFileEntry,
  ParticipantDetail,
  ParticipantSummary,
  Persona,
  ProcessorName,
  TelegramStatus,
  WorkflowSchema,
} from "./types";

async function parseError(r: Response): Promise<ApiError> {
  let body: { detail?: { code?: string; error?: string } } | null = null;
  try {
    body = await r.json();
  } catch {
    /* not json */
  }
  const code = body?.detail?.code ?? "unknown";
  const error = body?.detail?.error ?? r.statusText ?? "request failed";
  return new ApiError(r.status, code, error);
}

export async function listWorkflowTypes(): Promise<WorkflowSchema[]> {
  const r = await fetch("/api/admin/workflow-types");
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function listSessions(): Promise<AdminSession[]> {
  const r = await fetch("/api/admin/sessions");
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function getSession(id: string): Promise<AdminSession> {
  const r = await fetch(`/api/admin/sessions/${id}`);
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export interface CreateSessionInput {
  id: string;
  title: string;
  workflow_type: string;
  common?: AdminSession["common"];
  whisper?: AdminSession["whisper"];
  workflow_data?: AdminSession["workflow_data"];
}

export async function createSession(
  input: CreateSessionInput,
): Promise<AdminSession> {
  const r = await fetch("/api/admin/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export interface UpdateSessionInput {
  title?: string;
  common?: AdminSession["common"];
  whisper?: AdminSession["whisper"];
  workflow_data?: AdminSession["workflow_data"];
}

export async function updateSession(
  id: string,
  input: UpdateSessionInput,
): Promise<AdminSession> {
  const r = await fetch(`/api/admin/sessions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function deleteSession(id: string): Promise<void> {
  const r = await fetch(`/api/admin/sessions/${id}`, { method: "DELETE" });
  if (!r.ok) throw await parseError(r);
}

export async function runProcessor(
  id: string,
  processor: ProcessorName,
): Promise<{ status: string }> {
  const r = await fetch(`/api/admin/sessions/${id}/run/${processor}`, {
    method: "POST",
  });
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function listOutputs(id: string): Promise<OutputFileEntry[]> {
  const r = await fetch(`/api/admin/sessions/${id}/outputs`);
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export function outputUrl(id: string, filename: string): string {
  return `/api/admin/sessions/${id}/outputs/${encodeURIComponent(filename)}`;
}

export async function listParticipants(
  id: string,
): Promise<ParticipantSummary[]> {
  const r = await fetch(`/api/admin/sessions/${id}/participants`);
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function getParticipant(
  sessionId: string,
  participantId: string,
): Promise<ParticipantDetail> {
  const r = await fetch(
    `/api/admin/sessions/${sessionId}/participants/${participantId}`,
  );
  if (!r.ok) throw await parseError(r);
  return r.json();
}

// ---------------------------------------------------------------------------
// Personas — managed independently of sessions; sessions reference one by id.

export async function listPersonas(): Promise<Persona[]> {
  const r = await fetch("/api/admin/personas");
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function getPersona(id: string): Promise<Persona> {
  const r = await fetch(`/api/admin/personas/${id}`);
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export interface CreatePersonaInput {
  id: string;
  name: string;
  prompt: string;
  description?: string;
}

export async function createPersona(input: CreatePersonaInput): Promise<Persona> {
  const r = await fetch("/api/admin/personas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export interface UpdatePersonaInput {
  name?: string;
  prompt?: string;
  description?: string;
}

export async function updatePersona(
  id: string,
  input: UpdatePersonaInput,
): Promise<Persona> {
  const r = await fetch(`/api/admin/personas/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function deletePersona(id: string): Promise<void> {
  const r = await fetch(`/api/admin/personas/${id}`, { method: "DELETE" });
  if (!r.ok) throw await parseError(r);
}

// ---------------------------------------------------------------------------
// Telegram binding — single global setting, read/write via /admin/telegram.

export async function getTelegramStatus(): Promise<TelegramStatus> {
  const r = await fetch("/api/admin/telegram");
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function setTelegramBinding(
  sessionId: string | null,
): Promise<TelegramStatus> {
  const r = await fetch("/api/admin/telegram", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!r.ok) throw await parseError(r);
  return r.json();
}
