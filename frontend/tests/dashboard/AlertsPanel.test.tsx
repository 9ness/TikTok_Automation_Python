import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { AlertsPanel } from "@/components/dashboard/AlertsPanel";
import type { Alert } from "@/lib/types/dashboard";

describe("AlertsPanel", () => {
  it("muestra todas las alertas con su severidad", () => {
    const alerts: Alert[] = [
      {
        severity: "error",
        code: "budget_exceeded",
        message: "Presupuesto excedido: $150 / $100.",
      },
      {
        severity: "warning",
        code: "budget_warning",
        message: "85% del presupuesto.",
      },
      {
        severity: "info",
        code: "pilot_freeze",
        message: "2 cuentas en límite semanal.",
      },
    ];

    render(<AlertsPanel alerts={alerts} />);

    expect(screen.getByText(/Alertas \(3\)/)).toBeInTheDocument();
    expect(screen.getByText(/Presupuesto excedido/)).toBeInTheDocument();
    expect(screen.getByText(/85%/)).toBeInTheDocument();
    expect(screen.getByText(/2 cuentas/)).toBeInTheDocument();
  });

  it("no renderiza nada cuando no hay alertas", () => {
    const { container } = render(<AlertsPanel alerts={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
