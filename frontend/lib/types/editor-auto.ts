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

// =============================================================
// Billing (Planes / Suscripciones / Referidos)
// =============================================================

export interface Plan {
  id: string;
  slug: string;
  name: string;
  description: string;
  daily_video_limit: number;
  monthly_video_limit: number | null;
  allowed_tools: string[];
  processing_window_start_hour: number;
  processing_window_end_hour: number;
  spacing_minutes: number;
  queue_priority: number;
  queue_delay_minutes: number;
  support_level: string;
  features: string[];
  price_eur_monthly: number;
  price_eur_setup_once: number;
  is_active: boolean;
  is_promo: boolean;
  promo_slots_total: number | null;
  promo_slots_used: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface PlanCreateInput {
  slug: string;
  name: string;
  description?: string;
  daily_video_limit?: number;
  monthly_video_limit?: number | null;
  allowed_tools?: string[];
  processing_window_start_hour?: number;
  processing_window_end_hour?: number;
  spacing_minutes?: number;
  queue_priority?: number;
  queue_delay_minutes?: number;
  support_level?: string;
  features?: string[];
  price_eur_monthly?: number;
  price_eur_setup_once?: number;
  is_active?: boolean;
  is_promo?: boolean;
  promo_slots_total?: number | null;
  sort_order?: number;
}

export interface PlanUpdateInput {
  name?: string;
  description?: string;
  daily_video_limit?: number;
  monthly_video_limit?: number | null;
  allowed_tools?: string[];
  processing_window_start_hour?: number;
  processing_window_end_hour?: number;
  spacing_minutes?: number;
  queue_priority?: number;
  queue_delay_minutes?: number;
  support_level?: string;
  features?: string[];
  price_eur_monthly?: number;
  price_eur_setup_once?: number;
  is_active?: boolean;
  is_promo?: boolean;
  promo_slots_total?: number | null;
  promo_slots_used?: number;
  sort_order?: number;
}

export interface Subscription {
  plan_id: string;
  plan_slug: string;
  plan_name: string;
  status: string;
  started_at: string;
  current_period_start: string;
  current_period_end: string | null;
  discount_pct_next_period: number;
  notes: string;
}

export interface UsageStats {
  daily_videos_used: number;
  monthly_videos_used: number;
  total_videos_ever: number;
  last_reset_date: string;
  month_period: string;
  last_enqueue_at: string | null;
  daily_limit: number | null;
  monthly_limit: number | null;
}

export interface SubscriptionAssignInput {
  plan_id: string;
  status?: string;
  notes?: string;
  started_at?: string | null;
  discount_pct_next_period?: number;
}

export interface ReferralUse {
  referred_user_id: string;
  referred_user_name: string;
  used_at: string;
  discount_pct_applied: number;
  valid_until_period: string | null;
}

export interface ReferralCode {
  code: string;
  owner_user_id: string;
  owner_user_name: string;
  uses: ReferralUse[];
  created_at: string;
  active_uses_count: number;
  accumulated_discount_pct_next_period: number;
}

// =============================================================

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
  /** Cuenta atrás (min) antes de auto-encolar un vídeo nuevo. 0 = sin
   *  espera extra (solo el min-age global anti-uploads). */
  auto_enqueue_delay_minutes: number;
  /** Máx vídeos/día para este usuario (cuenta atrás). null = sin límite
   *  propio (usa el del plan, o ilimitado si no tiene plan). */
  daily_video_limit_override: number | null;
  window_start_hour_override: number | null;
  window_end_hour_override: number | null;
  subscription: Subscription | null;
  usage: UsageStats | null;
  referral_code: string | null;
  referred_by_code: string | null;
  referrals_count: number;
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface EditorUserCreateInput {
  name: string;
  display_name?: string;
  description?: string;
  tool_flow?: ToolStep[];
  referred_by_code?: string;
}

export interface EditorUserUpdateInput {
  display_name?: string;
  description?: string;
  tool_flow?: ToolStep[];
  auto_enqueue?: boolean;
  auto_enqueue_delay_minutes?: number;
  /** -1 = limpiar override (sin límite propio). */
  daily_video_limit_override?: number;
  window_start_hour_override?: number;
  window_end_hour_override?: number;
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
