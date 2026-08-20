import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MontadoEl } from "@/components/tiktok-shop-ai-pro/MontadoEl";

/** El reloj se fija: si no, "hoy" y "ayer" dependen de cuándo se ejecute. */
function conFechaFija(iso: string, fn: () => void) {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(iso));
  try {
    fn();
  } finally {
    vi.useRealTimers();
  }
}

const seg = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);

describe("cuándo se montó el vídeo", () => {
  afterEach(() => vi.useRealTimers());

  it("lo de hoy se dice como hoy, con su hora", () => {
    conFechaFija("2026-08-20T23:50:00", () => {
      render(<MontadoEl ts={seg("2026-08-20T23:40:00")} />);
      expect(screen.getByText(/Montado hoy/)).toBeInTheDocument();
    });
  });

  it("lo de ayer se dice como ayer, no con la fecha", () => {
    conFechaFija("2026-08-20T09:00:00", () => {
      render(<MontadoEl ts={seg("2026-08-19T23:40:00")} />);
      expect(screen.getByText(/Montado ayer/)).toBeInTheDocument();
    });
  });

  it("lo de hace días lleva la fecha, que es lo que se busca", () => {
    conFechaFija("2026-08-20T09:00:00", () => {
      render(<MontadoEl ts={seg("2026-08-15T18:20:00")} />);
      expect(screen.getByText(/15 ago/)).toBeInTheDocument();
    });
  });

  it("lo que no es de hoy se pinta en ámbar: es la señal de 'esto no es de ahora'", () => {
    conFechaFija("2026-08-20T09:00:00", () => {
      const { container } = render(<MontadoEl ts={seg("2026-08-15T18:20:00")} />);
      expect(container.querySelector("p")?.className).toContain("amber");
    });
    conFechaFija("2026-08-20T09:00:00", () => {
      const { container } = render(<MontadoEl ts={seg("2026-08-20T08:00:00")} />);
      expect(container.querySelector("p")?.className).not.toContain("amber");
    });
  });

  it("sin fecha no pinta nada, en vez de una fecha inventada", () => {
    const { container } = render(<MontadoEl ts={0} />);
    expect(container).toBeEmptyDOMElement();
    const vacio = render(<MontadoEl ts={undefined} />);
    expect(vacio.container).toBeEmptyDOMElement();
  });
});
