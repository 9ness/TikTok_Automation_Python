"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  EnqueueRequest,
  EnqueueResponse,
  GenerationListResponse,
  GenerationResponse,
} from "@/lib/types/generation";

const ROOT = "/api/v1/generations";

export interface GenerationsFilters {
  limit?: number;
  offset?: number;
  username?: string;
  product_id?: string;
  status?: string;
  include_deleted?: boolean;
}

export const generationKeys = {
  all: ["generations"] as const,
  list: (filters?: GenerationsFilters) =>
    [...generationKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...generationKeys.all, "detail", id] as const,
};

function buildQS(filters?: GenerationsFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  if (filters.username) params.set("username", filters.username);
  if (filters.product_id) params.set("product_id", filters.product_id);
  if (filters.status) params.set("status", filters.status);
  if (filters.include_deleted) params.set("include_deleted", "true");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useGenerations(filters?: GenerationsFilters) {
  return useQuery<GenerationListResponse>({
    queryKey: generationKeys.list(filters),
    queryFn: () => api.get<GenerationListResponse>(`${ROOT}${buildQS(filters)}`),
  });
}

export function useGeneration(id: string | null | undefined) {
  return useQuery<GenerationResponse>({
    queryKey: generationKeys.detail(id ?? ""),
    queryFn: () => api.get<GenerationResponse>(`${ROOT}/${id}`),
    enabled: Boolean(id),
  });
}

export function useEnqueueGeneration() {
  const qc = useQueryClient();
  return useMutation<EnqueueResponse, Error, EnqueueRequest>({
    mutationFn: (input) => api.post<EnqueueResponse>(`${ROOT}/enqueue`, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: generationKeys.all }),
  });
}

export function useRegenerateGeneration() {
  const qc = useQueryClient();
  return useMutation<
    EnqueueResponse,
    Error,
    { generationId: string; overrides?: Record<string, unknown> }
  >({
    mutationFn: ({ generationId, overrides }) =>
      api.post<EnqueueResponse>(`${ROOT}/${generationId}/regenerate`, {
        overrides: overrides ?? {},
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: generationKeys.all }),
  });
}

export function useDeleteGeneration() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.del<void>(`${ROOT}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: generationKeys.all }),
  });
}
