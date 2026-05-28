/**
 * Hooks generator — mutations para variantes, temáticos y favoritos.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface HookVariant {
  text: string;
  rationale: string;
}

export interface HookVariantsResponse {
  angle_detected: string;
  variants: HookVariant[];
}

export interface HookVariantsInput {
  productId: string;
  hook: string;
  n?: number;
  context?: string;
  angle_hint?: string;
}

export function useGenerateHookVariants() {
  return useMutation<HookVariantsResponse, Error, HookVariantsInput>({
    mutationFn: ({ productId, ...body }) =>
      api.post<HookVariantsResponse>(
        `/api/v1/tiktok-shop/products/${productId}/hooks/variants`,
        body,
      ),
  });
}

export interface HookThemed {
  text: string;
  angle: string;
  rationale: string;
}

export interface HookThemedResponse {
  theme_interpretation: string;
  hooks: HookThemed[];
}

export interface HookThemedInput {
  productId: string;
  theme: string;
  n?: number;
}

export function useGenerateThemedHooks() {
  return useMutation<HookThemedResponse, Error, HookThemedInput>({
    mutationFn: ({ productId, ...body }) =>
      api.post<HookThemedResponse>(
        `/api/v1/tiktok-shop/products/${productId}/hooks/themed`,
        body,
      ),
  });
}

/* ─────────── Favoritos ─────────── */
export interface FavoriteHook {
  text: string;
  angle: string;
  kind: string;
  source_preset_id: string | null;
  notes: string;
  saved_at: string;
}

export interface FavoriteHooksListResponse {
  items: FavoriteHook[];
  total: number;
}

export interface AddFavoriteHookInput {
  productId: string;
  text: string;
  angle?: string;
  kind?: string;
  source_preset_id?: string | null;
  notes?: string;
}

const favoriteKeys = {
  list: (pid: string) => ["product", pid, "favorite-hooks"] as const,
};

export function useFavoriteHooks(productId: string | null | undefined) {
  return useQuery<FavoriteHooksListResponse>({
    queryKey: favoriteKeys.list(productId ?? ""),
    queryFn: () =>
      api.get<FavoriteHooksListResponse>(
        `/api/v1/tiktok-shop/products/${productId}/favorite-hooks`,
      ),
    enabled: Boolean(productId),
    staleTime: 30_000,
  });
}

export function useAddFavoriteHook() {
  const qc = useQueryClient();
  return useMutation<FavoriteHook, Error, AddFavoriteHookInput>({
    mutationFn: ({ productId, ...body }) =>
      api.post<FavoriteHook>(
        `/api/v1/tiktok-shop/products/${productId}/favorite-hooks`,
        body,
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: favoriteKeys.list(vars.productId) });
    },
  });
}

export function useDeleteFavoriteHook() {
  const qc = useQueryClient();
  return useMutation<void, Error, { productId: string; text: string }>({
    mutationFn: async ({ productId, text }) => {
      await api.del<void>(
        `/api/v1/tiktok-shop/products/${productId}/favorite-hooks?text=${encodeURIComponent(text)}`,
      );
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: favoriteKeys.list(vars.productId) });
    },
  });
}
