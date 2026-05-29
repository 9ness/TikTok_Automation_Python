/**
 * Feedback loop de rendimiento — vídeos publicados + métricas reales.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface PublishedVideo {
  id: string;
  product_id: string;
  tiktok_url: string;
  tiktok_id: string;
  hook_text: string;
  angle: string;
  kind: string;
  preset_id: string | null;
  sound_used: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  orders: number;
  revenue_eur: number;
  notes: string;
  posted_at: string | null;
  metrics_updated_at: string | null;
  created_at: string;
}

export interface AngleStat {
  angle: string;
  count: number;
  views: number;
  orders: number;
  revenue_eur: number;
  avg_views: number;
}

export interface SoundStat {
  sound: string;
  count: number;
  views: number;
}

export interface PerformanceSummary {
  total_videos: number;
  total_views: number;
  total_orders: number;
  total_revenue_eur: number;
  by_angle: AngleStat[];
  by_sound: SoundStat[];
}

export interface PerformanceListResponse {
  items: PublishedVideo[];
  summary: PerformanceSummary;
}

export interface AddPublishedVideoInput {
  productId: string;
  tiktok_url: string;
  hook_text?: string;
  angle?: string;
  kind?: string;
  preset_id?: string | null;
  sound_used?: string;
  orders?: number;
  revenue_eur?: number;
  notes?: string;
  refresh_now?: boolean;
}

export interface UpdatePublishedVideoInput {
  productId: string;
  videoId: string;
  hook_text?: string;
  angle?: string;
  kind?: string;
  sound_used?: string;
  orders?: number;
  revenue_eur?: number;
  notes?: string;
}

const perfKeys = {
  list: (pid: string) => ["product", pid, "performance"] as const,
};

export function usePerformance(productId: string | null | undefined) {
  return useQuery<PerformanceListResponse>({
    queryKey: perfKeys.list(productId ?? ""),
    queryFn: () =>
      api.get<PerformanceListResponse>(
        `/api/v1/tiktok-shop/products/${productId}/performance`,
      ),
    enabled: Boolean(productId),
    staleTime: 30_000,
  });
}

export function useAddPublishedVideo() {
  const qc = useQueryClient();
  return useMutation<PublishedVideo, Error, AddPublishedVideoInput>({
    mutationFn: ({ productId, ...body }) =>
      api.post<PublishedVideo>(
        `/api/v1/tiktok-shop/products/${productId}/performance`,
        body,
      ),
    onSuccess: (_d, vars) =>
      qc.invalidateQueries({ queryKey: perfKeys.list(vars.productId) }),
  });
}

export function useRefreshPublishedVideo() {
  const qc = useQueryClient();
  return useMutation<
    PublishedVideo,
    Error,
    { productId: string; videoId: string }
  >({
    mutationFn: ({ productId, videoId }) =>
      api.post<PublishedVideo>(
        `/api/v1/tiktok-shop/products/${productId}/performance/${videoId}/refresh`,
        {},
      ),
    onSuccess: (_d, vars) =>
      qc.invalidateQueries({ queryKey: perfKeys.list(vars.productId) }),
  });
}

export function useUpdatePublishedVideo() {
  const qc = useQueryClient();
  return useMutation<PublishedVideo, Error, UpdatePublishedVideoInput>({
    mutationFn: ({ productId, videoId, ...body }) =>
      api.put<PublishedVideo>(
        `/api/v1/tiktok-shop/products/${productId}/performance/${videoId}`,
        body,
      ),
    onSuccess: (_d, vars) =>
      qc.invalidateQueries({ queryKey: perfKeys.list(vars.productId) }),
  });
}

export function useDeletePublishedVideo() {
  const qc = useQueryClient();
  return useMutation<void, Error, { productId: string; videoId: string }>({
    mutationFn: async ({ productId, videoId }) => {
      await api.del<void>(
        `/api/v1/tiktok-shop/products/${productId}/performance/${videoId}`,
      );
    },
    onSuccess: (_d, vars) =>
      qc.invalidateQueries({ queryKey: perfKeys.list(vars.productId) }),
  });
}
