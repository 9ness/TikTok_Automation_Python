"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  ClipLargoUploadResponse,
  ProductoLargo,
  ProductosLargoResponse,
  VocesLargo,
} from "@/lib/types/povBofLargo";

const ROOT = "/api/v1/nicho-pov-bof-largo";

export const largoKeys = {
  all: ["pov-bof-largo"] as const,
  voces: () => [...largoKeys.all, "voces"] as const,
  sources: () => [...largoKeys.all, "sources"] as const,
  folders: (source: string) => [...largoKeys.all, "folders", source] as const,
  productos: (source: string, folder: string) =>
    [...largoKeys.all, "productos", source, folder] as const,
};

export function useVocesLargo() {
  return useQuery<VocesLargo>({
    queryKey: largoKeys.voces(),
    queryFn: () => api.get<VocesLargo>(`${ROOT}/voces`),
    staleTime: Infinity,
  });
}

export function useSourcesLargo() {
  return useQuery<{ slug: string; label: string }[]>({
    queryKey: largoKeys.sources(),
    queryFn: async () =>
      (await api.get<{ items: { slug: string; label: string }[] }>(`${ROOT}/sources`))
        .items ?? [],
    staleTime: Infinity,
  });
}

export function useFoldersLargo(source: string) {
  return useQuery<string[]>({
    queryKey: largoKeys.folders(source),
    queryFn: async () =>
      (
        await api.get<{ items: { name: string }[] }>(
          `${ROOT}/folders?source=${encodeURIComponent(source)}`,
        )
      ).items.map((c) => c.name),
    enabled: Boolean(source),
  });
}

export function useProductosLargo(source: string, folder: string) {
  return useQuery<ProductosLargoResponse>({
    queryKey: largoKeys.productos(source, folder),
    queryFn: () =>
      api.get<ProductosLargoResponse>(
        `${ROOT}/productos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(folder)}`,
      ),
    enabled: Boolean(source && folder),
    // Mientras haya un montaje en curso se refresca solo.
    refetchInterval: (q) => (q.state.data?.montando ? 5000 : false),
  });
}

/** Escribe el guion locutado del producto. Gasta UNA llamada a Gemini. */
export function useEscribirGuion() {
  const qc = useQueryClient();
  return useMutation<
    ProductoLargo,
    Error,
    { source: string; folder: string; producto: string; rehacer?: boolean }
  >({
    mutationFn: async (body) =>
      (await api.post<{ producto: ProductoLargo }>(`${ROOT}/guion`, body)).producto,
    onSuccess: (_p, v) =>
      void qc.invalidateQueries({ queryKey: largoKeys.productos(v.source, v.folder) }),
  });
}

export function useSubirClipLargo() {
  const qc = useQueryClient();
  return useMutation<
    ClipLargoUploadResponse,
    Error,
    {
      source: string;
      folder: string;
      producto: string;
      slot: 1 | 2;
      sexo: string;
      file: File;
      conGancho: boolean;
      conTitulo: boolean;
      conCta: boolean;
      conFlecha: boolean;
    }
  >({
    mutationFn: async (v) => {
      const fd = new FormData();
      fd.append("file", v.file);
      fd.append("source", v.source);
      fd.append("folder", v.folder);
      fd.append("producto", v.producto);
      fd.append("slot", String(v.slot));
      fd.append("sexo", v.sexo);
      fd.append("con_gancho", String(v.conGancho));
      fd.append("con_titulo", String(v.conTitulo));
      fd.append("con_cta", String(v.conCta));
      fd.append("con_flecha", String(v.conFlecha));
      return api.post<ClipLargoUploadResponse>(`${ROOT}/clip/upload`, fd);
    },
    onSuccess: (_r, v) =>
      void qc.invalidateQueries({ queryKey: largoKeys.productos(v.source, v.folder) }),
  });
}

// --- URLs directas ----------------------------------------------------------

function base(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

function keyQs(): string {
  const k = process.env.NEXT_PUBLIC_API_KEY;
  return k ? `&api_key=${encodeURIComponent(k)}` : "";
}

/** La foto se sirve desde el POV BOF: es la misma de Drive, no se duplica. */
export function fotoLargoUrl(source: string, folder: string, fileId: string): string {
  return `${base()}/api/v1/nicho-pov-bof/photo?source=${encodeURIComponent(
    source,
  )}&folder=${encodeURIComponent(folder)}&file_id=${encodeURIComponent(fileId)}${keyQs()}`;
}

export function videoLargoUrl(
  source: string, folder: string, producto: string, descargar = false,
): string {
  return `${base()}${ROOT}/video?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}&descargar=${descargar}${keyQs()}`;
}
