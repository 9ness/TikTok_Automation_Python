"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  CarpetasListResponse,
  CortarClipsResponse,
  PropuestaClips,
  PropuestasListResponse,
  SubirAudioLargoResponse,
  PonentesListResponse,
  RoundPlanResponse,
  StylesListResponse,
  ViralizacionGenerateRequest,
  ViralizacionGenerateResponse,
} from "@/lib/types/viralizacion";

const ROOT = "/api/v1/viralizacion";

export const viralizacionKeys = {
  all: ["viralizacion"] as const,
  ponentes: () => [...viralizacionKeys.all, "ponentes"] as const,
};

export function usePonentes() {
  return useQuery<PonentesListResponse>({
    queryKey: viralizacionKeys.ponentes(),
    queryFn: () => api.get<PonentesListResponse>(`${ROOT}/ponentes`),
  });
}

export function useCarpetas() {
  return useQuery<CarpetasListResponse>({
    queryKey: [...viralizacionKeys.all, "carpetas"] as const,
    queryFn: () => api.get<CarpetasListResponse>(`${ROOT}/carpetas`),
  });
}

export function useEstilos() {
  return useQuery<StylesListResponse>({
    queryKey: [...viralizacionKeys.all, "estilos"] as const,
    queryFn: () => api.get<StylesListResponse>(`${ROOT}/estilos`),
  });
}

export interface CuentaEjemplo {
  handle: string;
  nota: string;
}

/** Cuentas de TikTok de referencia. Se guardan en Redis: el operador las
 *  añade sobre la marcha y no tiene sentido desplegar por cada una. */
export function useCuentasEjemplo() {
  return useQuery<CuentaEjemplo[]>({
    queryKey: [...viralizacionKeys.all, "cuentas-ejemplo"] as const,
    queryFn: async () =>
      (await api.get<{ cuentas: CuentaEjemplo[] }>(`${ROOT}/cuentas-ejemplo`))
        .cuentas ?? [],
  });
}

export function useGuardarCuentasEjemplo() {
  const qc = useQueryClient();
  return useMutation<{ cuentas: CuentaEjemplo[] }, Error, CuentaEjemplo[]>({
    mutationFn: (cuentas) =>
      api.post<{ cuentas: CuentaEjemplo[] }>(`${ROOT}/cuentas-ejemplo`, { cuentas }),
    onSuccess: (res) => {
      qc.setQueryData(
        [...viralizacionKeys.all, "cuentas-ejemplo"], res.cuentas ?? [],
      );
    },
  });
}

export interface AudioItem {
  nombre: string;
  duracion_s: number;
}

/** Audios del banco de un ponente, del más largo al más corto. */
export function useAudios(ponente: string | null) {
  return useQuery<AudioItem[]>({
    queryKey: [...viralizacionKeys.all, "audios", ponente ?? ""] as const,
    queryFn: async () =>
      (await api.get<{ items: AudioItem[] }>(
        `${ROOT}/audios?ponente=${encodeURIComponent(ponente ?? "")}`,
      )).items ?? [],
    enabled: Boolean(ponente),
  });
}

/** Cuántos vídeos caen en cada ronda — define cuántos selectores mostrar. */
export function useRoundPlan(ponente: string | null, cantidad: number) {
  return useQuery<RoundPlanResponse>({
    queryKey: [...viralizacionKeys.all, "plan", ponente, cantidad] as const,
    queryFn: () =>
      api.get<RoundPlanResponse>(
        `${ROOT}/plan?ponente=${encodeURIComponent(ponente ?? "")}&cantidad=${cantidad}`,
      ),
    enabled: Boolean(ponente) && cantidad > 0,
  });
}

export function useGenerateViralizacion() {
  return useMutation<ViralizacionGenerateResponse, Error, ViralizacionGenerateRequest>({
    mutationFn: (body) =>
      api.post<ViralizacionGenerateResponse>(`${ROOT}/generate`, body),
  });
}

// ---------------------------------------------------------------------------
// Cortar audios largos de YouTube en clips de ~1 minuto
// ---------------------------------------------------------------------------
const propuestasKey = [...viralizacionKeys.all, "propuestas"] as const;

/** Propuestas de corte pendientes de revisar.
 *
 *  Refresca sola cada 20s: el análisis (Whisper + Gemini) corre en la cola y
 *  la propuesta aparece cuando el job acaba, sin que haya que recargar. */
export function usePropuestasClips() {
  return useQuery<PropuestaClips[]>({
    queryKey: propuestasKey,
    queryFn: async () =>
      (await api.get<PropuestasListResponse>(`${ROOT}/audios/propuestas`)).items ?? [],
    refetchInterval: 20_000,
  });
}

export function useSubirAudioLargo() {
  return useMutation<SubirAudioLargoResponse, Error, { ponente: string; file: File }>({
    mutationFn: ({ ponente, file }) => {
      const fd = new FormData();
      fd.append("ponente", ponente);
      fd.append("file", file);
      return api.post<SubirAudioLargoResponse>(`${ROOT}/audios/subir`, fd);
    },
  });
}

export function useCortarClips() {
  const qc = useQueryClient();
  return useMutation<
    CortarClipsResponse,
    Error,
    { ponente: string; fichero: string; indices: number[] }
  >({
    mutationFn: (body) => api.post<CortarClipsResponse>(`${ROOT}/audios/cortar`, body),
    onSuccess: (_res, vars) => {
      void qc.invalidateQueries({ queryKey: propuestasKey });
      // Los clips nuevos entran en el banco → el selector de audios cambia.
      void qc.invalidateQueries({
        queryKey: [...viralizacionKeys.all, "audios", vars.ponente],
      });
    },
  });
}

export function useDescartarPropuesta() {
  const qc = useQueryClient();
  return useMutation<PropuestasListResponse, Error, { ponente: string; fichero: string }>({
    mutationFn: ({ ponente, fichero }) =>
      api.del<PropuestasListResponse>(
        `${ROOT}/audios/propuestas?ponente=${encodeURIComponent(ponente)}` +
          `&fichero=${encodeURIComponent(fichero)}`,
      ),
    onSuccess: (res) => qc.setQueryData(propuestasKey, res.items ?? []),
  });
}
