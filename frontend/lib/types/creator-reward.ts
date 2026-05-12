/**
 * Tipos del módulo Creator Reward (4 nichos).
 * Reflejan `src/api/schemas/creator_reward/*.py`.
 */

// ---------------------------------------------------------------------------
// Presidentes
// ---------------------------------------------------------------------------
export type PrefixWord = "The" | "Top";
export type TopCount = 3 | 4 | 5;
export type ResolutionLabel =
  | "1080p (Lento)"
  | "720p (Medio)"
  | "480p (Rápido)"
  | "240p (Ultra Rápido)";
export type EngineVersion = "v1_estable" | "v2_estable";

export interface PresidentsItem {
  topic?: string | null;
  prefix: PrefixWord;
  top_count: TopCount;
  include_history: boolean;
  include_hook: boolean;
}

export interface PresidentsSubsConfig {
  enabled: boolean;
  font_choice: string;
  highlight_color: string;
  text_color: string;
  stroke_color: string;
  stroke_width: number;
  case_mode: "UPPERCASE" | "lowercase" | "Title Case" | "None";
  font_scale: number;
  max_words: number;
  y_position: number;
  shadow_enabled: boolean;
  shadow_color: string;        // hex
  shadow_opacity: number;      // 0-1
  shadow_blur: number;         // 0-100 (% — convertido a px por backend)
  shadow_distance: number;     // 0-100 (CapCut units, en px sobre 1920)
  shadow_angle: number;        // grados (CapCut: -45 = abajo-derecha)
  highlight_mode: "pill" | "color_swap" | "underline" | "box_outline" | "glow" | "none";
  max_width: number;
}

export interface PresidentsHookConfig {
  enabled: boolean;
  duration: number;
  animation: "swipe_left" | "swipe_right" | "fade_in" | "pop" | "none";
  y_position: number;
  shadow_color: string;
  box_color: string;
  text_color: string;
  font_scale: number;
}

export interface PresidentsEnqueueRequest {
  items: PresidentsItem[];
  creative_mode: boolean;
  engine_version: EngineVersion;
  resolution: ResolutionLabel;
  subs: PresidentsSubsConfig;
  hook: PresidentsHookConfig;
}

export interface PresidentsBatchEnqueueResponse {
  jobs: Array<{ job_id: string; position_in_queue: number; title: string }>;
  total_enqueued: number;
}

// ---------------------------------------------------------------------------
// Pronósticos
// ---------------------------------------------------------------------------
export interface PronosticosVersionItem {
  id: string;
  trigger: string | null;
  mode: string | null;
  word_count: number | null;
  estimated_duration_s: number | null;
  picks_count: number;
  script: string;
  title: string | null;
  competition_focus: string | null;
  is_selected: boolean;
}

export interface PronosticosVersionsResponse {
  date: string;
  payload_exists: boolean;
  versions: PronosticosVersionItem[];
  selected_version_id: string | null;
}

export interface PronosticosLatestDateResponse {
  latest_date: string | null;
}

export interface PronosticosAudioConfig {
  add_subtitles: boolean;
  add_money_sfx: boolean;
  sfx_volume: number;
  add_clink_sfx: boolean;
  clink_volume: number;
  add_camera_sfx: boolean;
  camera_volume: number;
  add_background_music: boolean;
  bgm_volume: number;
}

export interface PronosticosOverlaysConfig {
  use_intro_folder: boolean;
  add_league_overlay: boolean;
  league_overlay_duration: number;
  saturation: number;
  show_pick_carousel: boolean;
  // Posiciones configurables vía preview drag (0..1).
  subtitle_y_pct: number;
  league_overlay_y_pct: number;
  league_logo_height_pct: number;
  team_shield_y_pct: number;
  team_shield_height_pct: number;
  team_shield_x_inset_pct: number;
  profile_cta_y_pct: number;
  profile_cta_height_pct: number;
}

export interface PronosticosEnqueueRequest {
  target_date: string;
  version_ids: string[];
  voice_id_override?: string | null;
  script_overrides?: Record<string, string>;
  video_size?: [number, number];
  publish_to_redis?: boolean;
  audio?: Partial<PronosticosAudioConfig>;
  overlays?: Partial<PronosticosOverlaysConfig>;
}

export interface PronosticosBatchEnqueueResponse {
  jobs: Array<{ job_id: string; version_id: string; title: string }>;
  total_enqueued: number;
}

// ---------------------------------------------------------------------------
// Copyright
// ---------------------------------------------------------------------------
export type CleanModeValue =
  | "Subtítulos Virales"
  | "Camuflaje Geométrico (Sin Subtítulos)";

export interface CopyrightEnqueueResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
  input_path_relative: string;
}

// ---------------------------------------------------------------------------
// Subs Auto
// ---------------------------------------------------------------------------
export interface SubsAutoWord {
  word: string;
  start: number;
  end: number;
}

export interface SubsAutoTranscribeResponse {
  input_path_relative: string;
  out_path_relative: string;
  words: SubsAutoWord[];
  quality_label: string;
  model_size: string;
  language: string | null;
  audio_type: string;
}

export type SubsAutoHighlightMode =
  | "pill"
  | "color_swap"
  | "underline"
  | "box_outline"
  | "glow"
  | "none";

export type SubsAutoCaseMode = "UPPERCASE" | "lowercase" | "Title Case" | "None";

export interface SubsAutoStyleConfig {
  font_path: string;
  highlight_mode: SubsAutoHighlightMode;
  highlight_color: string;
  text_color: string;
  stroke_color: string;
  stroke_width: number;
  case_mode: SubsAutoCaseMode;
  font_scale: number;
  max_words: number;
  y_position: number;
  pill_enabled: boolean;
  max_width: number;
  sync_offset: number;
}

export interface SubsAutoEnqueueRequest {
  input_path: string;
  out_path: string;
  edited_text?: string | null;
  reference_text?: string | null;
  model_size: string;
  language?: string | null;
  audio_type: string;
  quality_label: string;
  style: SubsAutoStyleConfig;
}

export interface SubsAutoEnqueueResponse {
  job_id: string;
  position_in_queue: number;
}
