"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  ConfigUGCResponse,
  ProductosUGCResponse,
} from "@/lib/types/nichoGeneral";

const ROOT = "/api/v1/nicho-general";

export const nichoGeneralKeys = {
  config: () => ["nicho-general", "config"] as const,
  productos: (source: string, folder: string, gancho: string, duracion: string) =>
    ["nicho-general", "productos", source, folder, gancho, duracion] as const,
};

/** Los ganchos y duraciones que existen. Los manda el backend porque son del
 *  curso: cuando publique otro formato, la pantalla no se toca. */
export function useConfigUGC() {
  return useQuery<ConfigUGCResponse>({
    queryKey: nichoGeneralKeys.config(),
    queryFn: () => api.get<ConfigUGCResponse>(`${ROOT}/config`),
    staleTime: 60 * 60 * 1000,
  });
}

/** Mientras haya un montaje en curso se sondea solo, y para al terminar. */
export function useProductosUGC(
  source: string, folder: string, gancho: string, duracion: string,
) {
  return useQuery<ProductosUGCResponse>({
    queryKey: nichoGeneralKeys.productos(source, folder, gancho, duracion),
    queryFn: () =>
      api.get<ProductosUGCResponse>(
        `${ROOT}/productos?source=${encodeURIComponent(source)}` +
          `&folder=${encodeURIComponent(folder)}` +
          `&gancho=${encodeURIComponent(gancho)}&duracion=${encodeURIComponent(duracion)}`,
      ),
    enabled: Boolean(source && folder),
    refetchInterval: (q) =>
      (q.state.data?.items ?? []).some((p) => p.montando) ? 5000 : false,
  });
}

export function useEscenasLote() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string },
    Error,
    {
      source: string; folder?: string; gancho: string; duracion: string;
      rehacer?: boolean; productos?: string[];
      /** Pedir la versión del otro sexo de UN producto. */
      sexo?: string;
    }
  >({
    mutationFn: (body) => api.post(`${ROOT}/escenas/lote`, body),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["nicho-general", "productos"] }),
  });
}

export function useMontarUGC() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string },
    Error,
    { source: string; folder: string; producto: string; gancho: string; duracion: string }
  >({
    mutationFn: (body) => api.post(`${ROOT}/montar`, body),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["nicho-general", "productos"] }),
  });
}

export function useLimpiarClipsUGC() {
  const qc = useQueryClient();
  return useMutation<
    { clips: number },
    Error,
    { source: string; folder: string; producto: string; gancho: string; duracion: string }
  >({
    mutationFn: (body) => api.post(`${ROOT}/clips/limpiar`, body),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["nicho-general", "productos"] }),
  });
}

export function useEstadoUGC() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    {
      source: string; folder: string; producto: string;
      gancho: string; duracion: string;
      uploaded?: boolean; sold?: boolean; en_escaparate?: boolean;
      /** En qué nicho cae: lo pone la IA y se corrige a mano. */
      nicho?: string;
      personaje?: string; personaje_sexo?: string;
    }
  >({
    mutationFn: (body) => api.post(`${ROOT}/producto/estado`, body),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["nicho-general", "productos"] }),
  });
}

/** Sube UN clip. De uno en uno para poder enseñar su porcentaje; el orden no
 *  se pregunta, lo decide el montaje escuchándolos. */
export function subirClipUGC(
  file: File,
  datos: { source: string; folder: string; producto: string; gancho: string; duracion: string },
  onProgreso?: (pct: number) => void,
): Promise<{ clips: number }> {
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(datos).forEach(([k, v]) => fd.append(k, v));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${api.baseUrl}${ROOT}/clips/subir`);
    const key = process.env.NEXT_PUBLIC_API_KEY;
    if (key) xhr.setRequestHeader("X-API-Key", key);
    // Sin `withCredentials`: la API va en el mismo origen, así que la cookie
    // de sesión viaja igual, y en la APK esa bandera daba problemas. Es como
    // sube los clips el Nicho Ropa, que funciona.
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgreso) {
        onProgreso(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () =>
      xhr.status < 300
        ? resolve(JSON.parse(xhr.responseText || "{}"))
        : reject(new Error(xhr.responseText || `Error ${xhr.status}`));
    xhr.onerror = () => reject(new Error("No se pudo subir el clip."));
    xhr.send(fd);
  });
}

export function buildVideoUGCUrl(
  datos: { source: string; folder: string; producto: string; gancho: string; duracion: string },
  descargar = false,
): string {
  const qs = new URLSearchParams({ ...datos, descargar: String(descargar) });
  const key = process.env.NEXT_PUBLIC_API_KEY;
  if (key) qs.set("api_key", key);
  return `${api.baseUrl}${ROOT}/video?${qs.toString()}`;
}
