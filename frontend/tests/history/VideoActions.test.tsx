import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { VideoActions } from "@/components/history/VideoActions";
import { mockFetch, renderWithProviders } from "../helpers";
import type { GenerationResponse } from "@/lib/types/generation";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

function makeGen(overrides: Partial<GenerationResponse> = {}): GenerationResponse {
  return {
    id: "gen_abc12345",
    user_id: "u1",
    product_id: "p1",
    tier_used: "standard",
    duration_seconds: 15,
    resolution: "720p",
    generation_status: "completed",
    cost: { total: 0.275, video_generation: 0.27, voice_tts: 0.005 },
    created_at: "2026-05-09T10:00:00+00:00",
    completed_at: "2026-05-09T10:05:00+00:00",
    drive_url: null,
    local_path: "/tmp/out.mp4",
    deleted: false,
    ...overrides,
  } as GenerationResponse;
}

describe("VideoActions", () => {
  it("regenerar idéntico dispara POST /generations/{id}/regenerate con overrides vacíos", async () => {
    fetchMock.on("POST", "/api/v1/generations/gen_abc12345/regenerate", () => ({
      job_id: "newjob01",
      estimated_cost: 0.275,
      estimated_duration_seconds: 15,
      position_in_queue: 0,
    }));

    renderWithProviders(<VideoActions generation={makeGen()} />);

    fireEvent.click(screen.getByRole("button", { name: /Regenerar idéntico/i }));

    await waitFor(() => {
      const post = fetchMock.calls.find((c) => c.method === "POST");
      expect(post).toBeDefined();
      expect(post?.url).toBe("/api/v1/generations/gen_abc12345/regenerate");
      expect(post?.body).toMatchObject({ overrides: {} });
    });
  });
});
