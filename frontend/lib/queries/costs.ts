"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface CostLine {
  kind: string;
  units: number;
  unit_label: string;
  cost_usd: number;
  detail: string | null;
}

export interface JobCost {
  job_id: string;
  program: string;
  mode: string;
  user: string | null;
  product_id: string | null;
  title: string | null;
  started_at: number;
  finished_at: number | null;
  lines: CostLine[];
  total_usd: number;
}

export interface CostSummary {
  total_usd: number;
  count: number;
  by_program: Record<string, number>;
  by_mode: Record<string, number>;
  by_user: Record<string, number>;
  by_kind: Record<string, number>;
}

export interface JobsWithCostsResponse {
  month: string;
  filters: {
    program: string | null;
    mode: string | null;
    user: string | null;
    product_id: string | null;
  };
  summary: CostSummary;
  jobs: JobCost[];
}

export interface CostsQueryFilters {
  month?: string;
  program?: string;
  mode?: string;
  user?: string;
  product_id?: string;
  limit?: number;
}

export function useJobsWithCosts(filters: CostsQueryFilters = {}) {
  const params = new URLSearchParams();
  if (filters.month) params.set("month", filters.month);
  if (filters.program) params.set("program", filters.program);
  if (filters.mode) params.set("mode", filters.mode);
  if (filters.user) params.set("user", filters.user);
  if (filters.product_id) params.set("product_id", filters.product_id);
  if (filters.limit) params.set("limit", String(filters.limit));
  const qs = params.toString();

  return useQuery<JobsWithCostsResponse>({
    queryKey: ["stats", "jobs", filters],
    queryFn: () => api.get(`/api/v1/stats/jobs${qs ? `?${qs}` : ""}`),
    staleTime: 30_000,
  });
}
