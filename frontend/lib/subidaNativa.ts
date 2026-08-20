"use client";

/** Subida en segundo plano DELEGADA en la app de Android.
 *
 *  Existe por lo que se midió con la APK de prueba: hoy las tandas van con
 *  Background Fetch, que lo gestiona Chrome y lo corta cuando le parece —de ahí
 *  que "a veces no se suben"—. Una app propia lo hace con un servicio en primer
 *  plano, al que Android no mata mientras tenga su notificación puesta.
 *
 *  La app pone SOLO los bytes: dice qué ficheros y a dónde, y la web se sigue
 *  encargando del reparto y de encolar. Los ficheros no se pasan por el puente
 *  (serían 30 MB por vídeo en base64): la app se quedó con lo que eligió el
 *  usuario en el selector y los dos lados los casan por NOMBRE.
 *
 *  En el navegador y en la app actual esto no existe, así que todo lo de aquí
 *  devuelve `false` y no cambia nada.
 */

/** Una subida: el fichero elegido, a dónde va y con qué campos. */
export interface TareaSubida {
  /** Nombre del fichero, que es como la app lo casa con lo que eligió el
   *  usuario en el selector. Por el puente NO viajan los bytes. */
  nombre: string;
  /** A dónde. Si se omite, la URL común de la llamada. */
  url?: string;
  /** Los campos del formulario, distintos en cada sitio que sube. */
  campos: Record<string, string>;
}

interface PuenteAndroid {
  puedeSubirEnSegundoPlano?: () => boolean;
  subirVarios?: (url: string, apiKey: string, tareasJson: string) => boolean;
  recogerResultados?: () => string;
}

function puente(): PuenteAndroid | null {
  if (typeof window === "undefined") return null;
  const p = (window as unknown as { PruebaAndroid?: PuenteAndroid }).PruebaAndroid;
  return p ?? null;
}

/** ¿Se está dentro de una app que sabe subir por su cuenta? */
export function haySubidaNativa(): boolean {
  const p = puente();
  return Boolean(p?.puedeSubirEnSegundoPlano?.() && p?.subirVarios);
}

/** Le pasa las subidas a la app. `false` = no se pudo y sube la web. */
export function subirConLaApp(v: {
  url: string;
  apiKey: string;
  tareas: TareaSubida[];
}): boolean {
  const p = puente();
  if (!p?.subirVarios || !v.tareas.length) return false;
  try {
    return p.subirVarios(v.url, v.apiKey, JSON.stringify(v.tareas));
  } catch {
    return false;
  }
}

/** Avisa de CADA fichero según lo va subiendo la app, para ir marcando la
 *  pantalla sin esperar al final de la tanda. */
export function alSubirCadaFichero(
  fn: (nombre: string, respuesta: string) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  const w = window as unknown as {
    __subidaAppFichero?: (nombre: string, respuesta: string) => void;
  };
  w.__subidaAppFichero = fn;
  return () => {
    delete w.__subidaAppFichero;
  };
}

/** Se avisa cuando la app termina una tanda que acabó con la app cerrada. */
export function alTerminarLaApp(fn: (respuestas: unknown[]) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const w = window as unknown as { __subidaPruebaLista?: (json: string) => void };
  w.__subidaPruebaLista = (json: string) => {
    try {
      const datos = JSON.parse(json || "[]");
      if (Array.isArray(datos) && datos.length) fn(datos);
    } catch {
      // Si viniera roto, mejor no repartir nada que repartir mal.
    }
  };
  return () => {
    delete w.__subidaPruebaLista;
  };
}
