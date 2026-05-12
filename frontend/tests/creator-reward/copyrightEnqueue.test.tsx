import { beforeEach, describe, expect, it } from "vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

import { useEnqueueCopyright } from "@/lib/queries/creator-reward/copyright";
import { makeQueryClient, mockFetch } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("useEnqueueCopyright", () => {
  it("hace POST multipart con el vídeo + clean_mode + hook params", async () => {
    fetchMock.on(
      "POST",
      "/api/v1/creator-reward/copyright/enqueue",
      () => ({
        job_id: "cpy12345",
        title: "test.mp4",
        position_in_queue: 0,
        input_path_relative: "api_uploads/copyright/test.mp4",
      }),
    );

    const client = makeQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useEnqueueCopyright(), { wrapper });

    const file = new File(["dummy"], "test.mp4", { type: "video/mp4" });
    result.current.mutate({
      file,
      clean_mode: "Subtítulos Virales",
      hook_y_pct: 0.20,
      hook_color: "#FDD002",
      upscale_1080p: false,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const post = fetchMock.calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("/api/v1/creator-reward/copyright/enqueue");
    const body = post?.body as Record<string, unknown>;
    expect(body.clean_mode).toBe("Subtítulos Virales");
    expect(body.hook_y_pct).toBe("0.2");
    expect(body.hook_color).toBe("#FDD002");
  });
});
