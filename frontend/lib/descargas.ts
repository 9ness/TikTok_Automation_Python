/** Prefijo de TODO lo que se baja del programa.
 *
 *  Una página web NO puede elegir en qué carpeta guarda el navegador: el
 *  atributo `download` es solo el NOMBRE del fichero y los navegadores quitan
 *  cualquier barra para que no se pueda escribir donde no toca. En el móvil
 *  todo cae en "Descargas" mezclado con lo demás, y no hay forma de cambiarlo
 *  desde aquí.
 *
 *  Lo que sí se puede: que todo empiece igual. Así en la app de Archivos se
 *  ordenan juntos, se buscan escribiendo "ttshop" y se seleccionan en bloque
 *  para borrarlos sin tocar nada del móvil.
 */
export const PREFIJO_DESCARGA = "TTShopAIPro_";

/** Nombre de fichero para bajar: con el prefijo del programa y sin caracteres
 *  que el sistema no acepte. La extensión, si la hay, se respeta. */
export function nombreDescarga(...partes: (string | number)[]): string {
  const limpio = partes
    .map((x) => String(x ?? "").trim())
    .filter(Boolean)
    .join("_")
    .replace(/[^a-zA-Z0-9_.-]+/g, "_");
  return `${PREFIJO_DESCARGA}${limpio}`;
}

/** Bajar varias fotos EN ORDEN, de verdad.
 *
 *  Con `<a download>` el navegador solo *empieza* la descarga: el fichero se
 *  crea cuando termina, así que las pequeñas adelantan a las grandes y en la
 *  galería del móvil (que ordena por fecha) los pares salen descolocados —
 *  todas las fotos de producto primero y las de la chica después.
 *
 *  Aquí se baja el contenido ANTES (fetch → blob) y solo entonces se guarda:
 *  el fichero se crea en el momento del click, así que el orden en el disco es
 *  el mismo que el de la lista. De paso va más rápido, porque no hace falta
 *  dejar 600 ms entre una y otra por si acaso.
 */
export async function bajarEnOrden(
  archivos: { href: string; nombre: string }[],
  onProgreso?: (hechos: number, total: number) => void,
  /** Cuántos se piden a la vez. Se GUARDAN igual en orden: solo se adelanta
   *  la bajada de los siguientes mientras se espera al actual. */
  simultaneas = 1,
): Promise<{ bajadas: number; fallidas: number }> {
  let bajadas = 0;
  let fallidas = 0;
  const pedir = (f: { href: string }) =>
    fetch(f.href, { credentials: "include" }).then((res) => {
      if (!res.ok) throw new Error(String(res.status));
      return res.blob();
    });
  const enCurso: Promise<Blob>[] = [];
  const lanzar = (j: number) => {
    if (j < archivos.length && !enCurso[j]) {
      enCurso[j] = pedir(archivos[j]!);
      // Que un fallo no quede como promesa rechazada sin atender antes de
      // llegarle el turno.
      enCurso[j].catch(() => undefined);
    }
  };
  for (const [i, f] of archivos.entries()) {
    onProgreso?.(i + 1, archivos.length);
    for (let j = i; j < i + Math.max(1, simultaneas); j++) lanzar(j);
    try {
      const blob = (await enCurso[i])!;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = f.nombre;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Se libera un poco después: revocarlo en el mismo tick corta la
      // descarga en algunos navegadores móviles.
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      bajadas += 1;
    } catch {
      fallidas += 1;
    }
    // Un respiro corto: el fichero ya está bajado, esto es solo para que el
    // gestor de descargas no agrupe dos guardados en el mismo instante.
    await new Promise((r) => setTimeout(r, 150));
  }
  return { bajadas, fallidas };
}
