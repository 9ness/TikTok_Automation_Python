import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RehacerDialog } from "@/components/tiktok-shop-ai-pro/RehacerDialog";

describe("RehacerDialog", () => {
  it("los motivos rápidos se suman a la nota y se marca con ella", async () => {
    const onMarcar = vi.fn();
    const onCerrar = vi.fn();
    render(
      <RehacerDialog abierto titulo="6 · Caja Shorkey" onCerrar={onCerrar} onMarcar={onMarcar} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Otro objeto parecido al lado" }));
    await userEvent.type(screen.getByLabelText(/Nota/), ". Ponlo en un cuarto infantil");
    await userEvent.click(screen.getByRole("button", { name: /Marcar para rehacer/ }));
    expect(onMarcar).toHaveBeenCalledWith("Otro objeto parecido al lado. Ponlo en un cuarto infantil");
    expect(onCerrar).toHaveBeenCalled();
  });

  it("cancelar no marca nada", async () => {
    const onMarcar = vi.fn();
    const onCerrar = vi.fn();
    render(<RehacerDialog abierto titulo="x" onCerrar={onCerrar} onMarcar={onMarcar} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onMarcar).not.toHaveBeenCalled();
    expect(onCerrar).toHaveBeenCalled();
  });
});
