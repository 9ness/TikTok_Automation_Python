"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  CarpetasRopaResponse,
  PrendaItem,
  PrendasListResponse,
  PromptsRopaResponse,
  VideoRopaUploadResponse,
} from "@/lib/types/nichoRopa";

const ROOT = "/api/v1/nicho-ropa";

export const nichoRopaKeys = {
  all: ["nicho-ropa"] as const,
  carpetas: () => [...nichoRopaKeys.all, "carpetas"] as const,
  prendas: (carpeta: string) => [...nichoRopaKeys.all, "prendas", carpeta] as const,
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

/** Carpetas de producto. Las de mujer son las del nicho CON personas, pero la
 *  misma prenda vale aquí colgada en percha. */
export function useCarpetasRopa() {
  return useQuery<CarpetasRopaResponse>({
    queryKey: nichoRopaKeys.carpetas(),
    queryFn: () => api.get<CarpetasRopaResponse>(`${ROOT}/carpetas`),
    staleTime: Infinity,
  });
}

/** Mientras haya un montaje en curso se sondea solo, y para al terminar. */
export function usePrendas(carpeta: string) {
  return useQuery<PrendasListResponse>({
    queryKey: nichoRopaKeys.prendas(carpeta),
    queryFn: () =>
      api.get<PrendasListResponse>(
        `${ROOT}/prendas?carpeta=${encodeURIComponent(carpeta)}`,
      ),
    refetchInterval: (query) => (query.state.data?.montando ? 5000 : false),
    enabled: Boolean(carpeta),
  });
}

/** Tarda ~1 min: lee todas las capturas con Gemini en una sola llamada. */
export function useExtraerTextosRopa() {
  const qc = useQueryClient();
  return useMutation<PrendasListResponse, Error, string>({
    mutationFn: (carpeta) =>
      api.post<PrendasListResponse>(
        `${ROOT}/extraer-textos?carpeta=${encodeURIComponent(carpeta)}`,
      ),
    onSuccess: (res, carpeta) =>
      qc.setQueryData(nichoRopaKeys.prendas(carpeta), res),
  });
}

export function useSubirVideoRopa() {
  const qc = useQueryClient();
  return useMutation<
    VideoRopaUploadResponse,
    Error,
    { producto: string; carpeta: string; file: File; sexo: string }
  >({
    mutationFn: ({ producto, carpeta, file, sexo }) => {
      const fd = new FormData();
      fd.append("producto", producto);
      fd.append("carpeta", carpeta);
      fd.append("sexo", sexo);
      fd.append("file", file);
      return api.post<VideoRopaUploadResponse>(`${ROOT}/video/upload`, fd);
    },
    onSuccess: (_res, vars) => {
      void qc.invalidateQueries({ queryKey: nichoRopaKeys.prendas(vars.carpeta) });
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

export function buildFotoLimpiaRopaUrl(producto: string, carpeta: string): string {
  return conApiKey(
    `${ROOT}/foto-limpia?producto=${encodeURIComponent(producto)}` +
      `&carpeta=${encodeURIComponent(carpeta)}`,
  );
}

/** `v` es la marca de versión: sin ella el navegador reutiliza el vídeo viejo. */
export function buildVideoRopaUrl(
  producto: string, carpeta: string, v: number, descargar = false,
): string {
  return conApiKey(
    `${ROOT}/video?producto=${encodeURIComponent(producto)}` +
      `&carpeta=${encodeURIComponent(carpeta)}&v=${v}` +
      (descargar ? "&descargar=true" : ""),
  );
}

export type { PrendaItem };
