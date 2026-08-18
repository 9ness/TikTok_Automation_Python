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
): Promise<{ bajadas: number; fallidas: number }> {
  let bajadas = 0;
  let fallidas = 0;
  for (const [i, f] of archivos.entries()) {
    onProgreso?.(i + 1, archivos.length);
    try {
      const res = await fetch(f.href, { credentials: "include" });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
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
