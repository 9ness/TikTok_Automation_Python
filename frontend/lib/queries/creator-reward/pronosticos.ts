"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  PronosticosBatchEnqueueResponse,
  PronosticosEnqueueRequest,
  PronosticosLatestDateResponse,
  PronosticosVersionsResponse,
} from "@/lib/types/creator-reward";

const ROOT = "/api/v1/creator-reward/pronosticos";

export const pronosticosKeys = {
  all: ["cr-pronosticos"] as const,
  versions: (date: string) => [...pronosticosKeys.all, "versions", date] as const,
  latestDate: () => [...pronosticosKeys.all, "latest-date"] as const,
};

export function usePronosticosVersions(date: string | null) {
  return useQuery<PronosticosVersionsResponse>({
    queryKey: pronosticosKeys.versions(date ?? ""),
    queryFn: () =>
      api.get<PronosticosVersionsResponse>(`${ROOT}/versions?date=${date}`),
    enabled: Boolean(date),
  });
}

export function useLatestPronosticosDate() {
  return useQuery<PronosticosLatestDateResponse>({
    queryKey: pronosticosKeys.latestDate(),
    queryFn: () => api.get<PronosticosLatestDateResponse>(`${ROOT}/latest-date`),
  });
}

export function useEnqueuePronosticos() {
  return useMutation<PronosticosBatchEnqueueResponse, Error, PronosticosEnqueueRequest>({
    mutationFn: (input) =>
      api.post<PronosticosBatchEnqueueResponse>(`${ROOT}/enqueue`, input),
  });
}
