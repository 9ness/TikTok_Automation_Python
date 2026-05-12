import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { JobCard } from "@/components/queue/JobCard";
import { renderWithProviders } from "../helpers";
import type { ActiveJob } from "@/lib/types/queue";

function makeJob(overrides: Partial<ActiveJob> = {}): ActiveJob {
  return {
    job_id: "abc12345",
    mode: "tiktok_shop",
    title: "Mi job",
    status: "running",
    progress_percent: 42,
    current_step: "Generando clip 2/3",
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

describe("JobCard", () => {
  it("muestra badge programa TikTok Shop y NO muestra badge submódulo", () => {
    renderWithProviders(<JobCard job={makeJob({ mode: "tiktok_shop" })} />);
    expect(screen.getByText(/TikTok Shop/i)).toBeInTheDocument();
    // El badge "Shop" del SUBMÓDULO no debe aparecer cuando el programa
    // ya es TikTok Shop (la jerarquía se redundaría).
    expect(screen.queryByText(/^Shop$/)).toBeNull();
    expect(screen.getByText(/42%/)).toBeInTheDocument();
  });

  it("muestra programa Creator Reward + badge submódulo Presidentes", () => {
    renderWithProviders(
      <JobCard
        job={makeJob({
          mode: "presidents",
          status: "pending",
          params: { topic: "worst", title_prefix: "The 5", top_count: 5 },
        })}
      />,
    );
    expect(screen.getByText(/Creator Reward/i)).toBeInTheDocument();
    expect(screen.getByText(/Presidentes/i)).toBeInTheDocument();
    // describeJobParams debe pintar topic + top_count
    expect(screen.getByText(/tema: worst/)).toBeInTheDocument();
    expect(screen.getByText(/top 5/)).toBeInTheDocument();
  });
});
