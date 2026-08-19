import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";

import {
  fijarUsuario,
  hidratar,
  olvidar,
  ultimoUsuario,
  vigilar,
} from "@/lib/cache-persistente";

/** Dónde guarda sus cosas una persona. */
function clave(usuario: string, key: unknown[]): string {
  return `qcache:u:${usuario}:${JSON.stringify(key)}`;
}

/** Deja la caché guardada como si la app acabara de morir: se apunta lo que
 *  llega y luego se arranca un cliente nuevo desde cero. */
async function sesionQueGuarda(key: unknown[], data: unknown, usuario = "ness") {
  const qc = new QueryClient();
  const parar = vigilar(qc, usuario);
  qc.setQueryData(key, data);
  // El `subscribe` de React Query notifica en microtask.
  await Promise.resolve();
  parar();
  qc.clear();
}

describe("caché que sobrevive a que Android mate la app", () => {
  beforeEach(() => localStorage.clear());

  it("al reabrir, la pantalla sale con lo último que se vio", async () => {
    const key = ["nicho-pov-bof", "productos", "aleatorios_2", "5 Agosto 2026"];
    await sesionQueGuarda(key, [{ producto: "8", titulo: "Tabla paddle surf" }]);

    const nuevo = new QueryClient();
    expect(nuevo.getQueryData(key)).toBeUndefined();
    hidratar(nuevo, "ness");
    expect(nuevo.getQueryData(key)).toEqual([
      { producto: "8", titulo: "Tabla paddle surf" },
    ]);
  });

  it("no guarda lo que no es un listado de nicho (cola, sesión…)", async () => {
    await sesionQueGuarda(["queue", "jobs"], [{ id: "1" }]);
    await sesionQueGuarda(["auth", "me"], { username: "ness" });
    expect(Object.keys(localStorage).filter((k) => k.startsWith("qcache:"))).toHaveLength(0);
  });

  it("descarta lo viejo en vez de enseñar datos de ayer", () => {
    const key = ["nicho-gorras", "gorras", "1"];
    const haceSieteHoras = Date.now() - 7 * 60 * 60 * 1000;
    localStorage.setItem(
      clave("ness", key),
      JSON.stringify({ key, data: [{ producto: "1" }], ts: haceSieteHoras }),
    );
    const qc = new QueryClient();
    hidratar(qc, "ness");
    expect(qc.getQueryData(key)).toBeUndefined();
    expect(localStorage.getItem(clave("ness", key))).toBeNull();
  });

  it("lo que ya está cargado manda sobre lo guardado", async () => {
    const key = ["pov-bof-largo", "productos", "aleatorios_2", "5 Agosto 2026"];
    await sesionQueGuarda(key, { items: [{ producto: "viejo" }] });

    const qc = new QueryClient();
    qc.setQueryData(key, { items: [{ producto: "recien pedido" }] });
    hidratar(qc, "ness");
    expect(qc.getQueryData(key)).toEqual({ items: [{ producto: "recien pedido" }] });
  });

  it("no llena el localStorage con respuestas gordas", async () => {
    const key = ["nicho-ropa", "prendas", "camisetas"];
    await sesionQueGuarda(key, { relleno: "x".repeat(200_000) });
    expect(localStorage.getItem(clave("ness", key))).toBeNull();
  });
  it("lo rehidratado se da por VIEJO, para que se refresque solo", async () => {
    const key = ["nicho-pov-bof", "vendidos", ""];
    await sesionQueGuarda(key, [{ producto: "2", unidades: 4 }]);

    const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
    hidratar(qc, "ness");
    const estado = qc.getQueryState(key)!;
    // Si se marcara como recién traído, React Query no volvería a pedirlo y te
    // comerías el dato guardado aunque estuviera mal.
    expect(Date.now() - estado.dataUpdatedAt).toBeGreaterThanOrEqual(0);
    expect(qc.getQueryCache().find({ queryKey: key })!.isStaleByTime(60_000)).toBe(false);
  });

  it("no guarda listas vacías: se confundirían con 'aún no ha cargado'", async () => {
    await sesionQueGuarda(["nicho-pov-bof", "vendidos", ""], []);
    await sesionQueGuarda(["pov-bof-largo", "productos", "a", "b"], { items: [] });
    expect(Object.keys(localStorage).filter((k) => k.startsWith("qcache:"))).toHaveLength(0);
  });

  // El progreso guardado (carpetas hechas, subidos, escaparate, vendidos) es
  // de UNA persona. Al entrar el admin en la cuenta de Ana, la pantalla salía
  // con el suyo hasta que respondía el Drive — segundos enseñando lo de otro.
  describe("cada persona con lo suyo", () => {
    const key = ["pov-bof-largo", "folders", "aleatorios_2"];

    it("no le pinta a Ana el progreso de ness", async () => {
      await sesionQueGuarda(key, { completed_count: 6 }, "ness");

      const deAna = new QueryClient();
      hidratar(deAna, "ana");
      expect(deAna.getQueryData(key)).toBeUndefined();
    });

    it("y a ness le sigue saliendo el suyo al instante", async () => {
      await sesionQueGuarda(key, { completed_count: 6 }, "ness");
      await sesionQueGuarda(key, { completed_count: 0 }, "ana");

      const deNess = new QueryClient();
      hidratar(deNess, "ness");
      expect(deNess.getQueryData(key)).toEqual({ completed_count: 6 });

      // Y volver a la otra cuenta tampoco cuesta una espera: su cajón sigue
      // ahí, no se tiró al cambiar.
      const otraVezAna = new QueryClient();
      hidratar(otraVezAna, "ana");
      expect(otraVezAna.getQueryData(key)).toEqual({ completed_count: 0 });
    });

    it("apunta quién entró el último, que es lo que evita la espera", () => {
      expect(ultimoUsuario()).toBe("");
      fijarUsuario("ana");
      expect(ultimoUsuario()).toBe("ana");
      // Al salir se olvida, para que el siguiente no herede pintura ajena.
      fijarUsuario("");
      expect(ultimoUsuario()).toBe("");
    });

    it("olvidar sin nombre lo tira todo; con nombre, solo ese cajón", async () => {
      await sesionQueGuarda(key, { completed_count: 6 }, "ness");
      await sesionQueGuarda(key, { completed_count: 0 }, "ana");

      olvidar("ana");
      expect(localStorage.getItem(clave("ana", key))).toBeNull();
      expect(localStorage.getItem(clave("ness", key))).not.toBeNull();

      olvidar();
      expect(Object.keys(localStorage).filter((k) => k.startsWith("qcache:"))).toHaveLength(0);
    });
  });
});
