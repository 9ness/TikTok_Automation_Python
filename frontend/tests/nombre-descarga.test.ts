import { describe, expect, it } from "vitest";

import { PREFIJO_DESCARGA, nombreDescarga } from "@/lib/descargas";

describe("cómo se llama lo que se baja", () => {
  it("todo empieza igual, que es lo que los agrupa en el móvil", () => {
    expect(nombreDescarga("5 Agosto 2026", "3").startsWith(PREFIJO_DESCARGA)).toBe(true);
  });

  it("los espacios y los acentos no llegan al nombre del fichero", () => {
    const n = nombreDescarga("5 Agosto 2026", "3");
    expect(n).toBe("TTShopAIPro_5_Agosto_2026_3");
    expect(n).not.toMatch(/[^a-zA-Z0-9_.-]/);
  });

  it("las partes vacías no dejan guiones sueltos", () => {
    expect(nombreDescarga("carpeta", "", "7")).toBe("TTShopAIPro_carpeta_7");
  });

  it("acepta números, que es como llegan el orden y el índice", () => {
    expect(nombreDescarga("01", "carpeta", 2)).toBe("TTShopAIPro_01_carpeta_2");
  });

  it("no toca la extensión, que se pega fuera", () => {
    expect(`${nombreDescarga("a", "b")}.mp4`).toBe("TTShopAIPro_a_b.mp4");
  });

  it("una barra NO cuela una carpeta: el navegador la quitaría igual", () => {
    // Es la razón de que esto sea un prefijo y no una ruta: `download` es solo
    // el nombre del fichero.
    expect(nombreDescarga("videos/agosto", "3")).toBe("TTShopAIPro_videos_agosto_3");
  });
});
