/**
 * Radar de Productos — descubrimiento avanzado (GMV Max + multi-país).
 */

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface WinnerScore {
  total: number;
  demand: number;
  low_competition: number;
  ads_injection: number;
  momentum: number;
  commission: number;
  reasons: string[];
}

export interface AdsSignal {
  checked: boolean;
  videos_analyzed: number;
  ad_labeled_videos: number;
  ad_labels_available: boolean;
  gmv_max_likelihood: number;
  probable_boosted: boolean;
  verdict: string;
  reasons: string[];
}

export interface RadarCandidate {
  product_id: string;
  name: string;
  cover_url: string;
  tiktok_url: string;
  region: string;
  units_sold: number;
  gmv: number;
  gmv_30d: number;
  influencer_count: number;
  video_count: number;
  commission_pct: number;
  min_price: number;
  max_price: number;
  growth_pct: number | null;
  video_sales_ratio: number;
  score: WinnerScore;
  ads: AdsSignal;
  imported: boolean;
  imported_product_id: string | null;
}

export interface RadarScanRequest {
  regions: string[];
  keywords: string[];
  per_source_limit?: number;
  deep_ads?: boolean;
  ads_provider?: string;
  deep_ads_top_n?: number;
  max_influencers?: number;
  min_gmv_eur?: number;
  min_units_sold?: number;
  min_commission_pct?: number;
  min_score?: number;
  require_ads_signal?: boolean;
  require_video_driven?: boolean;
  min_growth_pct?: number | null;
}

export interface RadarScanResponse {
  configured: boolean;
  scanned_regions: string[];
  found: number;
  items: RadarCandidate[];
  quota_exhausted: boolean;
  hint: string;
}

export interface RegionOption {
  code: string;
  label: string;
}

export function useRadarRegions() {
  return useQuery<{ regions: RegionOption[]; unsupported_eu: string[] }>({
    queryKey: ["radar-regions"],
    queryFn: () =>
      api.get<{ regions: RegionOption[]; unsupported_eu: string[] }>(
        "/api/v1/tiktok-shop/radar/regions",
      ),
    staleTime: 60 * 60_000,
    retry: false,
  });
}

export function useRadarCandidates(sort: string, enabled = true) {
  return useQuery<RadarCandidate[]>({
    queryKey: ["radar-candidates", sort],
    queryFn: () =>
      api.get<RadarCandidate[]>(`/api/v1/tiktok-shop/radar/candidates?sort=${sort}`),
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

export function useRadarScan() {
  return useMutation<RadarScanResponse, Error, RadarScanRequest>({
    mutationFn: (body) =>
      api.post<RadarScanResponse>("/api/v1/tiktok-shop/radar/scan", body),
  });
}

export function useRadarImport() {
  return useMutation<
    { ok: boolean; product_id: string | null; slug: string | null; message: string },
    Error,
    { product_id: string; category?: string; language?: string }
  >({
    mutationFn: (body) =>
      api.post("/api/v1/tiktok-shop/radar/import", body),
  });
}

export function useRadarClear() {
  return useMutation<{ deleted: number }, Error, void>({
    mutationFn: () => api.post<{ deleted: number }>("/api/v1/tiktok-shop/radar/clear"),
  });
}

// ── Calendario / Plan (Fase 2) ─────────────────────────────────────
export interface PlanEntry {
  day: number;
  product_id: string;
  slug: string;
  name: string;
  score: number;
  ads_verdict: string;
  tested: boolean;
  tiktok_url: string;
  presets_count: number;
  carousels_count: number;
  hooks_count: number;
  problem_videos_count: number;
  pack_ready: boolean;
  ai_ready: boolean;
}

export interface WeekPlan {
  exists: boolean;
  id: string;
  label: string;
  days: number;
  entries: PlanEntry[];
}

export interface CalendarActionResponse {
  ok: boolean;
  product_id: string | null;
  slug: string | null;
  job_id: string | null;
  message: string;
}

export function useRadarPlan() {
  return useQuery<WeekPlan>({
    queryKey: ["radar-plan"],
    queryFn: () => api.get<WeekPlan>("/api/v1/tiktok-shop/radar/plan"),
    // Refresca mientras haya packs generándose (pack_ready=false).
    refetchInterval: (q) =>
      q.state.data?.entries?.some((e) => !e.pack_ready) ? 5000 : false,
    retry: false,
  });
}

export function useImportToCalendar() {
  return useMutation<
    CalendarActionResponse,
    Error,
    { product_id: string; day?: number; research?: boolean; n_carousels?: number }
  >({
    mutationFn: (body) =>
      api.post<CalendarActionResponse>("/api/v1/tiktok-shop/radar/import-to-calendar", body),
  });
}

/** Llena un día del calendario con los productos que están recibiendo
 *  inyección de ADS ahora mismo (Radar v2, descubrimiento invertido). */
export interface ScrapeProduct {
  product_id: string;
  title: string;
  sold: number;
  price: number;
  image: string;
  seller: string;
  product_url: string;
}

/** Buscar productos de TikTok Shop España por nicho (ScrapeCreators). */
export function useScrapeSearch() {
  return useMutation<
    { ok: boolean; configured: boolean; products: ScrapeProduct[]; credits_remaining: number | null; message: string },
    Error,
    { query: string; min_sold?: number; max_price?: number }
  >({
    mutationFn: (body) => api.post("/api/v1/tiktok-shop/radar/scrape/search", body),
  });
}

/** Crear el producto encontrado + añadirlo a un día + generar vídeos. */
export function useScrapeAdd() {
  return useMutation<
    CalendarActionResponse,
    Error,
    {
      product_id: string; title: string; image?: string; price?: number;
      sold?: number; seller?: string; date?: string; gens?: string[];
    }
  >({
    mutationFn: (body) => api.post("/api/v1/tiktok-shop/radar/scrape/add", body),
  });
}

export function useAutoDay() {
  return useMutation<
    CalendarActionResponse,
    Error,
    {
      date?: string;
      top_n?: number;
      region?: string;
      days_window?: number;
      max_influencers?: number | null;
      min_commission_eur?: number;
      videos_per_product?: number;
      gens?: string[];
    }
  >({
    mutationFn: (body) =>
      api.post<CalendarActionResponse>("/api/v1/tiktok-shop/radar/plan/auto-day", body),
  });
}

export function usePlanGenerate() {
  return useMutation<
    CalendarActionResponse,
    Error,
    { per_day?: number; days?: number; research?: boolean; n_carousels?: number }
  >({
    mutationFn: (body) =>
      api.post<CalendarActionResponse>("/api/v1/tiktok-shop/radar/plan/generate", body),
  });
}

export function usePlanPack() {
  return useMutation<
    CalendarActionResponse,
    Error,
    { product_id: string; research?: boolean; n_carousels?: number }
  >({
    mutationFn: (body) =>
      api.post<CalendarActionResponse>("/api/v1/tiktok-shop/radar/plan/pack", body),
  });
}

export function useMarkTested() {
  return useMutation<{ ok: boolean }, Error, { product_id: string; tested: boolean }>({
    mutationFn: (body) =>
      api.post<{ ok: boolean }>("/api/v1/tiktok-shop/radar/plan/tested", body),
  });
}

export function useDeletePlan() {
  return useMutation<{ ok: boolean }, Error, void>({
    mutationFn: () => api.del<{ ok: boolean }>("/api/v1/tiktok-shop/radar/plan"),
  });
}

export function useRemoveFromPlan() {
  return useMutation<{ ok: boolean; removed: number }, Error, { product_id: string }>({
    mutationFn: (body) => api.post("/api/v1/tiktok-shop/radar/plan/remove", body),
  });
}

export function useRemoveBatch() {
  return useMutation<
    { ok: boolean; removed: number },
    Error,
    { product_ids?: string[]; day?: number }
  >({
    mutationFn: (body) => api.post("/api/v1/tiktok-shop/radar/plan/remove-batch", body),
  });
}

export interface VideoTemplate {
  id: string;
  name: string;
  niches: string[];
  notes: string;
  prompt: string;
  first_frame_prompt: string;
  kling_prompt: string;
}

export function useAddUrl() {
  return useMutation<
    CalendarActionResponse,
    Error,
    { url: string; name?: string; category?: string; date?: string; gens?: string[] }
  >({
    mutationFn: (body) =>
      api.post<CalendarActionResponse>("/api/v1/tiktok-shop/radar/plan/add-url", body),
  });
}

export interface BatchItemResult {
  line: string;
  ok: boolean;
  name: string;
  date: string;
  message: string;
}

export function useAddBatch() {
  return useMutation<
    { ok: boolean; added: number; failed: number; results: BatchItemResult[] },
    Error,
    { raw: string; date?: string; language?: string; gens?: string[] }
  >({
    mutationFn: (body) =>
      api.post("/api/v1/tiktok-shop/radar/plan/add-batch", body),
  });
}

export interface ReplicaSegment {
  is_extend: boolean;
  label: string;
  image_prompt: string;
  animate_prompt: string;
  spoken_line: string;
}

export interface ProblemVideo {
  concept: string;
  format: string;
  emotion: string;
  angle: string;
  veo3_prompt: string;
  image_prompt?: string;
  animate_prompt?: string;
  spoken_line: string;
  hook_text: string;
  cta_text: string;
  caption: string;
  ready_video?: string;
  /** Modo réplica larga: trozos encadenados de ~8s (solo "Replicar viral"). */
  segments?: ReplicaSegment[];
}

export function useProblemVideos() {
  return useMutation<
    { ok: boolean; videos: ProblemVideo[]; ideal_customer?: Record<string, unknown>; sale?: Record<string, unknown>; language: string },
    Error,
    { product_id: string; language: string; n?: number }
  >({
    mutationFn: (body) => api.post("/api/v1/tiktok-shop/radar/videos/problem", body),
  });
}

export function useVideoTemplates(productId: string) {
  return useQuery<{ product_name: string; templates: VideoTemplate[] }>({
    queryKey: ["radar-video-templates", productId],
    queryFn: () =>
      api.get(`/api/v1/tiktok-shop/radar/video-templates?product_id=${encodeURIComponent(productId)}`),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export interface BofuHook {
  text: string;
  type: string;
}

export function useBofuHooks() {
  return useMutation<
    { ok: boolean; hooks: BofuHook[]; language: string },
    Error,
    { product_id: string; language: string; n?: number }
  >({
    mutationFn: (body) => api.post("/api/v1/tiktok-shop/radar/hooks/bofu", body),
  });
}

export function useRegenerateCarousels() {
  return useMutation<
    { ok: boolean; count: number; language: string },
    Error,
    { product_id: string; language: string; text_style?: string; n_carousels?: number; n_slides?: number }
  >({
    mutationFn: (body) =>
      api.post("/api/v1/tiktok-shop/radar/carousels/regenerate", body),
  });
}
