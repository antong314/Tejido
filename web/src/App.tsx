import { useEffect, useState } from "react";
import { NameEntry } from "./components/NameEntry";
import { Chat } from "./components/Chat";

// Identity is stored per-session in localStorage. Different sessions on
// the same browser get different keys so two sessions don't collide.

interface StoredIdentity {
  participant_id: string;
  display_name: string;
}

function storageKey(sessionId: string): string {
  return `tejido:${sessionId}:identity`;
}

function loadIdentity(sessionId: string): StoredIdentity | null {
  try {
    const raw = localStorage.getItem(storageKey(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.participant_id === "string" && typeof parsed?.display_name === "string") {
      return parsed;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function saveIdentity(sessionId: string, identity: StoredIdentity): void {
  localStorage.setItem(storageKey(sessionId), JSON.stringify(identity));
}

function clearIdentity(sessionId: string): void {
  localStorage.removeItem(storageKey(sessionId));
}

// Path is `/s/<session_id>` — extract the id from window.location.
// SPA routing is intentionally minimal; one route is all we need.
function readSessionFromPath(): string | null {
  const m = /^\/s\/([a-zA-Z0-9_-]+)/.exec(window.location.pathname);
  return m ? m[1] : null;
}

export default function App() {
  const sessionId = readSessionFromPath();
  const [identity, setIdentity] = useState<StoredIdentity | null>(() =>
    sessionId ? loadIdentity(sessionId) : null,
  );

  useEffect(() => {
    document.title = sessionId ? `Tejido — ${sessionId}` : "Tejido";
  }, [sessionId]);

  if (!sessionId) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <div className="max-w-md">
          <h1 className="text-xl font-semibold">Tejido</h1>
          <p className="mt-2 text-sm text-neutral-600">
            Open the link your facilitator gave you. It looks like
            <code className="ml-1 rounded bg-neutral-100 px-1.5 py-0.5 text-xs">
              /s/&lt;session-id&gt;
            </code>.
          </p>
        </div>
      </div>
    );
  }

  if (!identity) {
    return (
      <NameEntry
        sessionId={sessionId}
        onJoined={(participant_id, display_name) => {
          const next = { participant_id, display_name };
          saveIdentity(sessionId, next);
          setIdentity(next);
        }}
      />
    );
  }

  return (
    <Chat
      sessionId={sessionId}
      participantId={identity.participant_id}
      displayName={identity.display_name}
      onResetIdentity={() => {
        clearIdentity(sessionId);
        setIdentity(null);
      }}
    />
  );
}
