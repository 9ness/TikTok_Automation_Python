import { beforeEach, describe, expect, it } from "vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

import { useDashboardSummary } from "@/lib/queries/dashboard";
import { makeQueryClient, mockFetch } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("useDashboardSummary", () => {
  it("hace GET /api/v1/dashboard/summary y devuelve los datos", async () => {
    fetchMock.on("GET", "/api/v1/dashboard/summary", () => ({
      total_users: 3,
      total_products: 5,
      total_videos_this_month: 12,
      total_cost_this_month: 4.5,
      active_jobs_count: 1,
      pending_jobs_count: 1,
      running_jobs_count: 0,
      recent_videos: [],
      pilot_users_summary: [],
      alerts: [],
    }));

    const client = makeQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useDashboardSummary(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_users).toBe(3);
    expect(result.current.data?.total_videos_this_month).toBe(12);
  });
});
