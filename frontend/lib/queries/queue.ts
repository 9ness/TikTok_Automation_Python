"use client";

import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function useCancelJob() {
  return useMutation<void, Error, string>({
    mutationFn: (jobId) => api.del<void>(`/api/v1/queue/${encodeURIComponent(jobId)}`),
  });
}

/**
 * Para jobs en estado FINAL (completed/failed/cancelled): elimina del
 * historial persistente (queue_state.json). Para jobs activos: cancela.
 *
 * El backend hace lo correcto según el estado.
 */
export function useRemoveJob() {
  return useMutation<void, Error, string>({
    mutationFn: (jobId) => api.del<void>(`/api/v1/queue/${encodeURIComponent(jobId)}`),
  });
}

export function useClearRecentJobs() {
  return useMutation<{ removed: number }, Error, void>({
    mutationFn: () => api.del<{ removed: number }>(`/api/v1/queue/recent/all`),
  });
}

/** Health check del backend. Devuelve `{status, version, redis_configured}`. */
export interface HealthResponse {
  status: string;
  version: string;
  redis_configured: boolean;
}

export async function checkApiHealth(): Promise<HealthResponse> {
  return api.get<HealthResponse>("/api/health");
}
