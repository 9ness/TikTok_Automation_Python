"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  CarpetasListResponse,
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
