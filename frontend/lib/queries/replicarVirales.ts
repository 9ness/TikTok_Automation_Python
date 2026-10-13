"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { conClave } from "@/lib/queries/replicarCarrusel";

/** «Replicar virales» (`src/replicar_viral/video.py`): el MP4 YA MONTADO de un
 *  viral replicado (con IA en Omni o sin IA, vídeo real). Se registra aquí y
 *  sale solo en Mis tandas (`rv|<id>`). */

const ROOT = "/api/v1/replicar-viral/video";

export type ModoReplicaVideo = "con_ia" | "sin_ia";

export interface ReplicaVideo {
  id: string;
  tipo: "video";
  modo: ModoReplicaVideo;
  modo_label: string;
  creado_at: number;
  video_listo_at: number;
  url: string;
  titulo: string;
  tienda: string;
  product_id: string;
  product_url: string;
  caption: string;
  hashtags: string[];
  prompts: number;
  notas: string;
  uploaded: boolean;
  sin_stock: boolean;
  rehacer: boolean;
  rehacer_nota: string;
  rehecho: boolean;
  /** Id de la fila en Mis tandas. */
  id_tandas: string;
  /** El MP4 sigue en el Drive. */
  existe: boolean;
}

export const replicarViralesKeys = {
  all: ["replicar-virales"] as const,
  lista: (modo: string) => [...replicarViralesKeys.all, "lista", modo] as const,
};

export function urlVideoReplica(r: Pick<ReplicaVideo, "id" | "video_listo_at">, descargar = false): string {
  return conClave(`${ROOT}/${r.id}/mp4?v=${Math.round(r.video_listo_at)}` + (descargar ? "&descargar=true" : ""));
}

export function useReplicasVideo(modo: string) {
  return useQuery<{ modos: Record<string, string>; items: ReplicaVideo[] }>({
    queryKey: replicarViralesKeys.lista(modo),
    queryFn: () => api.get(`${ROOT}${modo ? `?modo=${encodeURIComponent(modo)}` : ""}`),
    staleTime: 30_000,
  });
}

export interface AltaReplicaVideo {
  file: File;
  modo: ModoReplicaVideo;
  titulo: string;
  product_url: string;
  url_viral: string;
  tienda: string;
  caption: string;
  hashtags: string;
  prompts: string;
  notas: string;
  replica_id?: string;
  para?: string;
}

export function useRegistrarReplicaVideo() {
  const qc = useQueryClient();
  return useMutation<ReplicaVideo, Error, AltaReplicaVideo>({
    mutationFn: (v) => {
      const fd = new FormData();
      fd.append("file", v.file);
      for (const k of ["modo", "titulo", "product_url", "url_viral", "tienda", "caption", "hashtags", "prompts", "notas"] as const) {
        fd.append(k, v[k] ?? "");
      }
      if (v.replica_id) fd.append("replica_id", v.replica_id);
      if (v.para) fd.append("para", v.para);
      return api.post<ReplicaVideo>(ROOT, fd);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: replicarViralesKeys.all });
      // Sale en Mis tandas: que la próxima vez relea.
      void qc.invalidateQueries({ queryKey: ["mis-tandas"], refetchType: "none" });
    },
  });
}

export function useBorrarReplicaVideo() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean }, Error, string>({
    mutationFn: (id) => api.del(`${ROOT}/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: replicarViralesKeys.all });
      void qc.invalidateQueries({ queryKey: ["mis-tandas"], refetchType: "none" });
    },
  });
}
