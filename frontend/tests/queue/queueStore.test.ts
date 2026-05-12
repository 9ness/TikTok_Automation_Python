/**
 * Tests del store que recibe los eventos del WebSocket. Cubre el contrato
 * de los handlers que `useQueueWebSocket` invoca.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { selectActiveCount, useQueueStore } from "@/lib/stores/queueStore";
import type { ActiveJob } from "@/lib/types/queue";

function makeJob(overrides: Partial<ActiveJob> = {}): ActiveJob {
  return {
    job_id: "j1",
    mode: "tiktok_shop",
    title: "Job 1",
    status: "pending",
    progress_percent: 0,
    current_step: "",
    estimated_remaining_seconds: null,
    elapsed_seconds: 0,
    created_at: 1_000,
    started_at: null,
    finished_at: null,
    enqueued_by: null,
    error: null,
    ...overrides,
  };
}

beforeEach(() => useQueueStore.getState().reset());

describe("queueStore (contrato WS)", () => {
  it("setSnapshot reparte jobs entre active y recent según estado", () => {
    useQueueStore.getState().setSnapshot([
      makeJob({ job_id: "a", status: "pending" }),
      makeJob({ job_id: "b", status: "running" }),
      makeJob({ job_id: "c", status: "completed", finished_at: 2_000 }),
    ]);
    const state = useQueueStore.getState();
    expect(selectActiveCount(state)).toBe(2);
    expect(state.recent).toHaveLength(1);
    expect(state.recent[0]?.job_id).toBe("c");
  });

  it("upsertJobs mueve un job a recent cuando alcanza estado final", () => {
    const store = useQueueStore.getState();
    store.setSnapshot([makeJob({ job_id: "x", status: "running" })]);
    store.upsertJobs([
      makeJob({ job_id: "x", status: "completed", finished_at: 5_000 }),
    ]);
    const after = useQueueStore.getState();
    expect(after.active["x"]).toBeUndefined();
    expect(after.recent.find((j) => j.job_id === "x")).toBeDefined();
  });
});
