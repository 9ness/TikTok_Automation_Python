import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import { useEnqueueGeneration } from "@/lib/queries/generations";
import { makeQueryClient, mockFetch } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("useEnqueueGeneration", () => {
  it("dispara POST /generations/enqueue con el payload del wizard", async () => {
    fetchMock.on("POST", "/api/v1/generations/enqueue", () => ({
      job_id: "abc12345",
      estimated_cost: 0.27,
      estimated_duration_seconds: 15,
      position_in_queue: 0,
    }));

    const client = makeQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useEnqueueGeneration(), { wrapper });

    result.current.mutate({
      username: "@user",
      product_id: "p1",
      tier: "standard",
      duration_seconds: 15,
      resolution: "720p",
      strategy: "dynamic",
      voice_enabled: true,
      voice_id: "Spanish_EnergeticBoy",
      hook_category: "curiosity",
      target_audience: "Gymbros",
      shoppable: false,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const post = fetchMock.calls.find((c) => c.method === "POST");
    expect(post).toBeDefined();
    expect(post?.url).toBe("/api/v1/generations/enqueue");
    expect(post?.body).toMatchObject({
      username: "@user",
      product_id: "p1",
      tier: "standard",
      voice_enabled: true,
      voice_id: "Spanish_EnergeticBoy",
    });
    expect(result.current.data?.job_id).toBe("abc12345");
  });
});
