/**
 * Descubrimiento de productos (EchoTik) — qué se vende de verdad en ES.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface DiscoveredProduct {
  product_id: string;
  name: string;
  cover_url: string;
  tiktok_url: string;
  units_sold: number;
  units_sold_7d: number;
  units_sold_30d: number;
  gmv: number;
  gmv_30d: number;
  video_count: number;
  influencer_count: number;
  rating: number;
  review_count: number;
  min_price: number;
  max_price: number;
  commission_pct: number;
  category_id: string;
  region: string;
}

export interface DiscoveryResponse {
  configured: boolean;
  region: string;
  query: string;
  sort: string;
  items: DiscoveredProduct[];
  hint: string;
}

export interface DiscoveryParams {
  keyword: string;
  region?: string;
  sort?: string;
  minCommission?: number;
  maxPrice?: number;
  limit?: number;
  enabled?: boolean;
}

export function useDiscoverProducts(params: DiscoveryParams) {
  const {
    keyword,
    region = "ES",
    sort = "sales",
    minCommission = 0,
    maxPrice = 0,
    limit = 20,
    enabled,
  } = params;
  return useQuery<DiscoveryResponse>({
    queryKey: ["discovery", region, keyword, sort, minCommission, maxPrice, limit],
    queryFn: () => {
      const qs = new URLSearchParams({
        keyword,
        region,
        sort,
        limit: String(limit),
      });
      if (minCommission > 0) qs.set("min_commission", String(minCommission));
      if (maxPrice > 0) qs.set("max_price", String(maxPrice));
      return api.get<DiscoveryResponse>(
        `/api/v1/tiktok-shop/discovery/products?${qs.toString()}`,
      );
    },
    // Solo dispara cuando el user pulsa buscar (enabled controlado fuera).
    enabled: Boolean(enabled && keyword.trim()),
    staleTime: 5 * 60_000,
    retry: false,
  });
}
