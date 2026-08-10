"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/** Se apunta cada pocos segundos para saber CUÁNDO dejó de vivir la app. */
const CLAVE = "latido-app";
const CADA_MS = 5000;
/** Si el último latido es más viejo que esto, la app ya estaba parada y lo que
 *  hubo fue un arranque normal, no un cierre. */
const MUERTA_MS = 60 * 60 * 1000;

type Latido = {
  ts: number;
  path: string;
  visible: boolean;
  /** Lo pone `pagehide` cuando el operador cierra la app él mismo. */
  adios?: boolean;
  memoriaMB?: number;
  limiteMB?: number;
};

function leer(): Latido | null {
  try {
    const s = localStorage.getItem(CLAVE);
    return s ? (JSON.parse(s) as Latido) : null;
  } catch {
    return null;
  }
}

function memoria(): { memoriaMB?: number; limiteMB?: number } {
  // Solo Chrome, y solo del heap de JS: NO cuenta las imágenes, que es donde
  // se iba la memoria de verdad. Aun así sirve para descartar una fuga.
  const p = performance as Performance & {
    memory?: { usedJSHeapSize: number; jsHeapSizeLimit: number };
  };
  if (!p.memory) return {};
  return {
    memoriaMB: Math.round(p.memory.usedJSHeapSize / 1048576),
    limiteMB: Math.round(p.memory.jsHeapSizeLimit / 1048576),
  };
}

function avisar(evento: Record<string, unknown>) {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  try {
    void fetch(`${base}/api/v1/diagnostics/cliente`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(key ? { "X-API-Key": key } : {}) },
      body: JSON.stringify(evento),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* Si el chivato falla, no puede llevarse por delante a la app. */
  }
}

/** Cuenta al servidor CÓMO terminó la sesión anterior.
 *
 *  Existe porque "la app se cierra sola" tiene tres causas que piden arreglos
 *  distintos y desde fuera se ven igual: que Chrome reviente por memoria, que
 *  Android mate el proceso en segundo plano, o que el operador la cierre. La
 *  única forma de distinguirlas es que la propia app deje un latido y, al
 *  arrancar, mire cómo de fresco quedó y si estaba EN PANTALLA.
 *
 *  Es temporal: cuando sepamos qué pasa, esto se quita.
 */
export function ChivatoCierres() {
  const pathname = usePathname();
  const ruta = useRef(pathname);
  ruta.current = pathname;

  // 1. Al arrancar: ¿cómo acabó la vez anterior?
  useEffect(() => {
    const previo = leer();
    const nav = performance.getEntriesByType("navigation")[0] as
      | PerformanceNavigationTiming
      | undefined;
    const instalada =
      window.matchMedia("(display-mode: standalone)").matches ||
      document.referrer.startsWith("android-app://");

    if (previo && !previo.adios && Date.now() - previo.ts < MUERTA_MS) {
      avisar({
        tipo: "cierre_inesperado",
        // ESTE es el dato que decide el diagnóstico: si murió con la app
        // delante, la culpa es nuestra; si estaba de fondo, es Android.
        estaba_en_pantalla: previo.visible,
        pantalla: previo.path,
        hace_segundos: Math.round((Date.now() - previo.ts) / 1000),
        memoria_mb: previo.memoriaMB,
        limite_mb: previo.limiteMB,
        instalada,
        navegacion: nav?.type,
        // Chrome lo marca cuando descartó la pestaña ÉL por memoria, que es
        // distinto de que el sistema matara el proceso entero.
        descartada: (document as Document & { wasDiscarded?: boolean }).wasDiscarded ?? false,
        ua: navigator.userAgent.slice(0, 120),
      });
    }
  }, []);

  // 2. Latido: la marca de "seguía viva a esta hora, en esta pantalla".
  useEffect(() => {
    function latir(extra: Partial<Latido> = {}) {
      try {
        const l: Latido = {
          ts: Date.now(),
          path: ruta.current,
          visible: document.visibilityState === "visible",
          ...memoria(),
          ...extra,
        };
        localStorage.setItem(CLAVE, JSON.stringify(l));
      } catch {
        /* localStorage lleno: no es motivo para romper nada. */
      }
    }

    latir();
    const id = setInterval(latir, CADA_MS);

    // `pagehide` es el único que llega de verdad en móvil (`beforeunload` no).
    // Marca el cierre como voluntario para no acusar a Android de algo que
    // hizo el operador.
    const despedirse = () => latir({ adios: true });
    window.addEventListener("pagehide", despedirse);
    // Al volver a primera plano se limpia la despedida: si no, un cierre real
    // tras minimizar y volver pasaría por voluntario.
    const alVolver = () => document.visibilityState === "visible" && latir();
    document.addEventListener("visibilitychange", alVolver);

    return () => {
      clearInterval(id);
      window.removeEventListener("pagehide", despedirse);
      document.removeEventListener("visibilitychange", alVolver);
    };
  }, []);

  // 3. Errores sueltos de JS: si lo que mata la pantalla es una excepción,
  //    aquí sale con nombre y apellidos.
  useEffect(() => {
    const onError = (e: ErrorEvent) =>
      avisar({
        tipo: "error_js",
        mensaje: String(e.message).slice(0, 300),
        donde: `${e.filename}:${e.lineno}`,
        pantalla: ruta.current,
      });
    const onRechazo = (e: PromiseRejectionEvent) =>
      avisar({
        tipo: "promesa_sin_capturar",
        mensaje: String(e.reason).slice(0, 300),
        pantalla: ruta.current,
      });
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRechazo);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRechazo);
    };
  }, []);

  return null;
}
