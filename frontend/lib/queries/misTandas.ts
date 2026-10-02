"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";

const ROOT = "/api/v1/mis-tandas";

/** Un vídeo montado, venga del nicho que venga. `id` dice a qué documento
 *  escribe cada botón (ver `src/mis_tandas/fuentes.py`). */
export interface VideoTanda {
  id: string;
  nicho: "pov" | "largo" | "mm";
  nicho_label: string;
  hashtags_nicho: string;
  pantalla: string;
  modo: string;
  modo_label: string;
  formato: string;
  source: string;
  carpeta: string;
  carpeta_label: string;
  producto: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  emojis: string;
  product_url: string;
  uploaded: boolean;
  uploaded_at: number;
  sin_stock: boolean;
  rehacer: boolean;
  rehacer_nota: string;
  rehecho: boolean;
  puede_rehacer: boolean;
  video_listo_at: number;
  flecha: boolean;
  musica: { busqueda: string; alternativas: string[]; estilo: string } | null;
}

export interface Tanda {
  numero: number;
  total: number;
  subidos: number;
  sin_stock: number;
  rehacer: number;
  abierta: boolean;
  nichos: string[];
  fecha?: string;
  temporada?: string;
  items: VideoTanda[];
}

export interface MisTandasResponse {
  usuario: string;
  por_tanda: number;
  total: number;
  subidos: number;
  sin_stock: number;
  subidos_hoy: number;
  cerradas: number;
  abiertas: number;
  tandas: Tanda[];
}

export const misTandasKeys = {
  all: ["mis-tandas"] as const,
  lista: (todas: boolean) => [...misTandasKeys.all, todas ? "todas" : "abiertas"] as const,
};

/** Las tandas del usuario con sesión. Por defecto solo las ABIERTAS: ness
 *  lleva cientos de vídeos subidos y no hace falta traerlos cada vez. */
export function useMisTandas(todas = false) {
  return useQuery<MisTandasResponse>({
    queryKey: misTandasKeys.lista(todas),
    queryFn: () => api.get<MisTandasResponse>(`${ROOT}${todas ? "?todas=true" : ""}`),
    staleTime: 30 * 1000,
  });
}

/** Releer los nichos ya (lo nuevo que hayan montado los agentes). */
export function useRecargarTandas() {
  const qc = useQueryClient();
  return useMutation<MisTandasResponse, Error, boolean>({
    mutationFn: (todas) =>
      api.get<MisTandasResponse>(`${ROOT}?fresco=true${todas ? "&todas=true" : ""}`),
    onSuccess: (d, todas) => qc.setQueryData(misTandasKeys.lista(todas), d),
    onError: () => toast.error("No se pudieron recargar las tandas."),
  });
}

type Cambio = {
  id: string;
  uploaded?: boolean;
  sin_stock?: boolean;
  rehacer?: boolean;
  rehacer_nota?: string;
};

function aplicar(d: MisTandasResponse | undefined, c: Cambio, producto?: VideoTanda) {
  if (!d) return d;
  const tandas = d.tandas.map((t) => {
    const items = t.items.map((v) => {
      if (v.id === c.id) {
        return {
          ...v,
          ...(c.uploaded !== undefined ? { uploaded: c.uploaded } : {}),
          ...(c.sin_stock !== undefined ? { sin_stock: c.sin_stock } : {}),
          ...(c.rehacer !== undefined
            ? { rehacer: c.rehacer, rehacer_nota: c.rehacer ? (c.rehacer_nota ?? "") : "" }
            : {}),
        };
      }
      // «Sin stock» es del PRODUCTO: el mismo producto con vídeo de POV y de
      // Largo se marca en los dos.
      if (
        c.sin_stock !== undefined && producto && producto.nicho !== "mm" && v.nicho !== "mm" &&
        v.source === producto.source && v.carpeta === producto.carpeta && v.producto === producto.producto
      ) {
        return { ...v, sin_stock: c.sin_stock };
      }
      return v;
    });
    return {
      ...t,
      items,
      subidos: items.filter((v) => v.uploaded).length,
      sin_stock: items.filter((v) => v.sin_stock && !v.uploaded).length,
      rehacer: items.filter((v) => v.rehacer && !v.uploaded).length,
    };
  });
  return {
    ...d,
    tandas,
    subidos: d.subidos + tandas.reduce((n, t) => n + t.subidos, 0) - d.tandas.reduce((n, t) => n + t.subidos, 0),
  };
}

/** Subido / sin stock / rehacer. Se pinta AL MOMENTO y vuelve atrás si la
 *  API falla. El orden no se mueve: la tanda se queda donde estaba. */
export function useMarcarTanda(todas = false) {
  const qc = useQueryClient();
  const key = misTandasKeys.lista(todas);
  return useMutation<unknown, Error, Cambio & { video?: VideoTanda }, MisTandasResponse | undefined>({
    mutationFn: ({ video: _v, ...body }) => api.post(`${ROOT}/estado`, body),
    onMutate: async ({ video, ...c }) => {
      await qc.cancelQueries({ queryKey: key });
      const antes = qc.getQueryData<MisTandasResponse>(key);
      qc.setQueryData<MisTandasResponse>(key, (d) => aplicar(d, c, video));
      return antes;
    },
    onError: (e, _c, antes) => {
      if (antes) qc.setQueryData(key, antes);
      toast.error(`No se pudo guardar: ${e.message}`);
    },
    // Las pantallas de cada nicho enseñan el mismo estado: quedan como viejas
    // para la próxima vez que se abran, sin recargarlas ahora.
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["nicho-ropa"], refetchType: "none" });
      void qc.invalidateQueries({ queryKey: ["nicho-pov-bof"], refetchType: "none" });
      void qc.invalidateQueries({ queryKey: ["pov-bof-largo"], refetchType: "none" });
    },
  });
}

function conApiKey(path: string): string {
  const key = process.env.NEXT_PUBLIC_API_KEY;
  return `${api.baseUrl}${path}${key ? `&api_key=${encodeURIComponent(key)}` : ""}`;
}

/** El vídeo. Los del multimodo los sirve su nicho; el resto, este router. */
export function buildVideoTandaUrl(v: VideoTanda, descargar = false): string {
  if (v.nicho === "mm") {
    return conApiKey(
      `/api/v1/nicho-ropa/video?producto=${encodeURIComponent(v.producto)}` +
        `&carpeta=${encodeURIComponent(v.carpeta)}&v=${v.video_listo_at}` +
        `&modo=${encodeURIComponent(v.formato)}` +
        (descargar ? "&descargar=true" : ""),
    );
  }
  return conApiKey(
    `${ROOT}/video?id=${encodeURIComponent(v.id)}&v=${Math.round(v.video_listo_at)}` +
      (descargar ? "&descargar=true" : ""),
  );
}

export function buildFotoTandaUrl(v: VideoTanda, ancho = 96): string {
  return conApiKey(`${ROOT}/foto?id=${encodeURIComponent(v.id)}&w=${ancho}`);
}
