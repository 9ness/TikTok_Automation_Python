"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  PresidentsBatchEnqueueResponse,
  PresidentsEnqueueRequest,
} from "@/lib/types/creator-reward";

const ROOT = "/api/v1/creator-reward/presidents";

export const presidentsKeys = {
  all: ["cr-presidents"] as const,
  presets: () => [...presidentsKeys.all, "presets"] as const,
  preset: (name: string) => [...presidentsKeys.all, "preset", name] as const,
};

export function useEnqueuePresidents() {
  return useMutation<PresidentsBatchEnqueueResponse, Error, PresidentsEnqueueRequest>({
    mutationFn: (input) => api.post<PresidentsBatchEnqueueResponse>(`${ROOT}/enqueue`, input),
  });
}

export function usePresidentsPresets() {
  return useQuery<{ items: string[]; total: number }>({
    queryKey: presidentsKeys.presets(),
    queryFn: () => api.get<{ items: string[]; total: number }>(`${ROOT}/presets`),
  });
}

export function usePresidentsPreset(name: string | null) {
  return useQuery<{ name: string; config: Record<string, unknown> }>({
    queryKey: presidentsKeys.preset(name ?? ""),
    queryFn: () =>
      api.get<{ name: string; config: Record<string, unknown> }>(
        `${ROOT}/presets/${encodeURIComponent(name!)}`,
      ),
    enabled: Boolean(name),
  });
}

export function useSavePresidentsPreset() {
  const qc = useQueryClient();
  return useMutation<void, Error, { name: string; config: Record<string, unknown> }>({
    mutationFn: ({ name, config }) =>
      api.put<void>(`${ROOT}/presets/${encodeURIComponent(name)}`, config),
    onSuccess: () => qc.invalidateQueries({ queryKey: presidentsKeys.presets() }),
  });
}

export function useDeletePresidentsPreset() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) => api.del<void>(`${ROOT}/presets/${encodeURIComponent(name)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: presidentsKeys.presets() }),
  });
}
