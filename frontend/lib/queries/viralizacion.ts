"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  PonentesListResponse,
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

export function useGenerateViralizacion() {
  return useMutation<ViralizacionGenerateResponse, Error, ViralizacionGenerateRequest>({
    mutationFn: (body) =>
      api.post<ViralizacionGenerateResponse>(`${ROOT}/generate`, body),
  });
}
