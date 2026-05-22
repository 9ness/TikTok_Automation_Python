/**
 * Tipos TypeScript que reflejan los schemas de la API FastAPI.
 * Mantén sincronizado con `src/api/schemas/product.py`.
 */

export type Tier =
  | "standard"
  | "advanced"
  | "pro"
  | "veo3_prompt_only"
  | "nano_banana_prompt_only";

export type PhotoLocation = "source" | "generated";
export type PhotoType = "packshot" | "lifestyle" | "detail" | "in_use" | "macro";
export type PhotoOrigin = "internet" | "own" | "tiktok_shop_url";

export interface ProductPhoto {
  filename: string;
  local_path: string | null;
  drive_file_id: string | null;
  type: PhotoType | null;
  preferred_for_tiers: string[];
  origin: PhotoOrigin | null;
  url_origin: string | null;
  added_at: string | null;
  generation_prompt_used: string | null;
  generated_at: string | null;
  deleted: boolean;
}

export interface ProductPhotos {
  source: ProductPhoto[];
  generated: ProductPhoto[];
}

export interface TikTokShopMeta {
  product_url: string | null;
  product_id: string | null;
  commission_rate: number;
  price_eur: number | null;
}

export interface VoicePreference {
  type: "tts_preset" | "voice_clone";
  voice_id: string | null;
  tone: "energetic" | "calm" | "informative";
}

export interface VideoConfig {
  default_tier: Tier;
  default_duration: number;
  default_resolution: string;
  preferred_styles: string[];
  voice_preference: VoicePreference;
  has_complex_packaging: boolean;
  use_first_frame_anchor: boolean;
}

export interface Hook {
  category: string;
  template: string;
  performance_score: number | null;
}

export interface PerformanceHistory {
  total_videos_generated: number;
  total_orders_generated: number;
  best_hook_category: string | null;
  promoted_to_advanced_at: string | null;
  promoted_to_pro_at: string | null;
}

export interface Product {
  id: string;
  slug: string;
  name: string;
  brand: string | null;
  category: string;
  subcategory: string | null;
  target_audience: string[];
  key_features: string[];
  selling_points: string[];
  tiktok_shop: TikTokShopMeta;
  photos: ProductPhotos;
  video_config: VideoConfig;
  hooks_library: Hook[];
  /** Presets de vídeo precocinados (música + scripted). Generables con
   *  Gemini desde el tab Presets del producto. */
  video_presets: VideoPreset[];
  /** "high" | "medium" | "low" | "" — última evaluación de calidad
   *  de las fotos source por Gemini Vision. */
  photos_quality_assessment: string;
  /** Lista de motivos/avisos del último análisis (explica por qué se
   *  marcó packaging complejo, needs nano banana, etc). */
  last_analysis_warnings: string[];
  performance_history: PerformanceHistory;
  needs_nano_banana_regeneration: boolean;
  drive_folder: string | null;
  deleted: boolean;
  last_analyzed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductListResponse {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProductCreateInput {
  name: string;
  slug?: string;
  brand?: string | null;
  category?: string;
  subcategory?: string | null;
  target_audience?: string[];
  key_features?: string[];
  selling_points?: string[];
  tiktok_shop?: Partial<TikTokShopMeta>;
  default_tier?: Tier;
  default_duration?: number;
  default_resolution?: string;
  analyze_with_gemini?: boolean;
  /** Si viene, backend descarga esta imagen tras crear y la añade como
   *  primera foto source (packshot). Pensado para auto-completar productos
   *  creados desde URL TikTok Shop con la og:image detectada. */
  image_url_to_download?: string | null;
}

export type ProductUpdateInput = Partial<ProductCreateInput> & {
  // Campos extra que el backend acepta vía PUT pero que no son parte del
  // ProductCreateInput estricto (vienen como pass-through al modelo Pydantic).
  hooks_library?: Hook[];
  voice_preference?: VoicePreference;
  preferred_styles?: string[];
};

export interface PhotoUpdateInput {
  type?: PhotoType | null;
  preferred_for_tiers?: string[];
}

export interface ReanalyzeResponse {
  product_id: string;
  analyzed_at: string;
  key_features: string[];
  suggested_audiences: string[];
  selling_points: string[];
  has_complex_packaging_text: boolean;
  needs_nano_banana_regeneration: boolean;
  warnings: string[];
  raw: Record<string, unknown>;
}

export interface NanoBananaPromptInput {
  photo_types_wanted: PhotoType[];
  n_angles?: number;
}

export interface NanoBananaPromptResponse {
  product_id: string;
  prompt: string;
  instructions: string;
}

export interface AnalyzeUrlPreviewInput {
  url?: string;
  /** Texto libre pegado por el user (título, descripción, share text del
   *  móvil…). Al menos UNO de los dos (url / raw_text) debe ir relleno. */
  raw_text?: string;
  use_gemini?: boolean;
}

export interface AnalyzeUrlPreviewResponse {
  name: string | null;
  brand: string | null;
  description: string | null;
  category: string | null;
  subcategory: string | null;
  price_eur: number | null;
  currency: string | null;
  image_url: string | null;
  warnings: string[];
}

// --- Importar fotos por URL + grading -------------------------
export interface PhotoCandidateGrade {
  candidate_id: string;
  url: string;
  score: number; // 0-10
  type: PhotoType | "other";
  /** Si el producto ya tenía fotos, Gemini comparó y decidió si es
   *  el mismo SKU. Si false, el score está capado a 3 = descartable. */
  is_same_product: boolean;
  same_product_confidence: "high" | "medium" | "low" | "no_reference";
  /** True si el candidato es el mismo plano que una foto de referencia
   *  (mismo ángulo, composición, fondo). El score ya viene -3 capado;
   *  la UI también muestra badge "duplicado" para no marcarla. */
  is_duplicate_of_reference: boolean;
  is_branded: boolean;
  has_text_overlay: boolean;
  has_watermark: boolean;
  is_collage: boolean;
  shows_product_clearly: boolean;
  reasons: string;
  preview_url: string;
  error?: string | null;
}

export interface ImportPhotosFromUrlsInput {
  urls: string[];
}

export interface ImportPhotosFromUrlsResponse {
  product_id: string;
  candidates: PhotoCandidateGrade[];
}

export interface CommitImportedPhotoItem {
  candidate_id: string;
  type?: PhotoType | null;
}

export interface CommitImportedPhotosInput {
  candidates: CommitImportedPhotoItem[];
}

export interface CommitImportedPhotosResponse {
  product_id: string;
  saved_count: number;
  skipped: string[];
}

export interface GoogleImageSearchInput {
  query?: string;
  num?: number;
  /** Provider: "auto" (DDG primero, fallback CSE), "ddg", "google" */
  provider?: "auto" | "ddg" | "google";
}

export interface GoogleImageSearchResultItem {
  link: string;
  title: string;
}

export interface GoogleImageSearchResponse {
  configured: boolean;
  provider_used: "ddg" | "google_cse" | "none";
  query_used: string;
  results: GoogleImageSearchResultItem[];
  hint: string;
}

// --- Video Presets -------------------------
export type PresetKind = "music" | "scripted";

export const TEXT_OVERLAY_POSITIONS = [
  "top_center", "top_left", "top_right",
  "middle_center", "middle_left", "middle_right",
  "bottom_center", "bottom_left", "bottom_right",
] as const;

export const TEXT_OVERLAY_ANIMATIONS = [
  "none", "fade_in", "slide_up", "slide_down", "pop", "typing",
  "shake", "bounce",
] as const;

export interface TextOverlayStyle {
  font: string;          // path absoluto del registry o vacío (default)
  size_px: number;
  color: string;
  stroke_color: string;
  stroke_width: number;
  position: string;
  animation: string;
  uppercase: boolean;
  background: string; // "none" | "black_bar" | "blur"
  /** Segundos que el hook permanece en pantalla (default 4s = stop-scroll). */
  duration_s: number;
}

export interface SubtitleStyle {
  enabled: boolean;
  font: string;
  size_px: number;
  color: string;
  stroke_color: string;
  stroke_width: number;
  position: string;
  highlight_color: string;
  max_words_per_line: number;
  uppercase: boolean;
  animation: string;
}

export interface CtaArrowStyle {
  enabled: boolean;
  sticker_file: string;        // "flecha_negra.mov" | "flecha_roja.mov"
  position_x_pct: number;
  position_y_pct: number;
  scale_width_pct: number;
  rotation_deg: number;
  flip_horizontal: boolean;
  flip_vertical: boolean;
  duration_seconds: number;
  show_at_end: boolean;
}

export interface VideoPreset {
  id: string;
  kind: PresetKind;
  name: string;
  angle: string;
  /** "voiceover" (VO sobre planos producto — todos los tiers OK)
   *  | "creator_pov" (persona habla a cámara — solo Pro/Veo3)
   *  | "" (legacy / music) */
  style: string;
  /** "single_shot" (1 plano continuo) | "multi_shot" (cortes) | "auto" */
  shot_style: string;
  /** Estrategia de cámara: "cinematic" (continuo, lento) | "dynamic" (cortes) */
  strategy: string;
  duration_s: number;
  compatible_tiers: string[];
  text_overlay: string;
  text_overlay_style: TextOverlayStyle;
  subtitle_style: SubtitleStyle;
  cta_arrow_style: CtaArrowStyle;
  music_mood: string;
  voice_id: string | null;
  voice_tone: string;
  title: string;
  voice_script: string;
  hooks_alternatives: string[];
  cta: string;
  oratory_tips: string;
  keywords: string[];
  seedance_prompt: string;
  veo3_prompt: string;
  /** Fotos del producto que Gemini eligió para adjuntar manualmente al
   *  prompt de Veo 3 al pegarlo en Gemini chat / Flow. Filenames del
   *  array `product.photos.source`. Máx 3. */
  veo3_photo_filenames: string[];
  source: string; // "music_bof" | "scripted_bof" | "manual"
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface GeneratePresetsInput {
  kind?: "music" | "scripted" | "both";
  n_music?: number;
  n_scripted?: number;
  replace_existing?: boolean;
}

export interface GeneratePresetsResponse {
  product_id: string;
  gen_id: string;
  stage: string;
  created_count: number;
  presets: VideoPreset[];
  warnings: string[];
}

export interface PresetGenStatus {
  gen_id: string;
  product_id: string;
  kind: string;
  /** "started" | "generating_music" | "generating_scripted" | "saving"
   *  | "done" | "error" */
  stage: string;
  percent: number;
  expected_count: number;
  created_count: number;
  warnings: string[];
  started_at: string;
  ended_at: string | null;
  error: string | null;
  /** Coste acumulado en USD de las llamadas a Gemini. Se rellena tras
   *  cada stage; final cuando stage=done. */
  cost_usd: number;
}

export type VideoPresetUpdateInput = Partial<
  Omit<VideoPreset, "id" | "kind" | "source" | "created_at" | "updated_at">
>;

// --- Variantes A/B -------------------------
export const VARIANT_DIMENSIONS = [
  "text_overlay",
  "text_overlay_color",
  "text_overlay_position",
  "cta_arrow",
  "voice_tone",
  "voice_script",
  "music_mood",
  "shot_style",
  "hooks_alternatives",
  "subtitle_style",
] as const;
export type VariantDimension = (typeof VARIANT_DIMENSIONS)[number];

export interface GenerateVariantsInput {
  count?: number;
  dimensions?: VariantDimension[];
}

export interface VariantMeta {
  variant_id: string;
  hypothesis: string;
  patch_keys: string[];
}

export interface GenerateVariantsResponse {
  base_preset_id: string;
  variants: VideoPreset[];
  meta: VariantMeta[];
  warnings: string[];
}
