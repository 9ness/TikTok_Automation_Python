/**
 * Hooks generator — mutations para variantes y hooks temáticos.
 */

import { useMutation } from "@tanstack/react-query";

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
