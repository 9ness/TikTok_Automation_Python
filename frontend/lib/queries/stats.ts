"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  BudgetStatusResponse,
  HistoricalStatsResponse,
  MonthlyStatsResponse,
} from "@/lib/types/stats";

export const statsKeys = {
  all: ["stats"] as const,
  monthly: (month?: string) => [...statsKeys.all, "monthly", month ?? "current"] as const,
  budget: () => [...statsKeys.all, "budget"] as const,
  historical: (months: number) => [...statsKeys.all, "historical", months] as const,
};

export function useMonthlyStats(month?: string) {
  return useQuery<MonthlyStatsResponse>({
    queryKey: statsKeys.monthly(month),
    queryFn: () => {
      const qs = month ? `?month=${month}` : "";
      return api.get<MonthlyStatsResponse>(`/api/v1/stats/monthly${qs}`);
    },
  });
}

export function useBudgetStatus() {
  return useQuery<BudgetStatusResponse>({
    queryKey: statsKeys.budget(),
    queryFn: () => api.get<BudgetStatusResponse>("/api/v1/stats/budget"),
  });
}

export function useHistoricalStats(months = 12) {
  return useQuery<HistoricalStatsResponse>({
    queryKey: statsKeys.historical(months),
    queryFn: () =>
      api.get<HistoricalStatsResponse>(`/api/v1/stats/historical?months=${months}`),
  });
}
