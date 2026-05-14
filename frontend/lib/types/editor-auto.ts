/**
 * Tipos del programa Editor Auto. Reflejan `src/api/schemas/editor_auto/`.
 */

export interface ToolDescriptor {
  tool_id: string;
  display_name: string;
  description: string;
  position_weight: number;
  default_config: Record<string, unknown>;
  config_schema: ConfigSchemaField[];
}

export interface ConfigSchemaField {
  key: string;
  label: string;
  type: string; // "bool" | "int" | "float" | "string" | "text" | "select" | "color" | "preset_picker"
  options?: string[];
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
}

export interface ToolStep {
  tool_id: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface EditorUser {
  id: string;
  name: string;
  display_name: string;
  description: string;
  tool_flow: ToolStep[];
  drive_folder: string | null;
  output_folder: string | null;
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface EditorUserCreateInput {
  name: string;
  display_name?: string;
  description?: string;
  tool_flow?: ToolStep[];
}

export interface EditorUserUpdateInput {
  display_name?: string;
  description?: string;
  tool_flow?: ToolStep[];
}

export interface EditorAutoEnqueueResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
  input_path_relative: string;
  user_name: string;
  tool_count: number;
}
