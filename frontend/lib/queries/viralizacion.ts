"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
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

export function useEstilos() {
  return useQuery<StylesListResponse>({
    queryKey: [...viralizacionKeys.all, "estilos"] as const,
    queryFn: () => api.get<StylesListResponse>(`${ROOT}/estilos`),
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
