"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const ROOT = "/api/v1/tiktok-shop/presets";

export type ShopPresetKind = "auto_video" | "veo3" | "nano_banana";

export interface ShopPreset {
  name: string;
  config: Record<string, unknown>;
}

export interface ShopPresetList {
  items: string[];
  total: number;
}

export const shopPresetKeys = {
  all: ["tiktok-shop", "presets"] as const,
  list: (userId: string, productId: string, kind: ShopPresetKind) =>
    [...shopPresetKeys.all, "list", userId, productId, kind] as const,
  one: (userId: string, productId: string, kind: ShopPresetKind, name: string) =>
    [...shopPresetKeys.all, "one", userId, productId, kind, name] as const,
};

function basePath(userId: string, productId: string, kind: ShopPresetKind) {
  return `${ROOT}/${encodeURIComponent(userId)}/${encodeURIComponent(productId)}/${encodeURIComponent(kind)}`;
}

export function useShopPresets(
  userId: string,
  productId: string,
  kind: ShopPresetKind,
  enabled = true,
) {
  return useQuery<ShopPresetList>({
    queryKey: shopPresetKeys.list(userId, productId, kind),
    queryFn: () => api.get<ShopPresetList>(basePath(userId, productId, kind)),
    enabled: enabled && Boolean(userId && productId),
  });
}

export function useShopPreset(
  userId: string,
  productId: string,
  kind: ShopPresetKind,
  name: string | null,
) {
  return useQuery<ShopPreset>({
    queryKey: shopPresetKeys.one(userId, productId, kind, name ?? ""),
    queryFn: () =>
      api.get<ShopPreset>(`${basePath(userId, productId, kind)}/${encodeURIComponent(name!)}`),
    enabled: Boolean(userId && productId && name),
    retry: false,
  });
}

export function useSaveShopPreset(
  userId: string,
  productId: string,
  kind: ShopPresetKind,
) {
  const qc = useQueryClient();
  return useMutation<ShopPreset, Error, { name: string; config: Record<string, unknown> }>({
    mutationFn: ({ name, config }) =>
      api.put<ShopPreset>(
        `${basePath(userId, productId, kind)}/${encodeURIComponent(name)}`,
        config,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: shopPresetKeys.all });
    },
  });
}

export function useDeleteShopPreset(
  userId: string,
  productId: string,
  kind: ShopPresetKind,
) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) =>
      api.del<void>(`${basePath(userId, productId, kind)}/${encodeURIComponent(name)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: shopPresetKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Fase 5 — Replicar viral
// ---------------------------------------------------------------------------
export interface ReplicateViralResponse {
  config: Record<string, unknown>;
  detected: Record<string, unknown>;
  cost_breakdown: {
    gemini_usd: number;
    whisper_usd: number;
    total_usd: number;
    gemini_model: string;
    input_tokens_est: number;
    output_tokens_est: number;
  };
}

export interface ReplicateViralInput {
  file: File;
  user_id: string;
  product_id: string;
  target_kind: ShopPresetKind;
  same_product: boolean;
  gemini_model: string;
}

export function useReplicateViral() {
  return useMutation<ReplicateViralResponse, Error, ReplicateViralInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("user_id", input.user_id);
      fd.append("product_id", input.product_id);
      fd.append("target_kind", input.target_kind);
      fd.append("same_product", String(input.same_product));
      fd.append("gemini_model", input.gemini_model);
      return api.post<ReplicateViralResponse>(
        "/api/v1/tiktok-shop/replicate-viral",
        fd,
      );
    },
  });
}
