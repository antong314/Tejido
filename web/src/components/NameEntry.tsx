import { useState } from "react";
import { join, ApiError } from "../api";

interface Props {
  sessionId: string;
  onJoined: (participantId: string, displayName: string) => void;
}

export function NameEntry({ sessionId, onJoined }: Props) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Please enter a name.");
      return;
    }
    setSubmitting(true);
    try {
      const r = await join(sessionId, name.trim());
      onJoined(r.participant_id, r.display_name);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError("Couldn't reach the server. Try again?");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex h-full items-center justify-center">
      <div className="w-full max-w-md rounded-lg bg-white p-8 shadow-sm border border-neutral-200">
        <h1 className="text-xl font-semibold text-neutral-900">
          Welcome to Tejido
        </h1>
        <p className="mt-2 text-sm text-neutral-600">
          A private, AI-facilitated conversation. About 10 minutes. What you
          say is yours until you say otherwise.
        </p>
        <form onSubmit={handleSubmit} className="mt-6 space-y-3">
          <label className="block text-sm font-medium text-neutral-700">
            What should we call you?
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="off"
              autoFocus
              disabled={submitting}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-base shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-50"
            />
          </label>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
          >
            {submitting ? "Joining..." : "Begin"}
          </button>
          {error && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
