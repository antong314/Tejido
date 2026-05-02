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
  default_persona: string;
  processor: ProcessorName;
  fields: FieldSchema[];
  ui: { side_panel?: string };
}

export type FacilitationDepth = "minimal" | "medium" | "deep";

export interface CommonSettings {
  facilitator_model?: string;
  synthesis_model?: string;
  language?: string;
  facilitation_depth?: FacilitationDepth;
  // Slug reference into a Persona (see /api/admin/personas). Empty = use
  // the workflow type's default_persona.
  ai_persona_id?: string;
}

export interface Persona {
  id: string;
  name: string;
  prompt: string;
  description: string;
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
