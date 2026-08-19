"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  CarpetaRopaPersonas,
  ChicaInfo,
  PrendasPersonasResponse,
  RopaPersonasPrompts,
} from "@/lib/types/nichoRopaPersonas";

const ROOT = "/api/v1/nicho-ropa-personas";

export const ropaPersonasKeys = {
  all: ["nicho-ropa-personas"] as const,
  chicas: () => [...ropaPersonasKeys.all, "chicas"] as const,
  prompts: () => [...ropaPersonasKeys.all, "prompts"] as const,
  carpetas: () => [...ropaPersonasKeys.all, "carpetas"] as const,
  prendas: (carpeta: string) => [...ropaPersonasKeys.all, "prendas", carpeta] as const,
};

// --- Modelos (chicas) -------------------------------------------------------

export function useChicas() {
  return useQuery<ChicaInfo[]>({
    queryKey: ropaPersonasKeys.chicas(),
    queryFn: async () =>
      (await api.get<{ items: ChicaInfo[] }>(`${ROOT}/chicas`)).items ?? [],
  });
}

/** Sube una foto y crea la ficha con Gemini. Gasta UNA llamada. */
export function useCrearChica() {
  const qc = useQueryClient();
  return useMutation<ChicaInfo[], Error, { nombre: string; foto: File }>({
    mutationFn: async ({ nombre, foto }) => {
      const fd = new FormData();
      fd.append("nombre", nombre);
      fd.append("foto", foto);
      const r = await api.post<{ items: ChicaInfo[] }>(`${ROOT}/chicas`, fd);
      return r.items ?? [];
    },
    onSuccess: (items) => qc.setQueryData(ropaPersonasKeys.chicas(), items),
  });
}

export function useBorrarChica() {
  const qc = useQueryClient();
  return useMutation<ChicaInfo[], Error, string>({
    mutationFn: async (id) =>
      (await api.del<{ items: ChicaInfo[] }>(
        `${ROOT}/chicas?id=${encodeURIComponent(id)}`,
      )).items ?? [],
    onSuccess: (items) => qc.setQueryData(ropaPersonasKeys.chicas(), items),
  });
}

// --- Prompts y prendas ------------------------------------------------------

// Sin `Infinity`: un prompt retocado tiene que llegar al móvil (ver
// `usePrompts` del POV BOF, donde esto congeló el prompt viejo).
export function usePromptsRopaPersonas() {
  return useQuery<RopaPersonasPrompts>({
    queryKey: ropaPersonasKeys.prompts(),
    queryFn: () => api.get<RopaPersonasPrompts>(`${ROOT}/prompts`),
    staleTime: 60_000,
  });
}

export function useCarpetasRopaPersonas() {
  return useQuery<CarpetaRopaPersonas[]>({
    queryKey: ropaPersonasKeys.carpetas(),
    queryFn: async () =>
      (await api.get<{ items: CarpetaRopaPersonas[] }>(`${ROOT}/carpetas`)).items ?? [],
    staleTime: Infinity,
  });
}

export function usePrendasPersonas(carpeta: string) {
  return useQuery<PrendasPersonasResponse>({
    queryKey: ropaPersonasKeys.prendas(carpeta),
    queryFn: () =>
      api.get<PrendasPersonasResponse>(
        `${ROOT}/prendas?carpeta=${encodeURIComponent(carpeta)}`,
      ),
    enabled: Boolean(carpeta),
    // Mientras haya un montaje en curso se refresca solo, para que el botón
    // de ver el vídeo aparezca sin recargar.
    refetchInterval: (q) => (q.state.data?.montando ? 5000 : false),
  });
}

export function useExtraerTextosRopaPersonas() {
  const qc = useQueryClient();
  return useMutation<PrendasPersonasResponse, Error, string>({
    mutationFn: (carpeta) =>
      api.post<PrendasPersonasResponse>(
        `${ROOT}/extraer-textos?carpeta=${encodeURIComponent(carpeta)}`,
        {},
      ),
    onSuccess: (data) => qc.setQueryData(ropaPersonasKeys.prendas(data.carpeta), data),
  });
}

/** Título escrito a mano: es el que se quema en el centro del vídeo. */
export function useTituloPrenda() {
  const qc = useQueryClient();
  return useMutation<
    PrendasPersonasResponse,
    Error,
    { carpeta: string; producto: string; titulo: string }
  >({
    mutationFn: (body) =>
      api.post<PrendasPersonasResponse>(`${ROOT}/prenda/titulo`, body),
    onSuccess: (data) => qc.setQueryData(ropaPersonasKeys.prendas(data.carpeta), data),
  });
}

/** Mete o saca la prenda del escaparate. El estado es ÚNICO por producto
 *  (tienda|nombre) y compartido con los demás nichos: si ya se metió desde el
 *  POV BOF o desde otra carpeta, aquí ya sale hecho. */
export function useSetEstadoRopaPersonas(carpeta: string) {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { producto: string; en_escaparate: boolean }
  >({
    mutationFn: (body) => api.post(`${ROOT}/prenda/estado`, { carpeta, ...body }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ropaPersonasKeys.prendas(carpeta) }),
  });
}

export function useSubirVideoRopaPersonas() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string; message: string },
    Error,
    { carpeta: string; producto: string; file: File }
  >({
    mutationFn: async ({ carpeta, producto, file }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("producto", producto);
      fd.append("carpeta", carpeta);
      return api.post<{ job_id: string; message: string }>(`${ROOT}/video/upload`, fd);
    },
    onSuccess: (_r, vars) =>
      void qc.invalidateQueries({ queryKey: ropaPersonasKeys.prendas(vars.carpeta) }),
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

export function fotoRopaPersonasUrl(fileId: string): string {
  return `${base()}${ROOT}/foto?file_id=${encodeURIComponent(fileId)}${keyQs()}`;
}

export function fotoLimpiaRopaPersonasUrl(carpeta: string, producto: string): string {
  return `${base()}${ROOT}/foto-limpia?carpeta=${encodeURIComponent(
    carpeta,
  )}&producto=${encodeURIComponent(producto)}${keyQs()}`;
}

export function videoRopaPersonasUrl(
  carpeta: string, producto: string, v: number, descargar = false,
): string {
  return `${base()}${ROOT}/video?carpeta=${encodeURIComponent(
    carpeta,
  )}&producto=${encodeURIComponent(producto)}&descargar=${descargar}&v=${v}${keyQs()}`;
}
