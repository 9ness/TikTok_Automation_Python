"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { ANCHO_MINIATURA, ANCHO_VISOR } from "@/lib/queries/nichoPovBof";

// Se re-exporta para que las pantallas de este nicho no tengan que importar
// del POV BOF solo para pedir la foto grande del visor.
export { ANCHO_VISOR };
import type {
  CineFoldersResponse,
  CinePrompts,
  CineProductosResponse,
  CineSource,
  CineUploadResponse,
} from "@/lib/types/nichoBofCine";

const ROOT = "/api/v1/nicho-bof-cine";

export const cineKeys = {
  all: ["nicho-bof-cine"] as const,
  prompts: () => [...cineKeys.all, "prompts"] as const,
  sources: () => [...cineKeys.all, "sources"] as const,
  folders: (source: string) => [...cineKeys.all, "folders", source] as const,
  productos: (source: string, folder: string) =>
    [...cineKeys.all, "productos", source, folder] as const,
};

// Los prompts se retocan de vez en cuando y con `staleTime: Infinity` el móvil
// se quedaba con el viejo para siempre (ver `usePrompts` del POV BOF).
export function useCinePrompts() {
  return useQuery<CinePrompts>({
    queryKey: cineKeys.prompts(),
    queryFn: () => api.get<CinePrompts>(`${ROOT}/prompts`),
    staleTime: 60_000,
  });
}

export function useCineSources() {
  return useQuery<CineSource[]>({
    queryKey: cineKeys.sources(),
    queryFn: async () => (await api.get<{ items: CineSource[] }>(`${ROOT}/sources`)).items ?? [],
    staleTime: Infinity,
  });
}

export function useCineFolders(source: string) {
  return useQuery<CineFoldersResponse>({
    queryKey: cineKeys.folders(source),
    queryFn: () =>
      api.get<CineFoldersResponse>(`${ROOT}/folders?source=${encodeURIComponent(source)}`),
    enabled: Boolean(source),
  });
}

export function useCineProductos(source: string, folder: string | null) {
  return useQuery<CineProductosResponse>({
    queryKey: cineKeys.productos(source, folder ?? ""),
    queryFn: () =>
      api.get<CineProductosResponse>(
        `${ROOT}/productos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}`,
      ),
    enabled: Boolean(source && folder),
    // Mientras se monta algo, se refresca solo para que aparezca el vídeo.
    // 12 s, como los otros nichos: sondear cada 5 la lista entera era de donde
    // salían las lecturas de Redis.
    refetchInterval: (q) => (q.state.data?.montando ? 12000 : false),
  });
}

export function useCineExtraerTextos() {
  const qc = useQueryClient();
  return useMutation<CineProductosResponse, Error, { source: string; folder: string }>({
    mutationFn: ({ source, folder }) =>
      api.post<CineProductosResponse>(
        `${ROOT}/extraer-textos?source=${encodeURIComponent(
          source,
        )}&folder=${encodeURIComponent(folder)}`,
        {},
      ),
    onSuccess: (d) => qc.setQueryData(cineKeys.productos(d.source, d.folder), d),
  });
}

export function useCineMarcarCarpeta() {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { source: string; folder: string; completed: boolean }>({
    mutationFn: (body) => api.post(`${ROOT}/complete`, body),
    onSuccess: (_d, v) => void qc.invalidateQueries({ queryKey: cineKeys.folders(v.source) }),
  });
}

/** "Vídeos hechos, falta subirlos" — el aviso del listado de carpetas. */
export function useCineMarcarPendiente() {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { source: string; folder: string; pendiente: boolean }>({
    mutationFn: (body) => api.post(`${ROOT}/pendiente`, body),
    onSuccess: (_d, v) => void qc.invalidateQueries({ queryKey: cineKeys.folders(v.source) }),
  });
}

/** Sube UNO de los dos clips. El backend solo encola cuando están los dos. */
export function useCineSubirClip() {
  const qc = useQueryClient();
  return useMutation<
    CineUploadResponse,
    Error,
    { source: string; folder: string; producto: string; slot: 1 | 2; sexo: string; file: File }
  >({
    mutationFn: async ({ source, folder, producto, slot, sexo, file }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("source", source);
      fd.append("folder", folder);
      fd.append("producto", producto);
      fd.append("slot", String(slot));
      fd.append("sexo", sexo);
      return api.post<CineUploadResponse>(`${ROOT}/video/upload`, fd);
    },
    onSuccess: (_r, v) =>
      void qc.invalidateQueries({ queryKey: cineKeys.productos(v.source, v.folder) }),
  });
}

function base(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}
function keyQs(): string {
  const k = process.env.NEXT_PUBLIC_API_KEY;
  return k ? `&api_key=${encodeURIComponent(k)}` : "";
}

/** `ancho` encoge la foto en el servidor — ver `ANCHO_MINIATURA` en
 *  `nichoPovBof.ts`: sin esto el móvil se queda sin memoria y cierra la app. */
export function cineFotoUrl(
  source: string, folder: string, fileId: string, ancho: number | null = ANCHO_MINIATURA,
): string {
  const w = ancho ? `&w=${ancho}` : "";
  return `${base()}/api/v1/nicho-pov-bof/photo?source=${encodeURIComponent(
    source,
  )}&folder=${encodeURIComponent(folder)}&file_id=${encodeURIComponent(fileId)}${w}${keyQs()}`;
}

export function cineFotoLimpiaUrl(source: string, folder: string, producto: string): string {
  return `${base()}${ROOT}/foto-limpia?source=${encodeURIComponent(
    source,
  )}&folder=${encodeURIComponent(folder)}&producto=${encodeURIComponent(producto)}${keyQs()}`;
}

export function cineVideoUrl(
  source: string, folder: string, producto: string, v: number, descargar = false,
): string {
  return `${base()}${ROOT}/video?source=${encodeURIComponent(
    source,
  )}&folder=${encodeURIComponent(folder)}&producto=${encodeURIComponent(
    producto,
  )}&descargar=${descargar}&v=${v}${keyQs()}`;
}

/** Mete o saca el producto del escaparate. El estado es ÚNICO por producto
 *  (tienda|nombre) y compartido con los demás nichos: si ya se metió desde el
 *  POV BOF o desde otra carpeta, aquí ya sale hecho. */
export function useSetEstadoCine(source: string, folder: string) {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { producto: string; en_escaparate: boolean }
  >({
    mutationFn: (body) =>
      api.post(`${ROOT}/producto/estado`, { source, folder, ...body }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: cineKeys.productos(source, folder) }),
  });
}
