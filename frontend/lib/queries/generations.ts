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

// ---------------------------------------------------------------------------
// Preview prompts (Veo3 / Nano Banana) — síncronos, NO encolan
// ---------------------------------------------------------------------------
export interface PreviewVeo3Request {
  username: string;
  product_id: string;
  hook_category?: string;
  hook_custom?: string | null;
  target_audience?: string;
  language?: string;
}

export interface PreviewVeo3Response {
  prompt: string;
  hook_text: string;
  voiceover_script: string;
  style: string;
}

export interface PreviewNanoBananaRequest {
  username: string;
  product_id: string;
  n_angles?: number;
  use_cases?: string[];
}

export interface PreviewNanoBananaResponse {
  prompt: string;
  n_angles: number;
}

export function usePreviewVeo3Prompt() {
  return useMutation<PreviewVeo3Response, Error, PreviewVeo3Request>({
    mutationFn: (input) =>
      api.post<PreviewVeo3Response>(`${ROOT}/preview/veo3`, input),
  });
}

export function usePreviewNanoBananaPrompt() {
  return useMutation<PreviewNanoBananaResponse, Error, PreviewNanoBananaRequest>({
    mutationFn: (input) =>
      api.post<PreviewNanoBananaResponse>(`${ROOT}/preview/nano-banana`, input),
  });
}

// ---------------------------------------------------------------------------
// Fase 4 — Test batches (variantes A/B)
// ---------------------------------------------------------------------------
export const VARYABLE_DIMENSIONS = [
  "hook_category",
  "voice_id",
  "strategy",
  "duration_seconds",
  "hook_box_animation",
] as const;

export type VaryableDimension = (typeof VARYABLE_DIMENSIONS)[number];

export interface TestBatchRequest {
  base: EnqueueRequest;
  vary: VaryableDimension[];
  count: number;
  custom_values?: Record<string, string[]> | null;
}

export interface TestBatchResponse {
  test_batch_id: string;
  job_ids: string[];
  estimated_cost_total: number;
  variants: Record<string, unknown>[];
}

export function useEnqueueTestBatch() {
  const qc = useQueryClient();
  return useMutation<TestBatchResponse, Error, TestBatchRequest>({
    mutationFn: (input) => api.post<TestBatchResponse>(`${ROOT}/test-batch`, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: generationKeys.all }),
  });
}
