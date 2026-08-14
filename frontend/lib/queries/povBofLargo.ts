"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { ANCHO_CHIP, ANCHO_MINIATURA, ANCHO_VISOR } from "@/lib/queries/nichoPovBof";

// Se re-exportan para que las pantallas de este nicho no tengan que importar
// del POV BOF solo para pedir la foto al tamaño que toca.
export { ANCHO_CHIP, ANCHO_VISOR };
import type { VendidoItem } from "@/lib/types/nichoPovBof";
import type {
  ClipLargoUploadResponse,
  EstadoLargoRequest,
  FoldersLargoResponse,
  MarkCompletedLargoResponse,
  ProductoLargo,
  ProductosLargoResponse,
  VocesLargo,
} from "@/lib/types/povBofLargo";

const ROOT = "/api/v1/nicho-pov-bof-largo";
// El ranking de vendidos es GLOBAL entre todos los nichos (mismo índice, no se
// clasifica por nicho) y vive en el POV BOF.
const POV_ROOT = "/api/v1/nicho-pov-bof";

export const largoKeys = {
  all: ["pov-bof-largo"] as const,
  voces: () => [...largoKeys.all, "voces"] as const,
  sources: () => [...largoKeys.all, "sources"] as const,
  folders: (source: string) => [...largoKeys.all, "folders", source] as const,
  productos: (source: string, folder: string) =>
    [...largoKeys.all, "productos", source, folder] as const,
  vendidos: (source: string) => [...largoKeys.all, "vendidos", source] as const,
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

/** Carpetas del Drive compartido con el progreso PROPIO de este nicho. */
export function useFoldersLargo(source: string) {
  return useQuery<FoldersLargoResponse>({
    queryKey: largoKeys.folders(source),
    queryFn: () =>
      api.get<FoldersLargoResponse>(
        `${ROOT}/folders?source=${encodeURIComponent(source)}`,
      ),
    enabled: Boolean(source),
  });
}

export function useMarkCompletedLargo(source: string) {
  const qc = useQueryClient();
  return useMutation<
    MarkCompletedLargoResponse,
    Error,
    { source: string; folder: string; completed: boolean }
  >({
    mutationFn: (body) => api.post<MarkCompletedLargoResponse>(`${ROOT}/complete`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: largoKeys.folders(source) }),
  });
}

/** TODOS los productos de la fuente, de más a menos ventas (solo Top
 *  vendidos: ahí el sitio de cada producto es fijo y el ranking solo se ve
 *  juntando las carpetas). Cada item trae su `folder`. */
export function useProductosTodosLargo(source: string, activo: boolean) {
  return useQuery<ProductosLargoResponse>({
    queryKey: [...largoKeys.productos(source, "*todos*")],
    queryFn: () =>
      api.get<ProductosLargoResponse>(
        `${ROOT}/productos-todos?source=${encodeURIComponent(source)}`,
      ),
    enabled: Boolean(source && activo),
    refetchInterval: (q) => (q.state.data?.montando ? 5000 : false),
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

/** Escaparate / Subido / Vendió — progreso INDIVIDUAL del Largo. */
export function useSetEstadoLargo() {
  const qc = useQueryClient();
  return useMutation<ProductoLargo, Error, EstadoLargoRequest>({
    mutationFn: (body) => api.post<ProductoLargo>(`${ROOT}/producto/estado`, body),
    onSuccess: (updated, vars) => {
      qc.setQueryData<ProductosLargoResponse>(
        largoKeys.productos(vars.source, vars.folder),
        (old) =>
          old
            ? {
                ...old,
                items: old.items.map((p) =>
                  p.producto === updated.producto ? updated : p,
                ),
              }
            : old,
      );
      // Puede haber entrado o salido del ranking de vendidos.
      void qc.invalidateQueries({ queryKey: largoKeys.vendidos(vars.source) });
      if (vars.uploaded !== undefined) {
        void qc.invalidateQueries({ queryKey: ["cuotas", "hoy"] });
      }
    },
  });
}

/** Ranking de vendidos GLOBAL (índice único compartido con todos los nichos). */
export function useVendidosLargo(source: string) {
  return useQuery<VendidoItem[]>({
    queryKey: largoKeys.vendidos(source),
    queryFn: async () =>
      (await api.get<{ items: VendidoItem[] }>(
        `${POV_ROOT}/vendidos?source=${encodeURIComponent(source)}`,
      )).items ?? [],
    enabled: Boolean(source),
  });
}

/** Suma (o resta) unidades vendidas. Reordena el ranking del nicho. */
export function useSumarUnidadesLargo() {
  const qc = useQueryClient();
  return useMutation<
    { items: VendidoItem[] },
    Error,
    { source: string; folder: string; producto: string; delta: number }
  >({
    mutationFn: (body) =>
      api.post<{ items: VendidoItem[] }>(`${POV_ROOT}/vendidos/unidades`, body),
    onSuccess: (_res, vars) =>
      void qc.invalidateQueries({ queryKey: largoKeys.vendidos(vars.source) }),
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

/** La foto se sirve desde el POV BOF: es la misma de Drive, no se duplica.
 *
 *  `ancho` la encoge en el servidor — ver `ANCHO_MINIATURA` en `nichoPovBof.ts`:
 *  sin esto el móvil se queda sin memoria y cierra la app. */
export function fotoLargoUrl(
  source: string, folder: string, fileId: string, ancho: number | null = ANCHO_MINIATURA,
): string {
  const w = ancho ? `&w=${ancho}` : "";
  return `${base()}/api/v1/nicho-pov-bof/photo?source=${encodeURIComponent(
    source,
  )}&folder=${encodeURIComponent(folder)}&file_id=${encodeURIComponent(fileId)}${w}${keyQs()}`;
}

export function videoLargoUrl(
  source: string, folder: string, producto: string, version = 0, descargar = false,
): string {
  return `${base()}${ROOT}/video?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}&v=${version}&descargar=${descargar}${keyQs()}`;
}
