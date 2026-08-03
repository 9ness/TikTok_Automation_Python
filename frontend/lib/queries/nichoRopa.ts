"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  PrendaItem,
  PrendasListResponse,
  PromptsRopaResponse,
  VideoRopaUploadResponse,
} from "@/lib/types/nichoRopa";

const ROOT = "/api/v1/nicho-ropa";

export const nichoRopaKeys = {
  all: ["nicho-ropa"] as const,
  prendas: () => [...nichoRopaKeys.all, "prendas"] as const,
  prompts: () => [...nichoRopaKeys.all, "prompts"] as const,
};

/** Los prompts no cambian entre sesiones: se cachean para siempre. */
export function usePromptsRopa() {
  return useQuery<PromptsRopaResponse>({
    queryKey: nichoRopaKeys.prompts(),
    queryFn: () => api.get<PromptsRopaResponse>(`${ROOT}/prompts`),
    staleTime: Infinity,
  });
}

/** Mientras haya un montaje en curso se sondea solo, y para al terminar. */
export function usePrendas() {
  return useQuery<PrendasListResponse>({
    queryKey: nichoRopaKeys.prendas(),
    queryFn: () => api.get<PrendasListResponse>(`${ROOT}/prendas`),
    refetchInterval: (query) => (query.state.data?.montando ? 5000 : false),
  });
}

/** Tarda ~1 min: lee todas las capturas con Gemini en una sola llamada. */
export function useExtraerTextosRopa() {
  const qc = useQueryClient();
  return useMutation<PrendasListResponse, Error, void>({
    mutationFn: () => api.post<PrendasListResponse>(`${ROOT}/extraer-textos`),
    onSuccess: (res) => qc.setQueryData(nichoRopaKeys.prendas(), res),
  });
}

export function useSubirVideoRopa() {
  const qc = useQueryClient();
  return useMutation<
    VideoRopaUploadResponse,
    Error,
    { producto: string; file: File; sexo: string }
  >({
    mutationFn: ({ producto, file, sexo }) => {
      const fd = new FormData();
      fd.append("producto", producto);
      fd.append("sexo", sexo);
      fd.append("file", file);
      return api.post<VideoRopaUploadResponse>(`${ROOT}/video/upload`, fd);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: nichoRopaKeys.prendas() });
    },
  });
}

function conApiKey(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  return `${base}${path}${key ? `&api_key=${encodeURIComponent(key)}` : ""}`;
}

/** Un <img> no manda headers, así que la api_key va por query. */
export function buildFotoRopaUrl(fileId: string): string {
  return conApiKey(`${ROOT}/foto?file_id=${encodeURIComponent(fileId)}`);
}

export function buildFotoLimpiaRopaUrl(producto: string): string {
  return conApiKey(`${ROOT}/foto-limpia?producto=${encodeURIComponent(producto)}`);
}

/** `v` es la marca de versión: sin ella el navegador reutiliza el vídeo viejo. */
export function buildVideoRopaUrl(
  producto: string, v: number, descargar = false,
): string {
  return conApiKey(
    `${ROOT}/video?producto=${encodeURIComponent(producto)}&v=${v}` +
      (descargar ? "&descargar=true" : ""),
  );
}

export type { PrendaItem };
