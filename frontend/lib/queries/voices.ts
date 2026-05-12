"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { VoiceListResponse } from "@/lib/types/voice";

export interface VoicesFilters {
  language?: string;
  gender?: string;
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
