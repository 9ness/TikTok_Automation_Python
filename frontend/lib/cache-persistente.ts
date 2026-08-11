"use client";

import type { QueryClient } from "@tanstack/react-query";

/** Guarda en `localStorage` lo último que se cargó, para que al reabrir la app
 *  la pantalla salga PINTADA en vez de en blanco.
 *
 *  Android mata la app al poco de dejarla de fondo y eso no se puede evitar
 *  desde la web (ver `ChivatoCierres`). Al volver, la caché de React Query
 *  arranca vacía y hay que esperar otra vez al listado del Drive, que es lo
 *  lento. Con esto la pantalla aparece al momento con lo último que se vio y
 *  React Query refresca por detrás — que es justo lo que ya hace al montar,
 *  porque el `staleTime` es corto.
 *
 *  Reglas para que esto no se vuelva en contra:
 *  - Solo listados de los nichos (`PREFIJOS`). Nada de la cola ni de auth.
 *  - Se descarta lo de hace más de `FRESCURA_MS`: mejor esperar que enseñar
 *    algo de ayer.
 *  - Se ignoran las respuestas gordas (`MAX_BYTES`): `localStorage` tiene ~5 MB
 *    y llenarlo rompería también el resto (progreso de carpeta, sesión…).
 */
const PREFIJO = "qcache:";
const FRESCURA_MS = 6 * 60 * 60 * 1000;
const MAX_BYTES = 150_000;
const MAX_ENTRADAS = 40;

/** Qué se guarda. Son los listados caros de recargar (Drive + Gemini). */
const PREFIJOS = [
  "nicho-pov-bof",
  "pov-bof-largo",
  "nicho-bof-cine",
  "nicho-gorras",
  "nicho-ropa",
  "nicho-ropa-personas",
  "nicho-creativos",
  "cuenta-piloto",
];

function interesa(key: readonly unknown[]): boolean {
  return typeof key[0] === "string" && PREFIJOS.includes(key[0]);
}

function claveDe(key: readonly unknown[]): string {
  return PREFIJO + JSON.stringify(key);
}

/** Vuelca lo guardado a la caché. Se llama UNA vez, antes del primer render de
 *  las pantallas, para que la primera pintura ya lleve datos. */
export function hidratar(qc: QueryClient): void {
  let entradas: { clave: string; ts: number }[] = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const clave = localStorage.key(i);
      if (clave?.startsWith(PREFIJO)) entradas.push({ clave, ts: 0 });
    }
  } catch {
    return;
  }
  for (const { clave } of entradas) {
    try {
      const crudo = localStorage.getItem(clave);
      if (!crudo) continue;
      const { key, data, ts } = JSON.parse(crudo) as {
        key: unknown[];
        data: unknown;
        ts: number;
      };
      if (!key || Date.now() - ts > FRESCURA_MS) {
        localStorage.removeItem(clave);
        continue;
      }
      // Solo si no hay nada ya: lo recién pedido siempre manda sobre esto.
      if (qc.getQueryData(key) === undefined) qc.setQueryData(key, data);
    } catch {
      try {
        localStorage.removeItem(clave);
      } catch {
        /* nada que hacer */
      }
    }
  }
}

/** Empieza a guardar cada listado que llega. Devuelve cómo dejar de hacerlo. */
export function vigilar(qc: QueryClient): () => void {
  return qc.getQueryCache().subscribe((evento) => {
    const query = evento.query;
    if (!query || query.state.status !== "success") return;
    const key = query.queryKey as readonly unknown[];
    if (!interesa(key)) return;
    try {
      const cuerpo = JSON.stringify({
        key,
        data: query.state.data,
        ts: Date.now(),
      });
      if (cuerpo.length > MAX_BYTES) return;
      localStorage.setItem(claveDe(key), cuerpo);
      podar();
    } catch {
      // Cuota llena: se tira lo viejo y se deja estar. No merece más.
      podar(true);
    }
  });
}

/** Deja como mucho `MAX_ENTRADAS`, tirando las más viejas. */
function podar(agresivo = false): void {
  try {
    const entradas: { clave: string; ts: number }[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const clave = localStorage.key(i);
      if (!clave?.startsWith(PREFIJO)) continue;
      let ts = 0;
      try {
        ts = (JSON.parse(localStorage.getItem(clave) || "{}") as { ts?: number }).ts ?? 0;
      } catch {
        /* si no se puede leer, que sea la primera en caer */
      }
      entradas.push({ clave, ts });
    }
    const tope = agresivo ? Math.floor(MAX_ENTRADAS / 2) : MAX_ENTRADAS;
    if (entradas.length <= tope) return;
    entradas.sort((a, b) => a.ts - b.ts);
    for (const { clave } of entradas.slice(0, entradas.length - tope)) {
      localStorage.removeItem(clave);
    }
  } catch {
    /* idem */
  }
}
