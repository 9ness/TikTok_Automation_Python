import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useEstadoDeUsuario,
  useEstadoRecordado,
} from "@/lib/hooks/useEstadoRecordado";

// `useEstadoDeUsuario` saca el usuario de `/me`; aquí se decide a mano quién
// mira, que es lo que se está probando.
const quienMira = vi.hoisted(() => ({ username: "ness" as string | undefined }));
vi.mock("@/lib/queries/auth", () => ({
  useMe: () => ({ data: { username: quienMira.username } }),
}));

describe("por dónde iba cada uno", () => {
  beforeEach(() => {
    localStorage.clear();
    quienMira.username = "ness";
  });

  it("la carpeta abierta se guarda debajo del usuario", async () => {
    const { result } = renderHook(() =>
      useEstadoDeUsuario<string | null>("povbof-largo:carpeta", null),
    );
    act(() => result.current[1]("2 Pront Flow"));
    await waitFor(() =>
      expect(localStorage.getItem("u:ness:povbof-largo:carpeta")).toBe(
        JSON.stringify("2 Pront Flow"),
      ),
    );
  });

  it("Ana no aterriza en la carpeta que estaba mirando ness", async () => {
    localStorage.setItem("u:ness:povbof-largo:carpeta", JSON.stringify("2 Pront Flow"));

    quienMira.username = "ana";
    const { result } = renderHook(() =>
      useEstadoDeUsuario<string | null>("povbof-largo:carpeta", null),
    );
    // `null` = "ninguna elegida", que es lo que hace caer en la primera carpeta
    // pendiente DE ELLA (`data.current`, que ya viene por usuario del backend).
    await waitFor(() => expect(result.current[0]).toBeNull());
    expect(localStorage.getItem("u:ness:povbof-largo:carpeta")).not.toBeNull();
  });

  it("y al volver a la cuenta propia, sigue donde estaba", async () => {
    localStorage.setItem("u:ness:povbof-largo:carpeta", JSON.stringify("2 Pront Flow"));
    const { result } = renderHook(() =>
      useEstadoDeUsuario<string | null>("povbof-largo:carpeta", null),
    );
    await waitFor(() => expect(result.current[0]).toBe("2 Pront Flow"));
  });

  // Es el detalle que hace que lo de arriba funcione: al cambiar la clave hay
  // que VOLVER al valor por defecto, no quedarse con lo de la clave anterior.
  it("cambiar de clave sin nada guardado vuelve al valor por defecto", async () => {
    const { result, rerender } = renderHook(
      ({ clave }: { clave: string }) => useEstadoRecordado(clave, "camisetas"),
      { initialProps: { clave: "u:ness:ropa:carpeta" } },
    );
    act(() => result.current[1]("pantalones"));
    await waitFor(() => expect(result.current[0]).toBe("pantalones"));

    rerender({ clave: "u:ana:ropa:carpeta" });
    await waitFor(() => expect(result.current[0]).toBe("camisetas"));
    // Y lo de ness sigue intacto para cuando vuelva.
    expect(localStorage.getItem("u:ness:ropa:carpeta")).toBe(
      JSON.stringify("pantalones"),
    );
  });
});

describe("un móvil que ya tuvo otra sesión", () => {
  beforeEach(() => {
    localStorage.clear();
    quienMira.username = "ness";
  });

  it("mientras no se sepa quién entró, no se lee nada de nadie", async () => {
    // Así queda un móvil que configuró otra persona: su rastro sigue ahí.
    localStorage.setItem("qcache:ultimo", "ness");
    localStorage.setItem(
      "u:ness:povbof-largo:carpeta",
      JSON.stringify("2 Pront Flow"),
    );

    quienMira.username = undefined; // `/me` todavía no ha contestado
    const { result } = renderHook(() =>
      useEstadoDeUsuario<string | null>("povbof-largo:carpeta", null),
    );

    // Nada de la persona anterior. Antes salía su carpeta durante ese instante
    // y, si se tocaba algo, se guardaba bajo la clave de ÉL.
    await waitFor(() => expect(result.current[0]).toBeNull());
  });

  it("ni se guarda nada bajo la clave del anterior", async () => {
    localStorage.setItem("qcache:ultimo", "ness");
    quienMira.username = undefined;
    const { result } = renderHook(() =>
      useEstadoDeUsuario<string | null>("povbof-largo:carpeta", null),
    );
    act(() => result.current[1]("8 Agosto 2026"));
    await waitFor(() => expect(result.current[0]).toBe("8 Agosto 2026"));
    expect(localStorage.getItem("u:ness:povbof-largo:carpeta")).toBeNull();
  });
});
