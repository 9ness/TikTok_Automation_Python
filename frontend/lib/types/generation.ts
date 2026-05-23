/**
 * Tipos de generaciones de vídeo (TikTok Shop). Reflejan
 * `src/api/schemas/generation.py`.
 */

import type { Tier } from "./product";

export type StrategyValue = "cinematic" | "dynamic";

export interface ClipPhotoOverride {
  clip_idx: number;
  photo_index: number;
}

// Fase 3 — overlays componibles
export interface HookBoxOverlay {
  enabled: boolean;
  text?: string | null;
  animation?: string;
  duration?: number;
  y_position_pct?: number;
  text_color?: string;
  box_color?: string;
  shadow_color?: string;
  font_path?: string | null;
  font_scale?: number;
}

export interface CtaArrowOverlay {
  enabled: boolean;
  sticker_file?: string | null;
  position_x_pct?: number;
  position_y_pct?: number;
  scale_width_pct?: number;
  rotation_deg?: number;
  flip_horizontal?: boolean;
  flip_vertical?: boolean;
  duration_seconds?: number;
  fallback_last_seconds?: number;
}

export interface OverlaysConfig {
  hook_box: HookBoxOverlay;
  cta_arrow: CtaArrowOverlay;
}

export interface EnqueueRequest {
  username: string;
  product_id: string;
  tier: Tier;
  duration_seconds: number;
  resolution: string;
  strategy: StrategyValue;
  voice_enabled: boolean;
  voice_id: string | null;
  hook_category: string;
  hook_custom?: string | null;
  target_audience: string;
  shoppable: boolean;
  ai_disclosure?: boolean;
  n_angles?: number | null;
  clip_photo_overrides?: ClipPhotoOverride[] | null;
  pro_ref_photo_overrides?: number[] | null;
  overlays?: OverlaysConfig | null;
  /** Estilo de subtítulos del preset (size_px, color, highlight_color,
   *  margin_x_pct, position, uppercase, etc.). Pass-through al backend. */
  subtitle_style?: Record<string, unknown> | null;
}

export interface EnqueueResponse {
  job_id: string;
  estimated_cost: number;
  estimated_duration_seconds: number;
  position_in_queue: number;
}

export type GenerationStatusValue =
  | "pending"
  | "generating"
  | "completed"
  | "manual_pending"
  | "manual_completed"
  | "failed";

export interface GenerationResponse {
  id: string;
  user_id: string;
  product_id: string;
  tier_used: Tier;
  duration_seconds: number;
  resolution: string;
  generation_status: GenerationStatusValue;
  cost: { total: number; video_generation: number; voice_tts: number };
  created_at: string;
  completed_at: string | null;
  drive_url: string | null;
  local_path: string | null;
  deleted: boolean;
  // Campos extra del response que el frontend puede ignorar
  [key: string]: unknown;
}

export interface GenerationListResponse {
  items: GenerationResponse[];
  total: number;
  limit: number;
  offset: number;
}
