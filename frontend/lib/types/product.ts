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
