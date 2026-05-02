import { useEffect, useRef, useState } from "react";
import { fetchState, sendMessage, subscribeEvents, ApiError } from "../api";
import { deriveInitialMessages } from "../derive_messages";
import type { ChatMessage, ContentPart, Phase, ServerEvent } from "../types";
import { ChoicePrompt } from "./ChoicePrompt";
import { MicButton } from "./MicButton";

interface Props {
  sessionId: string;
  participantId: string;
  displayName: string;
  onResetIdentity: () => void;
}

let _eventCounter = 0;
const nextMsgId = () => `evt-${++_eventCounter}`;

export function Chat({ sessionId, participantId, displayName, onResetIdentity }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [phase, setPhase] = useState<Phase>("not_started");
  const [typing, setTyping] = useState(false);
  const [pending, setPending] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [bootstrapped, setBootstrapped] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Bootstrap from server state.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await fetchState(sessionId, participantId);
        if (cancelled) return;
        setMessages(deriveInitialMessages(s));
        setPhase(s.phase);
        setBootstrapped(true);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          // The participant_id in localStorage no longer exists on the
          // server (e.g. data dir wiped). Reset.
          onResetIdentity();
          return;
        }
        setError(
          e instanceof Error
            ? e.message
            : "Couldn't load your session.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, participantId, onResetIdentity]);

  // Subscribe to SSE.
  useEffect(() => {
    if (!bootstrapped) return;
    const dispose = subscribeEvents(sessionId, participantId, (event) => {
      applyEvent(event);
    });
    return dispose;
  }, [sessionId, participantId, bootstrapped]);

  function applyEvent(event: ServerEvent) {
    if (event.type === "typing") {
      setTyping(true);
      return;
    }
    if (event.type === "phase_update") {
      setPhase(event.phase);
      return;
    }
    if (event.type === "user_message") {
      // Server-echoed user input — currently only fires on the voice
      // path; text submissions are optimistically rendered by the
      // sender's client (see handleSend below).
      setMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: "user",
          content: [
            { type: "text", text: event.text, parse_mode: "plain" },
          ],
        },
      ]);
      return;
    }
    setTyping(false);

    if (event.type === "text") {
      setMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: "assistant",
          content: [
            { type: "text", text: event.text, parse_mode: event.parse_mode },
          ],
        },
      ]);
    } else if (event.type === "choice_prompt") {
      setMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: "assistant",
          content: [
            {
              type: "choice_prompt",
              text: event.text,
              parse_mode: event.parse_mode,
              choices: event.choices,
              resolved: false,
              resolvedText: null,
            },
          ],
        },
      ]);
    } else if (event.type === "resolve_choice") {
      // Mutate the most recent assistant message's last content part.
      setMessages((prev) => {
        const next = [...prev];
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role !== "assistant") continue;
          const parts = next[i].content;
          const last = parts[parts.length - 1];
          if (last.type === "choice_prompt") {
            const newParts: ContentPart[] = [
              ...parts.slice(0, -1),
              {
                ...last,
                resolved: true,
                resolvedText: event.text,
              },
            ];
            next[i] = { ...next[i], content: newParts };
            return next;
          }
        }
        return prev;
      });
    }
  }

  // Auto-scroll on new content.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, typing]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setError(null);
    setDraft("");
    setPending(true);

    // Optimistic user message.
    setMessages((prev) => [
      ...prev,
      {
        id: nextMsgId(),
        role: "user",
        content: [{ type: "text", text, parse_mode: "plain" }],
      },
    ]);

    try {
      await sendMessage(sessionId, participantId, text);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Couldn't send your message.",
      );
    } finally {
      setPending(false);
    }
  }

  const inputDisabled =
    pending ||
    phase === "complete" ||
    phase === "in_permissions" ||
    phase === "in_addition_permissions" ||
    phase === "awaiting_consent" ||
    phase === "not_started";

  // Auto-focus the textarea any time it transitions to enabled — first
  // arrival in `in_conversation`, return after permissions, post-send
  // when `pending` clears, etc. Lets the participant just keep typing
  // without re-clicking after each send. Skipped while the textarea is
  // disabled (focusing a disabled field is a no-op anyway).
  useEffect(() => {
    if (!inputDisabled) {
      // Defer to next paint so we don't fight any concurrent re-render
      // that hasn't finished mounting/enabling the element yet.
      const id = window.requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
      return () => window.cancelAnimationFrame(id);
    }
  }, [inputDisabled]);

  const inputPlaceholder = (() => {
    if (phase === "complete") return "Session complete.";
    if (phase === "in_permissions" || phase === "in_addition_permissions")
      return "Tap one of the buttons above.";
    if (phase === "awaiting_addition") return "Type or send your addition…";
    if (phase === "not_started" || phase === "awaiting_consent")
      return "Tap the button above to begin.";
    return "Type your reply…";
  })();

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white/80 backdrop-blur px-6 py-3">
        <div className="text-sm font-medium text-neutral-900">{displayName}</div>
        <button
          type="button"
          onClick={onResetIdentity}
          className="text-xs text-neutral-500 hover:text-neutral-800"
          title="Switch identity (clears your local link to this conversation)"
        >
          Sign out
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-8">
        <div className="mx-auto max-w-2xl space-y-5">
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              sessionId={sessionId}
              participantId={participantId}
            />
          ))}
          {typing && (
            <div className="flex items-center gap-1.5 px-2">
              <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-neutral-400 [animation-delay:0ms]" />
              <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-neutral-400 [animation-delay:150ms]" />
              <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-neutral-400 [animation-delay:300ms]" />
            </div>
          )}
        </div>
      </div>

      <form
        onSubmit={handleSend}
        className="border-t border-neutral-200 bg-white px-4 py-3"
      >
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={inputDisabled}
            placeholder={inputPlaceholder}
            rows={2}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend(e);
              }
            }}
            className="flex-1 resize-none rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:bg-neutral-100 disabled:text-neutral-500"
          />
          <MicButton
            sessionId={sessionId}
            participantId={participantId}
            disabled={inputDisabled}
            onTranscribed={() => {
              /* Reply will arrive over SSE; nothing to do here. */
            }}
          />
          <button
            type="submit"
            disabled={inputDisabled || !draft.trim()}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
          >
            Send
          </button>
        </div>
        {error && (
          <div className="mx-auto mt-2 max-w-2xl text-xs text-red-600">
            {error}
          </div>
        )}
      </form>
    </div>
  );
}

function MessageBubble({
  message,
  sessionId,
  participantId,
}: {
  message: ChatMessage;
  sessionId: string;
  participantId: string;
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={[
          isUser
            ? "max-w-[85%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed bg-neutral-900 text-white"
            // Assistant messages render edge-to-edge within the
            // centered column, no card chrome — cleaner reading rhythm
            // and a feel closer to a long-form conversation than a
            // chatroom of stacked bubbles.
            : "max-w-full text-[15px] leading-relaxed text-neutral-800",
        ].join(" ")}
      >
        {message.content.map((part, i) => {
          if (part.type === "text") {
            return (
              <div
                key={i}
                className="whitespace-pre-wrap"
                dangerouslySetInnerHTML={{
                  __html: renderInlineMarkup(part.text, part.parse_mode === "html"),
                }}
              />
            );
          }
          if (part.type === "choice_prompt") {
            return (
              <ChoicePrompt
                key={i}
                sessionId={sessionId}
                participantId={participantId}
                text={part.text}
                parseMode={part.parse_mode}
                choices={part.choices}
                resolved={part.resolved}
                resolvedText={part.resolvedText}
              />
            );
          }
          return null;
        })}
      </div>
    </div>
  );
}

function renderInlineMarkup(s: string, allowHtml: boolean): string {
  if (allowHtml) {
    // Backend html parse_mode uses <b>/<i>; allow only those tags through.
    const escaped = s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped
      .replace(/&lt;b&gt;(.+?)&lt;\/b&gt;/gs, "<strong>$1</strong>")
      .replace(/&lt;i&gt;(.+?)&lt;\/i&gt;/gs, "<em>$1</em>");
  }
  // Plain text: just escape.
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
