import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { QueueBadge } from "@/components/queue/QueueBadge";
import { useQueueStore } from "@/lib/stores/queueStore";
import type { ActiveJob } from "@/lib/types/queue";

function makeJob(overrides: Partial<ActiveJob> = {}): ActiveJob {
  return {
    job_id: "j1",
    mode: "tiktok_shop",
    title: "x",
    status: "running",
    progress_percent: 0,
    current_step: "",
    estimated_remaining_seconds: null,
    elapsed_seconds: 0,
    created_at: 1,
    started_at: null,
    finished_at: null,
    enqueued_by: null,
    error: null,
    ...overrides,
  };
}

beforeEach(() => useQueueStore.getState().reset());

describe("QueueBadge", () => {
  it("actualiza el contador cuando cambia el store", () => {
    useQueueStore.getState().setConnection("connected");
    const { rerender } = render(<QueueBadge />);
    // Inicialmente sin jobs → no debe haber badge numérico visible
    expect(screen.queryByText("3")).toBeNull();

    useQueueStore.getState().setSnapshot([
      makeJob({ job_id: "a" }),
      makeJob({ job_id: "b" }),
      makeJob({ job_id: "c" }),
    ]);
    rerender(<QueueBadge />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
