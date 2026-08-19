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
 *  - Cada persona tiene su cajón (`qcache:u:<usuario>:…`). Lo que se guarda
 *    son listados del nicho, y llevan dentro el progreso de quien los pidió:
 *    carpetas hechas, subidos, escaparate, vendidos. Con un cajón único, al
 *    entrar el admin en la cuenta de Ana la pantalla salía con el progreso de
 *    él —seis carpetas en verde que Ana no había hecho— hasta que respondía el
 *    Drive, que son segundos.
 *
 *    Separado por persona NO se pierde velocidad: se pinta igual de rápido,
 *    solo que del cajón que toca. Para saber cuál toca ANTES de que responda
 *    `/me` se guarda quién entró el último (`CLAVE_ULTIMO`); quien cambia de
 *    cuenta lo deja escrito antes de recargar (`useCambiarUsuario`), así que
 *    en la primera pintura ya se acierta. `/me` solo hace de red de seguridad
 *    para los casos que no pasan por ahí (sesión caducada, otro dispositivo).
 */
const PREFIJO = "qcache:";
/** Quién entró el último. Sirve para elegir cajón en la primera pintura, antes
 *  de que `/me` haya contestado. */
const CLAVE_ULTIMO = `${PREFIJO}ultimo`;
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

function vacio(data: unknown): boolean {
  if (Array.isArray(data)) return data.length === 0;
  if (data && typeof data === "object") {
    const items = (data as { items?: unknown[] }).items;
    if (Array.isArray(items)) return items.length === 0;
  }
  return data === undefined || data === null;
}

function interesa(key: readonly unknown[]): boolean {
  return typeof key[0] === "string" && PREFIJOS.includes(key[0]);
}

/** Cajón de una persona. Sin usuario cae en uno propio ("anónimo") en vez de
 *  mezclarse con el de nadie. */
function cajon(usuario: string): string {
  return `${PREFIJO}u:${usuario || "?"}:`;
}

function claveDe(usuario: string, key: readonly unknown[]): string {
  return cajon(usuario) + JSON.stringify(key);
}

/** Quién entró el último, o "" si no consta. */
export function ultimoUsuario(): string {
  try {
    return localStorage.getItem(CLAVE_ULTIMO) || "";
  } catch {
    return "";
  }
}

/** Deja apuntado quién manda ahora. Lo llama quien cambia de cuenta ANTES de
 *  recargar, para que la pintura de después ya salga del cajón correcto. */
export function fijarUsuario(usuario: string): void {
  try {
    localStorage.setItem(CLAVE_ULTIMO, usuario);
  } catch {
    /* localStorage bloqueado: se tirará de `/me` y ya está */
  }
}

/** ¿Esta query es de las que se guardan? Son las que llevan el progreso de
 *  una persona, así que también son las que hay que tirar al cambiar de
 *  cuenta. */
export function esDeNicho(key: readonly unknown[]): boolean {
  return interesa(key);
}

/** Borra lo guardado: el cajón de `usuario`, o TODO si no se pasa ninguno. */
export function olvidar(usuario?: string): void {
  const desde = usuario === undefined ? PREFIJO : cajon(usuario);
  try {
    const claves: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const clave = localStorage.key(i);
      if (clave?.startsWith(desde)) claves.push(clave);
    }
    for (const clave of claves) localStorage.removeItem(clave);
  } catch {
    /* localStorage bloqueado (modo privado): no hay nada que limpiar */
  }
}

/** Vuelca lo guardado a la caché. Se llama UNA vez, antes del primer render de
 *  las pantallas, para que la primera pintura ya lleve datos. */
export function hidratar(qc: QueryClient, usuario: string): void {
  const mio = cajon(usuario);
  const entradas: { clave: string; ts: number }[] = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const clave = localStorage.key(i);
      // Solo el cajón de esta persona: el de al lado tiene el progreso de
      // otra, que es justo lo que no puede pintarse aquí.
      if (clave?.startsWith(mio)) entradas.push({ clave, ts: 0 });
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
      // `updatedAt` con la fecha ORIGINAL es imprescindible: sin él React
      // Query da el dato por recién traído y NO refresca hasta pasado el
      // `staleTime`, así que te comes lo guardado aunque esté mal.
      if (qc.getQueryData(key) === undefined) {
        qc.setQueryData(key, data, { updatedAt: ts });
      }
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
export function vigilar(qc: QueryClient, usuario: string): () => void {
  return qc.getQueryCache().subscribe((evento) => {
    const query = evento.query;
    if (!query || query.state.status !== "success") return;
    const key = query.queryKey as readonly unknown[];
    if (!interesa(key)) return;
    // Una lista vacía no se distingue de 'no ha cargado' y es lo peor que
    // se puede pintar: mejor esperar al servidor.
    if (vacio(query.state.data)) return;
    try {
      const cuerpo = JSON.stringify({
        key,
        data: query.state.data,
        ts: Date.now(),
      });
      if (cuerpo.length > MAX_BYTES) return;
      localStorage.setItem(claveDe(usuario, key), cuerpo);
      podar(usuario);
    } catch {
      // Cuota llena: se tira lo viejo y se deja estar. No merece más.
      podar(usuario, true);
    }
  });
}

/** Deja como mucho `MAX_ENTRADAS` en el cajón de esa persona, tirando las más
 *  viejas. El tope es por cajón: son tres personas y `localStorage` da de
 *  sobra para eso. */
function podar(usuario: string, agresivo = false): void {
  const mio = cajon(usuario);
  try {
    const entradas: { clave: string; ts: number }[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const clave = localStorage.key(i);
      if (!clave?.startsWith(mio)) continue;
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
