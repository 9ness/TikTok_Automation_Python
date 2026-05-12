import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { BudgetCard } from "@/components/dashboard/BudgetCard";
import { mockFetch, renderWithProviders } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("BudgetCard", () => {
  it("muestra badge 'OK' cuando percent_used es bajo", async () => {
    fetchMock.on("GET", "/api/v1/stats/budget", () => ({
      current_month_cost: 5.0,
      monthly_budget_usd: 100.0,
      percent_used: 5.0,
      status: "ok",
      days_remaining_in_month: 20,
      projected_month_end_cost: 25.0,
    }));

    renderWithProviders(<BudgetCard />);
    await waitFor(() => expect(screen.getByText("OK")).toBeInTheDocument());
  });

  it("muestra el aviso 'Excedido en' cuando cost > budget", async () => {
    fetchMock.on("GET", "/api/v1/stats/budget", () => ({
      current_month_cost: 150.0,
      monthly_budget_usd: 100.0,
      percent_used: 150.0,
      status: "exceeded",
      days_remaining_in_month: 5,
      projected_month_end_cost: 180.0,
    }));

    renderWithProviders(<BudgetCard />);
    // El texto "Excedido en $X" solo aparece en estado exceeded — específico,
    // evita colisión con el badge "Excedido".
    await waitFor(() =>
      expect(screen.getByText(/Excedido en \$50\.00/)).toBeInTheDocument(),
    );
  });
});
