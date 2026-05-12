import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { CostByModuleChart } from "@/components/dashboard/CostByModuleChart";

describe("CostByModuleChart", () => {
  it("renderiza el gráfico cuando hay datos", () => {
    render(<CostByModuleChart data={{ tiktok_shop: 4.5, creator_reward: 0 }} />);
    // El gráfico se monta dentro del wrapper con data-testid
    expect(screen.getByTestId("cost-by-module-chart")).toBeInTheDocument();
  });

  it("muestra empty state cuando no hay coste", () => {
    render(<CostByModuleChart data={{}} />);
    expect(screen.getByText(/Sin coste registrado/i)).toBeInTheDocument();
  });
});
