"use client";

/** Subida en segundo plano DELEGADA en la app de Android.
 *
 *  Existe por lo que se midió antes de migrar la APK: en la TWA las tandas van
 *  con
 *  Background Fetch, que lo gestiona Chrome y lo corta cuando le parece —de ahí
 *  que "a veces no se suben"—. Una app propia lo hace con un servicio en primer
 *  plano, al que Android no mata mientras tenga su notificación puesta.
 *
 *  La app pone SOLO los bytes: dice qué ficheros y a dónde, y la web se sigue
 *  encargando del reparto y de encolar. Los ficheros no se pasan por el puente
 *  (serían 30 MB por vídeo en base64): la app se quedó con lo que eligió el
 *  usuario en el selector y los dos lados los casan por NOMBRE.
 *
 *  En el navegador —y en la APK vieja, hasta que cada uno actualice— esto no
 *  existe, así que todo lo de aquí devuelve `false` y no cambia nada.
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
  const p = (window as unknown as { AppAndroid?: PuenteAndroid }).AppAndroid;
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

/** Los que escuchan. Un conjunto y no una función suelta porque hay DOS
 *  interesados a la vez y con distinta vida: la pantalla, que refresca la lista
 *  cuando entra un clip, y cada tarjeta, que pinta el porcentaje de SU botón.
 *  Con una sola ranura, el último en montarse borraba al anterior. */
const alTerminarFichero = new Set<(nombre: string, respuesta: string) => void>();
const alAvanzarFichero = new Set<(nombre: string, pct: number) => void>();

/** Engancha los callbacks que llama la app. Se hace una vez y se queda: lo que
 *  entra y sale son los suscriptores, no el puente. */
function engancharPuente() {
  if (typeof window === "undefined") return;
  const w = window as unknown as {
    __subidaAppFichero?: (nombre: string, respuesta: string) => void;
    __subidaAppProgreso?: (nombre: string, pct: number) => void;
  };
  w.__subidaAppFichero = (nombre, respuesta) => {
    alTerminarFichero.forEach((fn) => fn(nombre, respuesta));
  };
  w.__subidaAppProgreso = (nombre, pct) => {
    alAvanzarFichero.forEach((fn) => fn(nombre, pct));
  };
}

/** Avisa de CADA fichero según lo va subiendo la app, para ir marcando la
 *  pantalla sin esperar al final de la tanda. */
export function alSubirCadaFichero(
  fn: (nombre: string, respuesta: string) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  engancharPuente();
  alTerminarFichero.add(fn);
  return () => {
    alTerminarFichero.delete(fn);
  };
}

/** Cuánto lleva subido el fichero que va ahora (0-100).
 *
 *  Existe porque al pasar la subida a la app se perdió el porcentaje del botón:
 *  la app avisaba solo al TERMINAR cada clip, y mientras tanto el botón se
 *  quedaba mudo. Con ocho productos a tres clips, no saber si algo avanza es
 *  justo lo que hace dudar de si se ha quedado colgado. */
export function alProgresoDeFichero(
  fn: (nombre: string, pct: number) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  engancharPuente();
  alAvanzarFichero.add(fn);
  return () => {
    alAvanzarFichero.delete(fn);
  };
}

/** Se avisa cuando la app termina una tanda que acabó con la app cerrada. */
export function alTerminarLaApp(fn: (respuestas: unknown[]) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const w = window as unknown as { __subidaAppLista?: (json: string) => void };
  w.__subidaAppLista = (json: string) => {
    try {
      const datos = JSON.parse(json || "[]");
      if (Array.isArray(datos) && datos.length) fn(datos);
    } catch {
      // Si viniera roto, mejor no repartir nada que repartir mal.
    }
  };
  return () => {
    delete w.__subidaAppLista;
  };
}
