// Thin REST + SSE client for the FastAPI backend.

import type {
  ApiErrorBody,
  JoinResponse,
  ServerEvent,
  StateResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function parseError(r: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    body = await r.json();
  } catch {
    /* not json */
  }
  const code = body?.detail?.code ?? "unknown";
  const error = body?.detail?.error ?? r.statusText ?? "request failed";
  return new ApiError(r.status, code, error);
}

export async function join(
  sessionId: string,
  name: string,
): Promise<JoinResponse> {
  const r = await fetch(`/api/s/${sessionId}/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function fetchState(participantId: string): Promise<StateResponse> {
  const r = await fetch(`/api/p/${participantId}/state`);
  if (!r.ok) throw await parseError(r);
  return r.json();
}

export async function sendMessage(
  participantId: string,
  text: string,
): Promise<void> {
  const r = await fetch(`/api/p/${participantId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw await parseError(r);
}

export async function sendCallback(
  participantId: string,
  callback_data: string,
): Promise<void> {
  const r = await fetch(`/api/p/${participantId}/callback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_data }),
  });
  if (!r.ok) throw await parseError(r);
}

// EventSource subscription with auto-reconnect on transient failures.
// Returns a disposer that closes the connection.
export function subscribeEvents(
  participantId: string,
  onEvent: (event: ServerEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const url = `/api/p/${participantId}/events`;
  const es = new EventSource(url);

  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      onEvent(data as ServerEvent);
    } catch (e) {
      // ignore malformed events
      console.warn("malformed SSE event:", ev.data, e);
    }
  };
  es.onerror = (err) => {
    if (onError) onError(err);
    // EventSource auto-reconnects on transport errors.
  };

  return () => es.close();
}
