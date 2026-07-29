"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  BackupCheckResponse,
  BackupSyncResponse,
  EstadoRequest,
  ExtraerTextosRequest,
  FoldersListResponse,
  MarkCompletedRequest,
  MarkCompletedResponse,
  PhotosListResponse,
  ProductoItem,
  ProductoUrlRequest,
  PromptsResponse,
  SourcesListResponse,
  VendidoItem,
} from "@/lib/types/nichoPovBof";

const ROOT = "/api/v1/nicho-pov-bof";

export const nichoPovBofKeys = {
  all: ["nicho-pov-bof"] as const,
  sources: () => [...nichoPovBofKeys.all, "sources"] as const,
  folders: (source: string) => [...nichoPovBofKeys.all, "folders", source] as const,
  photos: (source: string, folder: string) =>
    [...nichoPovBofKeys.all, "photos", source, folder] as const,
  prompts: () => [...nichoPovBofKeys.all, "prompts"] as const,
  productos: (source: string, folder: string) =>
    [...nichoPovBofKeys.all, "productos", source, folder] as const,
  vendidos: (source: string) => [...nichoPovBofKeys.all, "vendidos", source] as const,
};

export function useSources() {
  return useQuery<SourcesListResponse>({
    queryKey: nichoPovBofKeys.sources(),
    queryFn: () => api.get<SourcesListResponse>(`${ROOT}/sources`),
  });
}

export function useFolders(source: string) {
  return useQuery<FoldersListResponse>({
    queryKey: nichoPovBofKeys.folders(source),
    queryFn: () =>
      api.get<FoldersListResponse>(`${ROOT}/folders?source=${encodeURIComponent(source)}`),
    enabled: Boolean(source),
  });
}

export function usePhotos(source: string, folder: string | null) {
  return useQuery<PhotosListResponse>({
    queryKey: nichoPovBofKeys.photos(source, folder ?? ""),
    queryFn: () =>
      api.get<PhotosListResponse>(
        `${ROOT}/photos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}`,
      ),
    enabled: Boolean(source && folder),
  });
}

export function useMarkCompleted(source: string) {
  const qc = useQueryClient();
  return useMutation<MarkCompletedResponse, Error, MarkCompletedRequest>({
    mutationFn: (body) => api.post<MarkCompletedResponse>(`${ROOT}/complete`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: nichoPovBofKeys.folders(source) });
    },
  });
}

/** Comprobar cambios en el Drive de origen. Bajo demanda: el listado
 *  recursivo tarda ~1 min, así que no se dispara solo al abrir la página. */
export function useBackupCheck() {
  return useMutation<BackupCheckResponse, Error, void>({
    mutationFn: () => api.get<BackupCheckResponse>(`${ROOT}/backup/check`),
  });
}

export function useBackupSync() {
  return useMutation<BackupSyncResponse, Error, { force_full: boolean }>({
    mutationFn: (body) => api.post<BackupSyncResponse>(`${ROOT}/backup/sync`, body),
  });
}

/** URL de la foto (api_key por query — un <img> no manda headers). */
export function buildPhotoUrl(source: string, folder: string, fileId: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  return `${base}${ROOT}/photo?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&file_id=${encodeURIComponent(fileId)}${qs}`;
}

// --- Fase 2: automatización de vídeos ----------------------------------

/** Prompts fijos (imagen/vídeo) — no dependen de carpeta ni fuente. */
export function usePrompts() {
  return useQuery<PromptsResponse>({
    queryKey: nichoPovBofKeys.prompts(),
    queryFn: () => api.get<PromptsResponse>(`${ROOT}/prompts`),
    staleTime: Infinity,
  });
}

export function useProductos(source: string, folder: string | null) {
  // El backend devuelve {source, folder, items, textos_extraidos}; se
  // desenvuelve aquí a la lista para que los componentes no tengan que
  // conocer la envoltura.
  return useQuery<ProductoItem[]>({
    queryKey: nichoPovBofKeys.productos(source, folder ?? ""),
    queryFn: async () =>
      (await api.get<{ items: ProductoItem[] }>(
        `${ROOT}/productos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}`,
      )).items ?? [],
    enabled: Boolean(source && folder),
  });
}

/** Tarda ~1 min (lee las capturas con Gemini) — el caller muestra spinner. */
export function useExtraerTextos() {
  const qc = useQueryClient();
  return useMutation<ProductoItem[], Error, ExtraerTextosRequest>({
    mutationFn: async (body) =>
      (await api.post<{ items: ProductoItem[] }>(`${ROOT}/extraer-textos`, body)).items ?? [],
    onSuccess: (items, vars) => {
      qc.setQueryData(nichoPovBofKeys.productos(vars.source, vars.folder), items);
    },
  });
}

export function useSetEstado() {
  const qc = useQueryClient();
  return useMutation<ProductoItem, Error, EstadoRequest>({
    mutationFn: (body) => api.post<ProductoItem>(`${ROOT}/producto/estado`, body),
    onSuccess: (updated, vars) => {
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(vars.source, vars.folder),
        (old) => old?.map((p) => (p.producto === updated.producto ? updated : p)),
      );
      // Puede haber entrado o salido de "vendidos".
      void qc.invalidateQueries({ queryKey: nichoPovBofKeys.vendidos(vars.source) });
    },
  });
}

/** Averigua la ficha de TikTok Shop del producto. GASTA UNA LLAMADA del plan
 *  de EchoTik (trial de 100), por eso va producto a producto y no de carpeta
 *  entera. Si no encuentra nada fiable devuelve el producto sin `product_url`
 *  (no es un error). */
export function useBuscarProductoUrl() {
  const qc = useQueryClient();
  return useMutation<ProductoItem, Error, ProductoUrlRequest>({
    mutationFn: (body) => api.post<ProductoItem>(`${ROOT}/producto/url`, body),
    onSuccess: (updated, vars) => {
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(vars.source, vars.folder),
        (old) => old?.map((p) => (p.producto === updated.producto ? updated : p)),
      );
    },
  });
}

export function useVendidos(source: string) {
  return useQuery<VendidoItem[]>({
    queryKey: nichoPovBofKeys.vendidos(source),
    queryFn: async () =>
      (await api.get<{ items: VendidoItem[] }>(
        `${ROOT}/vendidos?source=${encodeURIComponent(source)}`,
      )).items ?? [],
    enabled: Boolean(source),
  });
}

/** URL de descarga de la foto limpia por nombre de producto (no por file id;
 *  el backend resuelve el par limpia/titulada dentro de la carpeta). */
export function buildCleanPhotoDownloadUrl(source: string, folder: string, producto: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  return `${base}${ROOT}/foto-limpia?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}${qs}`;
}
