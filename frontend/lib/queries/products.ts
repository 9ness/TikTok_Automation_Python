"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  AnalyzeUrlPreviewInput,
  AnalyzeUrlPreviewResponse,
  CommitImportedPhotosInput,
  CommitImportedPhotosResponse,
  GeneratePresetsInput,
  GeneratePresetsResponse,
  GenerateVariantsInput,
  GenerateVariantsResponse,
  PresetGenStatus,
  GoogleImageSearchInput,
  GoogleImageSearchResponse,
  ImportPhotosFromUrlsInput,
  ImportPhotosFromUrlsResponse,
  NanoBananaPromptInput,
  NanoBananaPromptResponse,
  PhotoLocation,
  PhotoOrigin,
  PhotoType,
  PhotoUpdateInput,
  Product,
  ProductCreateInput,
  ProductListResponse,
  ProductPhoto,
  ProductUpdateInput,
  ReanalyzeResponse,
  VideoPreset,
  VideoPresetUpdateInput,
} from "@/lib/types/product";

const ROOT = "/api/v1/products";

export interface ProductsFilters {
  limit?: number;
  offset?: number;
  category?: string;
  include_deleted?: boolean;
}

export const productKeys = {
  all: ["products"] as const,
  list: (filters?: ProductsFilters) => [...productKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...productKeys.all, "detail", id] as const,
};

function buildQueryString(filters?: ProductsFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  if (filters.category) params.set("category", filters.category);
  if (filters.include_deleted) params.set("include_deleted", "true");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useProducts(
  filters?: ProductsFilters,
  options?: Omit<UseQueryOptions<ProductListResponse>, "queryKey" | "queryFn">,
) {
  return useQuery<ProductListResponse>({
    queryKey: productKeys.list(filters),
    queryFn: () => api.get<ProductListResponse>(`${ROOT}${buildQueryString(filters)}`),
    ...options,
  });
}

export function useProduct(id: string | null | undefined) {
  return useQuery<Product>({
    queryKey: productKeys.detail(id ?? ""),
    queryFn: () => api.get<Product>(`${ROOT}/${id}`),
    enabled: Boolean(id),
    // Mientras el deep research corre en background, refrescar cada 8s
    // para que el spinner desaparezca y aparezcan los datos al terminar.
    refetchInterval: (q) =>
      q.state.data?.research_context?.research_in_progress ? 8000 : false,
  });
}

/** Lanza SOLO el deep research (Audiencia) sin re-analizar fotos. */
export function useRunDeepResearch(id: string) {
  const qc = useQueryClient();
  return useMutation<{ product_id: string; status: string }, Error, void>({
    mutationFn: () =>
      api.post<{ product_id: string; status: string }>(
        `${ROOT}/${id}/deep-research`,
        {},
      ),
    onSuccess: () => {
      // Optimista: marcamos research_in_progress=true en el cache YA, sin
      // esperar al backend (que lo pone en background tras el 202). Esto
      // muestra el spinner al instante y activa el refetchInterval de
      // useProduct (8s) → se actualiza solo cuando el server lo termine.
      qc.setQueryData<Product>(productKeys.detail(id), (old) =>
        old
          ? {
              ...old,
              research_context: {
                ...old.research_context,
                research_in_progress: true,
              },
            }
          : old,
      );
    },
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation<Product, Error, ProductCreateInput>({
    mutationFn: (input) => api.post<Product>(ROOT, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useUpdateProduct(id: string) {
  const qc = useQueryClient();
  return useMutation<Product, Error, ProductUpdateInput>({
    mutationFn: (input) => api.put<Product>(`${ROOT}/${id}`, input),
    onSuccess: (data) => {
      qc.setQueryData(productKeys.detail(id), data);
      qc.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.del<void>(`${ROOT}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export interface UploadPhotoInput {
  productId: string;
  file: File;
  location: PhotoLocation;
  type?: PhotoType;
  origin?: PhotoOrigin;
  url_origin?: string;
}

export function useUploadPhoto() {
  const qc = useQueryClient();
  return useMutation<ProductPhoto, Error, UploadPhotoInput>({
    mutationFn: async ({ productId, file, location, type, origin, url_origin }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("location", location);
      if (type) fd.append("type", type);
      if (origin) fd.append("origin", origin);
      if (url_origin) fd.append("url_origin", url_origin);
      return api.post<ProductPhoto>(`${ROOT}/${productId}/photos`, fd);
    },
    onSuccess: (_data, { productId }) => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useDeletePhoto() {
  const qc = useQueryClient();
  return useMutation<void, Error, { productId: string; photoId: string }>({
    mutationFn: ({ productId, photoId }) =>
      api.del<void>(`${ROOT}/${productId}/photos/${encodeURIComponent(photoId)}`),
    onSuccess: (_data, { productId, photoId }) => {
      // Optimistic update: marca deleted=true en la cache inmediatamente
      // para que la UI esconda la foto sin esperar al refetch. Si el
      // refetch luego trae un estado distinto, gana el server (correcto).
      qc.setQueryData<Product>(productKeys.detail(productId), (prev) => {
        if (!prev) return prev;
        const markDeleted = (list: typeof prev.photos.source) =>
          list.map((p) =>
            p.filename === photoId ? { ...p, deleted: true } : p,
          );
        return {
          ...prev,
          photos: {
            ...prev.photos,
            source: markDeleted(prev.photos.source),
            generated: markDeleted(prev.photos.generated),
          },
        };
      });
      // Y además forzamos refetch real para reconciliar con el server.
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
      qc.refetchQueries({
        queryKey: productKeys.detail(productId),
        exact: true,
      });
    },
  });
}

export function useUpdatePhoto() {
  const qc = useQueryClient();
  return useMutation<
    ProductPhoto,
    Error,
    { productId: string; photoId: string; payload: PhotoUpdateInput }
  >({
    mutationFn: ({ productId, photoId, payload }) =>
      api.put<ProductPhoto>(
        `${ROOT}/${productId}/photos/${encodeURIComponent(photoId)}`,
        payload,
      ),
    onSuccess: (_data, { productId }) => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useReanalyzeProduct() {
  const qc = useQueryClient();
  return useMutation<ReanalyzeResponse, Error, string>({
    mutationFn: (productId) => api.post<ReanalyzeResponse>(`${ROOT}/${productId}/analyze`),
    onSuccess: (_data, productId) => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

/**
 * Analiza una URL de TikTok Shop sin persistir nada. Devuelve los campos
 * detectados (nombre, marca, categoría, precio, …) para auto-rellenar
 * el form de Identidad. El usuario revisa y guarda con el PUT normal.
 */
export function useAnalyzeUrlPreview() {
  return useMutation<AnalyzeUrlPreviewResponse, Error, AnalyzeUrlPreviewInput>({
    mutationFn: (input) =>
      api.post<AnalyzeUrlPreviewResponse>(`${ROOT}/analyze-url-preview`, input),
  });
}

/** Descarga + graduea con Gemini un lote de URLs de imagen. NO persiste —
 *  el user revisa los scores y elige cuáles guardar via commit. */
export function useImportPhotosFromUrls(productId: string) {
  return useMutation<
    ImportPhotosFromUrlsResponse,
    Error,
    ImportPhotosFromUrlsInput
  >({
    mutationFn: (input) =>
      api.post<ImportPhotosFromUrlsResponse>(
        `${ROOT}/${productId}/import-photos-from-urls`,
        input,
      ),
  });
}

/** Confirma los candidatos que el user marcó keep. Mueve los temp files
 *  a la carpeta source y registra ProductPhoto en el producto. */
export function useCommitImportedPhotos(productId: string) {
  const qc = useQueryClient();
  return useMutation<
    CommitImportedPhotosResponse,
    Error,
    CommitImportedPhotosInput
  >({
    mutationFn: (input) =>
      api.post<CommitImportedPhotosResponse>(
        `${ROOT}/${productId}/commit-imported-photos`,
        input,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

/** Búsqueda opcional en Google Images vía CSE. Devuelve `configured:false`
 *  si las env vars no están set — UI muestra un hint en ese caso. */
export function useSearchPhotosOnGoogle(productId: string) {
  return useMutation<GoogleImageSearchResponse, Error, GoogleImageSearchInput>({
    mutationFn: (input) =>
      api.post<GoogleImageSearchResponse>(
        `${ROOT}/${productId}/search-photos-on-google`,
        input,
      ),
  });
}

// --- Video Presets ------------------------------------------------
export function useVideoPresets(productId: string) {
  return useQuery<VideoPreset[]>({
    queryKey: [...productKeys.detail(productId), "video-presets"],
    queryFn: () => api.get<VideoPreset[]>(`${ROOT}/${productId}/video-presets`),
    staleTime: 30_000,
  });
}

export function useGeneratePresets(productId: string) {
  const qc = useQueryClient();
  return useMutation<GeneratePresetsResponse, Error, GeneratePresetsInput>({
    mutationFn: (input) =>
      api.post<GeneratePresetsResponse>(
        `${ROOT}/${productId}/video-presets/generate`,
        input,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useUpdateVideoPreset(productId: string) {
  const qc = useQueryClient();
  return useMutation<
    VideoPreset,
    Error,
    { presetId: string; patch: VideoPresetUpdateInput }
  >({
    mutationFn: ({ presetId, patch }) =>
      api.patch<VideoPreset>(
        `${ROOT}/${productId}/video-presets/${presetId}`,
        patch,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

/** Hook de polling del progreso de la generación de presets. */
export function usePresetGenStatus(
  productId: string,
  genId: string | null,
  options?: { onDone?: () => void },
) {
  const qc = useQueryClient();
  return useQuery<PresetGenStatus>({
    queryKey: [...productKeys.detail(productId), "preset-gen", genId],
    queryFn: () =>
      api.get<PresetGenStatus>(
        `${ROOT}/${productId}/preset-gen-status/${genId}`,
      ),
    enabled: Boolean(genId),
    refetchInterval: (q) => {
      const s = q.state.data?.stage;
      if (s === "done" || s === "error") {
        // Refresh el producto para que la lista de presets se actualice.
        qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
        options?.onDone?.();
        return false;
      }
      // Abandonar generaciones colgadas (>15 min sin terminar) — p.ej. si
      // el contenedor se reinició a mitad. Evita spinner zombie eterno.
      const startedAt = q.state.data?.started_at;
      if (startedAt && Date.now() - new Date(startedAt).getTime() > 900_000) {
        options?.onDone?.();
        return false;
      }
      return 2000;
    },
    refetchOnWindowFocus: false,
  });
}

/** Genera N variantes A/B de un preset via Gemini. NO persiste — son
 *  one-shot para encolar tests inteligentes. */
export function useGenerateVariants(productId: string) {
  return useMutation<
    GenerateVariantsResponse,
    Error,
    { presetId: string; input: GenerateVariantsInput }
  >({
    mutationFn: ({ presetId, input }) =>
      api.post<GenerateVariantsResponse>(
        `${ROOT}/${productId}/video-presets/${presetId}/generate-variants`,
        input,
      ),
  });
}

export interface BulkStyleInput {
  text_overlay_style?: Record<string, unknown>;
  subtitle_style?: Record<string, unknown>;
  scope?: "all" | "music" | "scripted" | "viral_replica";
}

export interface BulkStyleResult {
  updated_count: number;
  skipped_count: number;
  total_presets: number;
}

/** Aplica un patch de estilo VISUAL (color, fuente, animación, etc.)
 *  a TODOS los presets del producto, o a un scope concreto. La
 *  posición se ignora server-side (whitelist defensiva). */
export function useBulkApplyPresetStyle(productId: string) {
  const qc = useQueryClient();
  return useMutation<BulkStyleResult, Error, BulkStyleInput>({
    mutationFn: (input) =>
      api.patch<BulkStyleResult>(
        `${ROOT}/${productId}/video-presets/bulk-style`,
        input,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

/** Persiste un VideoPreset generado por el analizador viral en el
 *  producto. El payload es el dict completo `result.video_preset` que
 *  devuelve el endpoint replicate-viral. */
export function useSaveViralVideoPreset(productId: string) {
  const qc = useQueryClient();
  return useMutation<VideoPreset, Error, Record<string, unknown>>({
    mutationFn: (videoPresetPayload) =>
      api.post<VideoPreset>(
        `${ROOT}/${productId}/video-presets/save-viral`,
        videoPresetPayload,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useDeleteVideoPreset(productId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (presetId) =>
      api.del<void>(`${ROOT}/${productId}/video-presets/${presetId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

/** Borra TODOS los presets del producto. Si `only_autogenerated=true`,
 *  mantiene los manuales (source="manual"). */
export function useDeleteAllVideoPresets(productId: string) {
  const qc = useQueryClient();
  return useMutation<
    { deleted_count: number; remaining: number },
    Error,
    { onlyAutogenerated?: boolean }
  >({
    mutationFn: ({ onlyAutogenerated }) =>
      api.del<{ deleted_count: number; remaining: number }>(
        `${ROOT}/${productId}/video-presets/all${
          onlyAutogenerated ? "?only_autogenerated=true" : ""
        }`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useGenerateNanoBananaPrompt() {
  return useMutation<
    NanoBananaPromptResponse,
    Error,
    { productId: string; payload: NanoBananaPromptInput }
  >({
    mutationFn: ({ productId, payload }) =>
      api.post<NanoBananaPromptResponse>(`${ROOT}/${productId}/nano-banana-prompt`, payload),
  });
}
