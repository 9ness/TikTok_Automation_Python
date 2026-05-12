import { beforeEach, describe, expect, it } from "vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";

import { useEnqueueSubsAuto } from "@/lib/queries/creator-reward/subsAuto";
import { makeQueryClient, mockFetch } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("useEnqueueSubsAuto", () => {
  it("hace POST con input_path + edited_text + style", async () => {
    fetchMock.on(
      "POST",
      "/api/v1/creator-reward/subs-auto/enqueue",
      () => ({ job_id: "sa12345", position_in_queue: 0 }),
    );

    const client = makeQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useEnqueueSubsAuto(), { wrapper });

    result.current.mutate({
      input_path: "api_uploads/subs/in.mp4",
      out_path: "out.mp4",
      edited_text: "hola mundo",
      model_size: "small",
      audio_type: "speech",
      quality_label: "720p (Medio)",
      style: {
        font_path: "Impact",
        highlight_mode: "pill",
        highlight_color: "#BB0808",
        text_color: "#FFFFFF",
        stroke_color: "#000000",
        stroke_width: 3,
        case_mode: "UPPERCASE",
        font_scale: 0.045,
        max_words: 3,
        y_position: 0.78,
        pill_enabled: true,
        max_width: 0.85,
        sync_offset: 0,
      },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const post = fetchMock.calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("/api/v1/creator-reward/subs-auto/enqueue");
    expect(post?.body).toMatchObject({
      input_path: "api_uploads/subs/in.mp4",
      edited_text: "hola mundo",
    });
  });
});
