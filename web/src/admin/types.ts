// Types mirror the admin REST API in src/circle/web/admin.py.

export type FieldType = "text" | "long_text" | "list_of_text";
export type ProcessorName = "synthesis" | "proposal" | "revise";

export interface FieldSchema {
  name: string;
  label: string;
  type: FieldType;
  required: boolean;
  default: unknown;
  description: string;
}

export interface WorkflowSchema {
  type: string;
  label: string;
  description: string;
  processor: ProcessorName;
  fields: FieldSchema[];
  ui: { side_panel?: string };
  // Code-defined defaults — what runs when no override is set.
  default_task_framing: string;
  default_output_template: string;
  default_mechanics: string;
  // Current admin overrides — empty string = no override (default applies).
  task_framing_override: string;
  output_template_override: string;
  mechanics_override: string;
}

// Partial-update body for PATCH /api/admin/workflow-types/{type}.
// Any omitted field is left unchanged. Empty string clears the override.
export interface WorkflowOverridesUpdate {
  task_framing?: string;
  output_template?: string;
  mechanics_override?: string;
}

export type FacilitationDepth = "minimal" | "medium" | "deep";

export interface CommonSettings {
  facilitator_model?: string;
  synthesis_model?: string;
  language?: string;
  facilitation_depth?: FacilitationDepth;
  // Reference into the Context Library (see /api/admin/contexts). Empty =
  // no community context attached. The synthesis/proposal/revise prompts
  // already handle empty context gracefully.
  community_context_id?: string;
}

export interface Context {
  id: string;
  name: string;
  text: string;
}

export interface TelegramStatus {
  // True when the running process owns a TelegramManager (i.e. it's
  // `circle.run`, not `circle.web`). False = hide the binding card.
  available: boolean;
  // Session id Telegram is currently routing to, or null if unbound.
  bound_session_id: string | null;
}

export interface WhisperSettings {
  model?: string;
  models_dir?: string;
}

export interface AdminSession {
  id: string;
  title: string;
  workflow_type: string;
  created_at: string;
  common: CommonSettings;
  whisper: WhisperSettings;
  workflow_data: Record<string, unknown>;
}

export interface OutputFileEntry {
  filename: string;
  bytes: number;
  created_at: string;
}

export interface ParticipantSummary {
  participant_id: string;
  participant_name: string;
  phase: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  num_turns: number;
  // Words this participant contributed across all their turns. Facilitator
  // turns excluded.
  participant_word_count: number;
  num_extracted_points: number;
  num_additions: number;
}

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

export interface ParticipantDetail {
  participant_id: string;
  participant_name: string;
  session_id: string;
  question: string;
  phase: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  transcript: TranscriptTurn[];
  extracted_points: ExtractedPoint[];
  additions: Addition[];
}
