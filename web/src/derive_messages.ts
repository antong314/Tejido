// Pure function: given the persisted ParticipantState, produce the
// initial list of ChatMessages the UI should render on load. Mirrors the
// "render_state.py" sketch from earlier planning — kept on the frontend
// because it's pure UI logic and only the frontend cares about the
// ChatMessage shape.
//
// The state machine awareness lives here: depending on phase, we
// reconstruct the unanswered prompt the user should be looking at when
// they reopen the page mid-flow.

import type {
  ChatMessage,
  ContentPart,
  ExtractedPoint,
  StateResponse,
} from "./types";

const PERMISSION_LABELS: Record<string, string> = {
  attributed: "By name",
  anonymous: "Anonymous",
  private: "Private",
};

const PERMISSION_GLYPHS: Record<string, string> = {
  attributed: "✓ By name",
  anonymous: "✓ Anonymous",
  private: "✓ Private",
};

let _id = 0;
const nextId = () => `msg-${++_id}`;

function pointPrompt(
  point: ExtractedPoint,
  index: number,
  total: number,
): ContentPart {
  const text = `**${index + 1} of ${total}**\n\n${point.point}`;
  if (point.permission) {
    return {
      type: "choice_prompt",
      text,
      parse_mode: "html",
      choices: [],
      resolved: true,
      resolvedText: `${text}\n\n${PERMISSION_GLYPHS[point.permission]}`,
    };
  }
  return {
    type: "choice_prompt",
    text,
    parse_mode: "html",
    choices: [
      { label: PERMISSION_LABELS.attributed, callback_data: `perm:${index}:attributed` },
      { label: PERMISSION_LABELS.anonymous, callback_data: `perm:${index}:anonymous` },
      { label: PERMISSION_LABELS.private, callback_data: `perm:${index}:private` },
    ],
    resolved: false,
    resolvedText: null,
  };
}

export function deriveInitialMessages(state: StateResponse): ChatMessage[] {
  const messages: ChatMessage[] = [];

  // 1. Transcript → text bubbles.
  for (const turn of state.transcript) {
    messages.push({
      id: nextId(),
      role: turn.role,
      content: [
        { type: "text", text: turn.content, parse_mode: "plain" },
      ],
    });
  }

  // 2. If we're mid-flow, reconstruct the active prompt.
  switch (state.phase) {
    case "awaiting_consent":
      messages.push({
        id: nextId(),
        role: "assistant",
        content: [
          {
            type: "choice_prompt",
            text: state.question,
            parse_mode: "plain",
            choices: [
              { label: "I'm ready, let's begin", callback_data: "consent:ready" },
            ],
            resolved: false,
            resolvedText: null,
          },
        ],
      });
      break;

    case "in_permissions": {
      const total = state.extracted_points.length;
      // Show every point with its current state — answered points show
      // their resolved choice; unanswered ones show buttons.
      for (let i = 0; i < total; i++) {
        const point = state.extracted_points[i];
        messages.push({
          id: nextId(),
          role: "assistant",
          content: [pointPrompt(point, i, total)],
        });
      }
      break;
    }

    case "awaiting_addition":
      messages.push({
        id: nextId(),
        role: "assistant",
        content: [
          {
            type: "choice_prompt",
            text: "Is there anything else you'd like to add that didn't come up?",
            parse_mode: "plain",
            choices: [
              { label: "Yes, I want to add something", callback_data: "add:yes" },
              { label: "No, I'm done", callback_data: "add:no" },
            ],
            resolved: false,
            resolvedText: null,
          },
        ],
      });
      break;

    case "in_addition_permissions": {
      const last = state.additions[state.additions.length - 1];
      if (last) {
        messages.push({
          id: nextId(),
          role: "assistant",
          content: [
            {
              type: "choice_prompt",
              text: `**Your addition**\n\n${last.content}\n\nHow should this be shared with the group?`,
              parse_mode: "html",
              choices: last.permission
                ? []
                : [
                    { label: PERMISSION_LABELS.attributed, callback_data: "addperm:attributed" },
                    { label: PERMISSION_LABELS.anonymous, callback_data: "addperm:anonymous" },
                    { label: PERMISSION_LABELS.private, callback_data: "addperm:private" },
                  ],
              resolved: !!last.permission,
              resolvedText: last.permission
                ? `**Your addition**\n\n${last.content}\n\n${PERMISSION_GLYPHS[last.permission]}`
                : null,
            },
          ],
        });
      }
      break;
    }

    case "complete":
      messages.push({
        id: nextId(),
        role: "assistant",
        content: [
          {
            type: "text",
            text: "That's it. Thank you. We'll come back together in the circle when everyone has finished.",
            parse_mode: "plain",
          },
        ],
      });
      break;

    case "not_started":
    case "in_conversation":
      // No reconstructed prompt — the next thing happens via SSE
      // when the user types or the controller advances.
      break;
  }

  return messages;
}
