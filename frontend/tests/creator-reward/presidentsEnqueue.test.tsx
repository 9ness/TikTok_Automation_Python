import { beforeEach, describe, expect, it } from "vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

import { useEnqueuePresidents } from "@/lib/queries/creator-reward/presidents";
import { makeQueryClient, mockFetch } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("useEnqueuePresidents", () => {
  it("hace POST con items + subs + hook", async () => {
    fetchMock.on(
      "POST",
      "/api/v1/creator-reward/presidents/enqueue",
      () => ({ jobs: [{ job_id: "j1", position_in_queue: 0, title: "x" }], total_enqueued: 1 }),
    );
    const client = makeQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useEnqueuePresidents(), { wrapper });

    result.current.mutate({
      items: [{ topic: "worst", prefix: "The", top_count: 5, include_history: true, include_hook: true, numbers_variant: false }],
      creative_mode: false,
      engine_version: "v2_estable",
      resolution: "1080p (Lento)",
      subs: {
        enabled: false,
        font_choice: "Impact",
        highlight_color: "#fff",
        text_color: "#000",
        stroke_color: "#000",
        stroke_width: 3,
        case_mode: "UPPERCASE",
        font_scale: 0.04,
        max_words: 4,
        y_position: 0.62,
        shadow_enabled: false,
        shadow_color: "#000000",
        shadow_opacity: 0.8,
        shadow_blur: 33,
        shadow_distance: 8,
        shadow_angle: -45,
        highlight_mode: "pill",
        max_width: 0.85,
      },
      hook: {
        enabled: false,
        duration: 5,
        animation: "swipe_left",
        y_position: 0.33,
        shadow_color: "#000",
        box_color: "#fff",
        text_color: "#000",
        font_scale: 0.02,
      },
      numbers: {
        font_choice: "Impact",
        mystery_text: "???",
        header_text: "",
        header_mode: "all",
        header_duration: 5,
        header_animation: "none",
        header_y_position: 0.07,
        header_font_scale: 0.024,
        header_text_color: "#0B0B0B",
        header_box_color: "#FFFFFF",
        header_shadow_color: "#1E01C4",
        list_x_position: 0.07,
        list_y_position: 0.32,
        list_line_spacing: 0.105,
        number_font_scale: 0.044,
        name_font_scale: 0.036,
        number_color: "#FFFFFF",
        number_medal_colors: true,
        number_color_gold: "#FFD700",
        number_color_silver: "#C0C0C0",
        number_color_bronze: "#CD7F32",
        name_color: "#FFFFFF",
        name_stroke_color: "#000000",
        name_stroke_width: 3,
      },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const post = fetchMock.calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("/api/v1/creator-reward/presidents/enqueue");
    expect((post?.body as Record<string, unknown>).items).toHaveLength(1);
  });
});
