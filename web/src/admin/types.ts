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

export interface CommonSettings {
  facilitator_model?: string;
  synthesis_model?: string;
  language?: string;
  expected_duration_minutes?: number;
  ai_persona?: string;
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
