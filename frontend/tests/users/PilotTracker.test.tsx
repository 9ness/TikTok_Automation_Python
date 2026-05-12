import { describe, expect, it, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { PilotTracker } from "@/components/users/PilotTracker";
import { makePilotProgress, mockFetch, renderWithProviders } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("PilotTracker", () => {
  it("muestra los counters y las 3 vías de graduación con missing reasons", async () => {
    const progress = makePilotProgress({
      days_in_program: 10,
      followers: 1200,
      current_chr: 200,
      orders_count: 0,
      weekly_shoppable_used: 1,
    });
    fetchMock.on(
      "GET",
      "/api/v1/users/%40test_user/pilot-progress",
      () => progress,
    );

    renderWithProviders(<PilotTracker username="@test_user" />);

    await waitFor(() => screen.getByText(/Vías de graduación/i));

    // Counters — `toLocaleString()` puede rendir sin separador de miles en jsdom
    expect(screen.getByText(/^1,?200$/)).toBeInTheDocument(); // followers
    expect(screen.getByText("200")).toBeInTheDocument(); // CHR
    expect(screen.getByText("10")).toBeInTheDocument(); // días

    // Las 3 vías están renderizadas
    expect(screen.getByText(/Vía A/i)).toBeInTheDocument();
    expect(screen.getByText(/Vía B/i)).toBeInTheDocument();
    expect(screen.getByText(/Vía C/i)).toBeInTheDocument();

    // Missing reasons visibles
    expect(screen.getByText(/3800 followers más/i)).toBeInTheDocument();
    expect(screen.getByText(/Quiz pendiente/i)).toBeInTheDocument();
  });

  it("muestra label 'Graduado' cuando graduation_status=graduated", async () => {
    const progress = makePilotProgress({
      status: "graduated",
      graduation_status: "graduated",
      days_until_eligible: 0,
    });
    fetchMock.on(
      "GET",
      "/api/v1/users/%40test_user/pilot-progress",
      () => progress,
    );

    renderWithProviders(<PilotTracker username="@test_user" />);
    await waitFor(() => expect(screen.getByText(/Graduado/i)).toBeInTheDocument());
  });
});
