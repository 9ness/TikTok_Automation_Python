"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { DashboardSummaryResponse } from "@/lib/types/dashboard";

export const dashboardKeys = {
  all: ["dashboard"] as const,
  summary: () => [...dashboardKeys.all, "summary"] as const,
};

export function useDashboardSummary() {
  return useQuery<DashboardSummaryResponse>({
    queryKey: dashboardKeys.summary(),
    queryFn: () => api.get<DashboardSummaryResponse>("/api/v1/dashboard/summary"),
    staleTime: 60 * 1000,
  });
}
