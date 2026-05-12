import { beforeEach, describe, expect, it } from "vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

import { useCancelJob } from "@/lib/queries/queue";
import { makeQueryClient, mockFetch } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("useCancelJob", () => {
  it("hace DELETE /api/v1/queue/{jobId}", async () => {
    fetchMock.on(
      "DELETE",
      "/api/v1/queue/abc12345",
      () => new Response(null, { status: 204 }),
    );

    const client = makeQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useCancelJob(), { wrapper });
    result.current.mutate("abc12345");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const del = fetchMock.calls.find((c) => c.method === "DELETE");
    expect(del?.url).toBe("/api/v1/queue/abc12345");
  });
});
