import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { QueueDrawer } from "@/components/queue/QueueDrawer";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import { useQueueStore } from "@/lib/stores/queueStore";
import { renderWithProviders } from "../helpers";
import type { ActiveJob } from "@/lib/types/queue";

function makeJob(overrides: Partial<ActiveJob> = {}): ActiveJob {
  return {
    job_id: "j1",
    mode: "tiktok_shop",
    title: "Test job",
    status: "running",
    progress_percent: 50,
    current_step: "…",
    estimated_remaining_seconds: 30,
    elapsed_seconds: 30,
    created_at: 1,
    started_at: 2,
    finished_at: null,
    enqueued_by: null,
    error: null,
    ...overrides,
  };
}

beforeEach(() => {
  useQueueStore.getState().reset();
  useDrawerStore.setState({ queueOpen: true });
});

describe("QueueDrawer", () => {
  it("filtra por programa al hacer click en 'Creator Reward'", () => {
    useQueueStore.getState().setSnapshot([
      makeJob({ job_id: "ts", mode: "tiktok_shop", title: "Shop job" }),
      makeJob({ job_id: "pres", mode: "presidents", title: "Pres job" }),
    ]);
    useQueueStore.getState().setConnection("connected");

    renderWithProviders(<QueueDrawer />);

    // Pre-filtro: ambos visibles
    expect(screen.getByText("Shop job")).toBeInTheDocument();
    expect(screen.getByText("Pres job")).toBeInTheDocument();

    // Click en filtro Creator Reward
    fireEvent.click(screen.getByRole("button", { name: /Creator Reward/ }));

    // Solo CR debe estar
    expect(screen.queryByText("Shop job")).toBeNull();
    expect(screen.getByText("Pres job")).toBeInTheDocument();

    // Sub-filtros aparecen al filtrar por CR
    expect(screen.getByRole("button", { name: /Presidentes/ })).toBeInTheDocument();
  });
});
