import { useEffect, useState } from "react";
import { NameEntry } from "./components/NameEntry";
import { Chat } from "./components/Chat";
import { EditSession } from "./admin/EditSession";
import { NewSession } from "./admin/NewSession";
import { ContextEdit } from "./admin/ContextEdit";
import { Contexts } from "./admin/Contexts";
import { ParticipantDetail } from "./admin/ParticipantDetail";
import { SessionList } from "./admin/SessionList";
import { WorkflowTypes } from "./admin/WorkflowTypes";
import { WorkflowTypeEdit } from "./admin/WorkflowTypeEdit";
import { useRoute } from "./router";

// Identity is stored per-session in localStorage. Different sessions on the
// same browser get different keys so two sessions don't collide.

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
    if (
      typeof parsed?.participant_id === "string" &&
      typeof parsed?.display_name === "string"
    ) {
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

export default function App() {
  const route = useRoute();

  useEffect(() => {
    if (route.name === "session") document.title = `Tejido — ${route.sessionId}`;
    else if (route.name === "admin_home") document.title = "Tejido — admin";
    else if (route.name === "admin_new_session")
      document.title = "Tejido — new workflow";
    else if (route.name === "admin_edit_session")
      document.title = `Tejido — admin — ${route.sessionId}`;
    else if (route.name === "admin_workflows")
      document.title = "Tejido — workflows";
    else if (route.name === "admin_edit_workflow")
      document.title = `Tejido — workflow — ${route.workflowType}`;
    else if (route.name === "admin_contexts")
      document.title = "Tejido — contexts";
    else if (route.name === "admin_new_context")
      document.title = "Tejido — new context";
    else if (route.name === "admin_edit_context")
      document.title = `Tejido — context — ${route.contextId}`;
    else document.title = "Tejido";
  }, [route]);

  if (route.name === "admin_home") return <SessionList />;
  if (route.name === "admin_new_session") return <NewSession />;
  if (route.name === "admin_edit_session")
    return <EditSession sessionId={route.sessionId} />;
  if (route.name === "admin_participant")
    return (
      <ParticipantDetail
        sessionId={route.sessionId}
        participantId={route.participantId}
      />
    );
  if (route.name === "admin_workflows") return <WorkflowTypes />;
  if (route.name === "admin_edit_workflow")
    return <WorkflowTypeEdit workflowType={route.workflowType} />;
  if (route.name === "admin_contexts") return <Contexts />;
  if (route.name === "admin_new_context") return <ContextEdit contextId={null} />;
  if (route.name === "admin_edit_context")
    return <ContextEdit contextId={route.contextId} />;
  if (route.name === "session")
    return <ParticipantSession sessionId={route.sessionId} />;
  return <Welcome />;
}

function Welcome() {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center">
      <div className="max-w-md">
        <h1 className="text-xl font-semibold">Tejido</h1>
        <p className="mt-2 text-sm text-neutral-600">
          Open the link your facilitator gave you. It looks like
          <code className="ml-1 rounded bg-neutral-100 px-1.5 py-0.5 text-xs">
            /s/&lt;session-id&gt;
          </code>
          .
        </p>
        <a
          href="/admin"
          className="mt-4 inline-block text-sm text-neutral-600 hover:text-neutral-900"
        >
          Admin →
        </a>
      </div>
    </div>
  );
}

function ParticipantSession({ sessionId }: { sessionId: string }) {
  const [identity, setIdentity] = useState<StoredIdentity | null>(() =>
    loadIdentity(sessionId),
  );

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
