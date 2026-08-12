import { render, screen } from "@testing-library/react";
import { useEffect, useState } from "react";
import { describe, expect, it } from "vitest";

/** Reproduce el fallo: React reutiliza el componente si la `key` coincide, y
 *  `useState` solo mira su valor inicial la PRIMERA vez. */
function TarjetaVieja({ marcado }: { marcado: boolean }) {
  const [v] = useState(marcado);
  return <span data-testid="v">{v ? "marcado" : "sin marcar"}</span>;
}
function TarjetaNueva({ marcado }: { marcado: boolean }) {
  const [v, set] = useState(marcado);
  useEffect(() => set(marcado), [marcado]);
  return <span data-testid="v">{v ? "marcado" : "sin marcar"}</span>;
}

describe("tarjeta al cambiar de carpeta (mismo número de producto)", () => {
  it("ANTES: se quedaba marcada aunque el producto nuevo no lo esté", () => {
    const { rerender } = render(<TarjetaVieja key="1" marcado={true} />);
    rerender(<TarjetaVieja key="1" marcado={false} />);   // otra carpeta, producto 1
    expect(screen.getByTestId("v").textContent).toBe("marcado");   // el fallo
  });
  it("AHORA: refleja el producto de la carpeta abierta", () => {
    const { rerender } = render(<TarjetaNueva key="1" marcado={true} />);
    rerender(<TarjetaNueva key="1" marcado={false} />);
    expect(screen.getByTestId("v").textContent).toBe("sin marcar");
  });
});
