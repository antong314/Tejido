import { useEffect, useRef, useState } from "react";
import { fetchState, sendMessage, subscribeEvents, ApiError } from "../api";
import { deriveInitialMessages } from "../derive_messages";
import type { ChatMessage, ContentPart, Phase, ServerEvent } from "../types";
import { ChoicePrompt } from "./ChoicePrompt";
import { DocumentPanel } from "./DocumentPanel";
import { MicButton } from "./MicButton";
import { SidePanel } from "./SidePanel";

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
  const [sidePanel, setSidePanel] = useState<{
    title: string;
    content_md: string;
    layout: "split" | "drawer";
  } | null>(null);
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
        setSidePanel(s.workflow_ui?.side_panel ?? null);
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

  // During the permissions walk-through, surface the participant's
  // progress as a thin terracotta bar at the top of the scroll area —
  // gives them a sense of "almost done" without yet another widget.
  // The "current" point is the one with no resolved permission yet.
  let permissionsProgress: { current: number; total: number } | null = null;
  if (phase === "in_permissions") {
    const total = messages.reduce(
      (acc, m) =>
        acc + m.content.filter((p) => p.type === "choice_prompt").length,
      0,
    );
    const resolvedCount = messages.reduce(
      (acc, m) =>
        acc +
        m.content.filter((p) => p.type === "choice_prompt" && p.resolved).length,
      0,
    );
    if (total > 0) {
      permissionsProgress = {
        current: Math.min(resolvedCount + 1, total),
        total,
      };
    }
  }

  // Extracted as local elements so the split and drawer layouts can both
  // reference them without duplicating the JSX. Both close over the same
  // state, so this stays cheap.
  const messagesScroll = (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-8">
      <div className="mx-auto max-w-[560px] space-y-5">
        {permissionsProgress && (
          <div className="pb-2">
            <div className="mb-2 text-[12px] font-medium text-p-ink-muted">
              Point {permissionsProgress.current} of {permissionsProgress.total}
            </div>
            <div className="h-[3px] w-full overflow-hidden rounded-sm bg-p-border">
              <div
                className="h-full rounded-sm bg-p-accent transition-[width] duration-[400ms] ease-out"
                style={{
                  width: `${
                    ((permissionsProgress.current - 1) /
                      permissionsProgress.total) *
                    100
                  }%`,
                }}
              />
            </div>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            sessionId={sessionId}
            participantId={participantId}
          />
        ))}
        {typing && (
          // Three bouncing dots. Animations are defined in tailwind.config.js
          // as named delays so we don't need arbitrary [animation-delay:...]
          // values here.
          <div className="flex items-center gap-1.5 px-2">
            <span className="inline-block h-2 w-2 animate-bounce-dot-1 rounded-full bg-p-ink-faint" />
            <span className="inline-block h-2 w-2 animate-bounce-dot-2 rounded-full bg-p-ink-faint" />
            <span className="inline-block h-2 w-2 animate-bounce-dot-3 rounded-full bg-p-ink-faint" />
          </div>
        )}
      </div>
    </div>
  );

  const inputForm = (
    <form
      onSubmit={handleSend}
      className="border-t border-p-border bg-p-bg-card px-6 pb-4 pt-3"
    >
      <div className="mx-auto flex max-w-[560px] items-end gap-2">
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
          className="flex-1 resize-none rounded-md border-[1.5px] border-p-border bg-p-bg px-3.5 py-2.5 text-[14px] leading-[1.5] text-p-ink outline-none transition-[border-color,box-shadow] placeholder:text-p-ink-faint focus:border-p-border-focus focus:shadow-[0_0_0_3px_var(--p-accent-tint)] disabled:bg-p-bg-subtle disabled:text-p-ink-faint"
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
          className="h-11 rounded-md bg-p-accent px-[18px] text-[13px] font-medium text-white transition-colors hover:bg-p-accent-dark disabled:cursor-default disabled:opacity-50"
        >
          Send
        </button>
      </div>
      {error && (
        <div className="mx-auto mt-2 max-w-[560px] text-xs text-pill-private">
          {error}
        </div>
      )}
    </form>
  );

  const isSplit = sidePanel?.layout === "split";

  // The completion phase replaces the chat entirely with a calm
  // full-viewport thank-you screen. The transcript stays in the
  // session's data dir if the participant ever needs to reference what
  // they said, but the UI doesn't dwell on it.
  if (phase === "complete") {
    return <CompletionScreen displayName={displayName} onResetIdentity={onResetIdentity} />;
  }

  return (
    <div className="flex h-full flex-col bg-p-bg">
      <header className="flex h-12 items-center justify-between border-b border-p-border bg-[oklch(98.5%_0.006_75/0.9)] px-6 backdrop-blur">
        <div className="text-[13px] font-medium text-p-ink">{displayName}</div>
        <button
          type="button"
          onClick={onResetIdentity}
          className="text-[12px] text-p-ink-faint transition-colors hover:text-p-ink-muted"
          title="Switch identity (clears your local link to this conversation)"
        >
          Sign out
        </button>
      </header>

      {isSplit && sidePanel ? (
        // Split layout: document permanently on the left, chat column
        // (messages + input) on the right. Both columns scroll
        // independently. Used by document_revision so the participant
        // never loses sight of the doc they're reacting to.
        <div className="flex flex-1 overflow-hidden">
          <DocumentPanel
            title={sidePanel.title}
            contentMd={sidePanel.content_md}
          />
          <div className="flex flex-1 flex-col overflow-hidden">
            {messagesScroll}
            {inputForm}
          </div>
        </div>
      ) : (
        // Drawer layout (default): chat fills the viewport with the input
        // bar spanning the full width. Optional collapsible side panel
        // overlays from the right.
        <>
          <div className="relative flex flex-1 overflow-hidden">
            {messagesScroll}
            {sidePanel && (
              <SidePanel
                title={sidePanel.title}
                contentMd={sidePanel.content_md}
              />
            )}
          </div>
          {inputForm}
        </>
      )}
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
    <div className={`flex animate-fade-in ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={[
          isUser
            // User: dark warm-charcoal bubble with the iMessage-style
            // pinched bottom-right corner. Uses inline arbitrary radius
            // because Tailwind doesn't have asymmetric rounded utilities.
            ? "max-w-[82%] rounded-[20px_20px_4px_20px] bg-p-bubble-user px-4 py-3 text-[15px] leading-[1.65] text-p-bubble-text"
            // Assistant: edge-to-edge plain text, no bubble — feels
            // closer to long-form conversation than a chatroom of
            // stacked bubbles.
            : "max-w-full text-[15px] leading-[1.75] text-p-ink",
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
          if (part.type === "question_callout") {
            return (
              <div
                key={i}
                className="my-1 rounded-md border-l-[3px] border-p-accent bg-p-bg-card px-5 py-4 font-p-display text-[17px] italic leading-snug text-p-ink"
              >
                {part.text}
              </div>
            );
          }
          return null;
        })}
      </div>
    </div>
  );
}

// Completion screen — shown when phase === "complete". Replaces the
// chat entirely so the participant gets a clean exit signal instead of
// staring at a frozen disabled input. Calm, centered, terracotta wave
// motif as a small visual punctuation.
function CompletionScreen({
  displayName,
  onResetIdentity,
}: {
  displayName: string;
  onResetIdentity: () => void;
}) {
  return (
    <div className="flex h-full flex-col bg-p-bg">
      <header className="flex h-12 items-center justify-between border-b border-p-border bg-[oklch(98.5%_0.006_75/0.9)] px-6 backdrop-blur">
        <div className="text-[13px] font-medium text-p-ink">{displayName}</div>
        <button
          type="button"
          onClick={onResetIdentity}
          className="text-[12px] text-p-ink-faint transition-colors hover:text-p-ink-muted"
          title="Switch identity (clears your local link to this conversation)"
        >
          Sign out
        </button>
      </header>
      <div className="flex flex-1 items-center justify-center px-8 text-center">
        <div className="max-w-[440px]">
          {/* Three crossing wave paths in terracotta — a small
              visual punctuation, matches the brand's "weaving" metaphor. */}
          <svg
            width="68"
            height="48"
            viewBox="0 0 68 48"
            fill="none"
            className="mx-auto mb-6"
            aria-hidden="true"
          >
            <path
              d="M2 32 Q 17 12, 34 24 T 66 16"
              stroke="var(--p-accent)"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.85"
            />
            <path
              d="M2 24 Q 17 36, 34 24 T 66 32"
              stroke="var(--p-accent)"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.55"
            />
            <path
              d="M2 16 Q 17 28, 34 16 T 66 24"
              stroke="var(--p-accent)"
              strokeWidth="2"
              strokeLinecap="round"
              opacity="0.35"
            />
          </svg>

          <h1 className="font-p-display text-[30px] font-normal leading-tight tracking-[-0.3px] text-p-ink">
            That's it. Thank you.
          </h1>
          <p className="mt-3 text-[15px] leading-[1.7] text-p-ink-muted">
            We'll come back together when everyone has finished. Your
            choices about what's shared have been recorded — only what
            you said could be shared will be.
          </p>
          <p className="mt-6 text-[13px] text-p-ink-faint">
            You can close this tab.
          </p>
        </div>
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
