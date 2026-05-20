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
  /** Si true, un watcher del backend encola automáticamente los vídeos
   *  nuevos en entrada/ del usuario. Polling cada 30s. */
  auto_enqueue: boolean;
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
  auto_enqueue?: boolean;
}

export interface EditorAutoEnqueueResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
  input_path_relative: string;
  user_name: string;
  tool_count: number;
}

// Las 4 carpetas que el cliente y el admin gestionan:
//   entrada       — cliente deposita aquí
//   cola          — vídeo bloqueado mientras procesa (admin no toca)
//   recuperacion  — original tras procesado OK (re-editable)
//   salida        — MP4 final que el cliente descarga
export type FolderName = "entrada" | "cola" | "recuperacion" | "salida";

export interface FolderFile {
  filename: string;
  folder: FolderName;
  ext: string;
  size_bytes: number;
  modified_at: number; // epoch seconds
  // Si en la misma carpeta existe `<stem>.txt`, el backend lo asocia
  // como guion companion. Para flows con `silence_cutter_scripted`, al
  // encolar el backend lee el .txt automáticamente.
  script: {
    filename: string;
    size_bytes: number;
    modified_at: number;
  } | null;
}

export interface FolderCounts {
  entrada: number;
  cola: number;
  recuperacion: number;
  salida: number;
}

export interface UserFoldersResponse {
  user_id: string;
  user_name: string;
  folders: Record<FolderName, FolderFile[]>;
  counts: FolderCounts;
}

export interface UserFolderCountsResponse {
  user_id: string;
  user_name: string;
  counts: FolderCounts;
}

export interface GlobalFolderCountsResponse {
  totals: FolderCounts;
  by_user: UserFolderCountsResponse[];
}

export interface MoveFileInput {
  src_folder: FolderName;
  dst_folder: FolderName;
  filename: string;
}

export interface MoveFileResponse {
  filename_new: string;
  src_folder: FolderName;
  dst_folder: FolderName;
  moved: boolean;
}

export interface EnqueueFromEntradaInput {
  filename: string;
  script?: string;
}

export interface EnqueueFromEntradaResponse {
  job_id: string;
  title: string;
  filename: string;
  moved: MoveFileResponse;
}

// Google Drive sharing — fase 2 con Service Account
export interface SharingStatus {
  configured: boolean;
  service_account_email: string | null;
}

export type ShareRole = "reader" | "commenter" | "writer";

export interface DriveShare {
  permission_id: string;
  email: string | null;
  role: ShareRole;
  type: string;
  display_name: string | null;
  folder_id: string;
}

export interface InheritedShare extends DriveShare {
  /** De qué carpeta padre se hereda — "TIKTOK_EDITOR" / "Usuarios" /
   *  el nombre del usuario. La UI lo muestra como read-only. */
  inherited_from: string;
}

export interface UserSharesResponse {
  user_id: string;
  user_name: string;
  shares: Record<FolderName, DriveShare[]>;
  /** Permisos heredados de carpetas padre (TIKTOK_EDITOR, Usuarios,
   *  <user>/). No se pueden revocar desde aquí — habría que tocar la
   *  carpeta padre directamente. */
  inherited_shares: InheritedShare[];
  /** Emails a los que el usuario ha dado acceso alguna vez (incluso si
   *  ahora no tienen ninguna carpeta compartida). Permite al UI mostrar
   *  filas re-utilizables sin re-tipear el gmail. */
  known_emails: string[];
}

export interface CreateShareInput {
  email: string;
  folders?: FolderName[];
  role?: ShareRole;
  notify?: boolean;
}

export interface CreateShareResponse {
  user_id: string;
  user_name: string;
  shared: {
    folder: FolderName;
    folder_id: string;
    permission_id: string;
    email: string;
    role: ShareRole;
    type: string;
    display_name: string | null;
  }[];
}
