// Shapes mirror the Python backend (see src/circle/web/render_action.py and
// src/circle/web/app.py). Keep these in sync with the backend's JSON output.

export type ParseMode = "plain" | "html";

export interface Choice {
  label: string;
  callback_data: string;
}

// SSE events — what the server pushes to /api/p/{id}/events
export type ServerEvent =
  | { type: "text"; text: string; parse_mode: ParseMode }
  | {
      type: "choice_prompt";
      text: string;
      parse_mode: ParseMode;
      choices: Choice[];
    }
  | { type: "resolve_choice"; text: string | null; parse_mode: ParseMode }
  | { type: "typing" }
  // Emitted by the web adapter after every controller drain so the
  // frontend's input-enabled state stays in sync with the state machine.
  | { type: "phase_update"; phase: Phase }
  // Echoes a user-side input so it renders as a chat bubble. Currently
  // only emitted on the voice path (text path is optimistically added
  // by the sender's own client). `via` distinguishes how the input was
  // produced — same field name as the on-disk transcript turn.
  | { type: "user_message"; text: string; via: "text" | "voice" };

// REST: GET /api/p/{id}/state
export interface StateResponse {
  participant_id: string;
  participant_name: string;
  session_id: string;
  question: string;
  phase: Phase;
  transcript: TranscriptTurn[];
  extracted_points: ExtractedPoint[];
  additions: Addition[];
  status: string;
  started_at: string | null;
  completed_at: string | null;
}

export type Phase =
  | "not_started"
  | "awaiting_consent"
  | "in_conversation"
  | "in_permissions"
  | "awaiting_addition"
  | "in_addition_permissions"
  | "complete";

export interface TranscriptTurn {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  via?: "text" | "voice";
  detected_language?: string | null;
}

export interface ExtractedPoint {
  point: string;
  permission: "attributed" | "anonymous" | "private" | null;
  index: number;
}

export interface Addition {
  content: string;
  permission: "attributed" | "anonymous" | "private" | null;
}

// Client-side message model — what the chat UI renders.
export type ContentPart =
  | { type: "text"; text: string; parse_mode: ParseMode }
  | {
      type: "choice_prompt";
      text: string;
      parse_mode: ParseMode;
      choices: Choice[];
      // resolved=true means the user (or another tab) has answered;
      // we render the resolvedText in place of the buttons.
      resolved: boolean;
      resolvedText: string | null;
    };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: ContentPart[];
}

// REST: POST /api/s/{id}/join
export interface JoinResponse {
  participant_id: string;
  display_name: string;
}

export interface ApiErrorBody {
  detail: { code: string; error: string };
}
