"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Voice, VoiceListResponse } from "@/lib/types/voice";

export interface VoicesFilters {
  language?: string;
  gender?: "male" | "female" | "neutral";
  age_group?: "young" | "adult" | "mature";
  include_presets?: boolean;
}

export const voiceKeys = {
  all: ["voices"] as const,
  list: (filters?: VoicesFilters) => [...voiceKeys.all, "list", filters ?? {}] as const,
};

function buildQS(filters?: VoicesFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.language) params.set("language", filters.language);
  if (filters.gender) params.set("gender", filters.gender);
  if (filters.age_group) params.set("age_group", filters.age_group);
  if (filters.include_presets !== undefined) {
    params.set("include_presets", filters.include_presets ? "true" : "false");
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useVoices(filters?: VoicesFilters) {
  return useQuery<VoiceListResponse>({
    queryKey: voiceKeys.list(filters),
    queryFn: () => api.get<VoiceListResponse>(`/api/v1/voices${buildQS(filters)}`),
  });
}

export interface CloneVoiceInput {
  file: File;
  name: string;
  language: "en" | "es";
}

export function useCloneVoice() {
  const qc = useQueryClient();
  return useMutation<Voice, Error, CloneVoiceInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("name", input.name);
      fd.append("language", input.language);
      return api.post<Voice>("/api/v1/voices/clone", fd);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceKeys.all });
    },
  });
}

export function useDeleteVoice() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (voiceId) => api.del<void>(`/api/v1/voices/${voiceId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceKeys.all });
    },
  });
}

/** Construye la URL del sample MP3 de una voz (cacheada server-side). */
export function buildVoiceSampleUrl(voiceId: string): string {
  return `${api.baseUrl}/api/v1/voices/${encodeURIComponent(voiceId)}/sample`;
}

export interface VoicesSyncStatus {
  cached: boolean;
  count?: number;
  age_seconds?: number;
}

export function useVoicesSyncStatus() {
  return useQuery<VoicesSyncStatus>({
    queryKey: ["voices", "sync", "status"],
    queryFn: () => api.get<VoicesSyncStatus>("/api/v1/voices/sync/status"),
    staleTime: 30_000,
  });
}

export function useSyncVoicesCatalog() {
  const qc = useQueryClient();
  return useMutation<{ synced: boolean; count: number }, Error, void>({
    mutationFn: () => api.post<{ synced: boolean; count: number }>("/api/v1/voices/sync"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceKeys.all });
      qc.invalidateQueries({ queryKey: ["voices", "sync", "status"] });
    },
  });
}
