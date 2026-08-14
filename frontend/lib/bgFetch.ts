"use client";

/** Subida en segundo plano (Background Fetch) — Chrome Android, o sea la APK.
 *
 *  Es lo que hace que se puedan soltar los vídeos, bloquear el móvil y cerrar
 *  la app sin que se corte: el sistema sigue subiendo y enseña el progreso en
 *  una notificación. Donde no existe (iOS, Firefox, escritorio) esto devuelve
 *  `false` y la pantalla sube por la vía normal, que también sabe retomarse.
 *
 *  El trabajo de después (recoger tokens, repartir, encolar) lo hace
 *  `public/sw-subidas.js`.
 */

interface BgFetchRegistration extends EventTarget {
  id: string;
  uploaded: number;
  uploadTotal: number;
  result: string;
  failureReason: string;
  abort(): Promise<boolean>;
}

interface BgFetchManager {
  fetch(id: string, requests: Request[], options?: Record<string, unknown>): Promise<BgFetchRegistration>;
  get(id: string): Promise<BgFetchRegistration | undefined>;
}

type RegistroConBg = ServiceWorkerRegistration & { backgroundFetch?: BgFetchManager };

export function soportaBgFetch(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "BackgroundFetchManager" in window
  );
}

let registrando: Promise<RegistroConBg | null> | null = null;

export function registrarSw(): Promise<RegistroConBg | null> {
  if (!soportaBgFetch()) return Promise.resolve(null);
  // El registro se comparte: llamarlo desde dos pantallas no debe registrar dos
  // veces ni esperar dos veces al `ready`.
  registrando ??= navigator.serviceWorker
    .register("/sw-subidas.js", { scope: "/" })
    .then(() => navigator.serviceWorker.ready as Promise<RegistroConBg>)
    .catch(() => null);
  return registrando;
}

/** Lanza la tanda. Devuelve `false` si no se pudo y hay que subir a mano. */
export async function lanzarEnSegundoPlano(v: {
  loteId: string;
  url: string;
  apiKey: string;
  source: string;
  folder: string;
  files: File[];
}): Promise<BgFetchRegistration | null> {
  const reg = await registrarSw();
  if (!reg?.backgroundFetch) return null;
  try {
    // Si quedaba una tanda anterior de la misma carpeta a medias, fuera: si no,
    // `fetch()` con el mismo id revienta.
    const previa = await reg.backgroundFetch.get(v.loteId);
    if (previa) await previa.abort().catch(() => false);

    const peticiones = v.files.map((file, i) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("source", v.source);
      fd.append("folder", v.folder);
      // `?i=` es la ÚNICA forma de saber después qué respuesta es de qué
      // fichero: todas las peticiones van a la misma URL.
      return new Request(`${v.url}?i=${i}`, {
        method: "POST",
        body: fd,
        credentials: "include",
        headers: v.apiKey ? { "X-API-Key": v.apiKey } : undefined,
      });
    });

    const total = v.files.reduce((n, f) => n + f.size, 0);
    return await reg.backgroundFetch.fetch(v.loteId, peticiones, {
      title: `Subiendo ${v.files.length} vídeo(s)`,
      icons: [{ src: "/icon-192.png", sizes: "192x192", type: "image/png" }],
      // Es la respuesta lo que se descarga (JSON diminuto); el peso de verdad
      // es la subida, y Chrome lo saca de las propias peticiones.
      downloadTotal: Math.max(1024, v.files.length * 512),
      uploadTotal: total,
    });
  } catch {
    return null;
  }
}

export async function tandaEnMarcha(loteId: string): Promise<BgFetchRegistration | null> {
  const reg = await registrarSw();
  if (!reg?.backgroundFetch) return null;
  try {
    return (await reg.backgroundFetch.get(loteId)) ?? null;
  } catch {
    return null;
  }
}

/** Avisos que manda el Service Worker cuando termina con la app cerrada. */
export type AvisoLote =
  | { tipo: "lote-subido"; loteId: string }
  | { tipo: "lote-encolado"; loteId: string; encolados: number }
  | { tipo: "lote-cancelado"; loteId: string }
  | { tipo: "lote-fallo"; loteId: string };

export function escucharAvisos(fn: (a: AvisoLote) => void): () => void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return () => {};
  const handler = (e: MessageEvent) => {
    const d = e.data as AvisoLote | undefined;
    if (d && typeof d.tipo === "string" && d.tipo.startsWith("lote-")) fn(d);
  };
  navigator.serviceWorker.addEventListener("message", handler);
  return () => navigator.serviceWorker.removeEventListener("message", handler);
}
