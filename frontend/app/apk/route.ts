/** Sirve la APK desde NUESTRO dominio.
 *
 *  El botón apuntaba directamente a la release de GitHub y en el móvil la
 *  descarga se quedaba clavada en "Descargando…" con el fichero ya completo, y
 *  luego no aparecía en Descargas. La causa es el camino: GitHub redirige a
 *  `objects.githubusercontent.com` y eso, dentro de la pestaña incrustada que
 *  abre la app, deja la descarga a medio camino.
 *
 *  Aquí no hay redirección ni otro dominio, y se manda el tipo de contenido de
 *  verdad (`vnd.android.package-archive`) más el nombre en `Content-Disposition`
 *  — que es lo que mira Android para saber que es una app y ofrecer instalarla.
 *  Mismo problema que ya dio la cola cuando los vídeos bajaban como `.bin`.
 */

const ORIGEN =
  "https://github.com/9ness/TikTok_Automation_Python/releases/download/apk-latest/tiktok-auto.apk";

// Sin esto Next intentaría prerenderizarla en el build, cuando la release aún
// puede ser otra.
export const dynamic = "force-dynamic";

export async function GET() {
  const arriba = await fetch(ORIGEN, { redirect: "follow", cache: "no-store" });

  if (!arriba.ok || !arriba.body) {
    return new Response(
      `No se pudo traer la APK de GitHub (${arriba.status}).`,
      { status: 502, headers: { "Content-Type": "text/plain; charset=utf-8" } },
    );
  }

  const cabeceras = new Headers({
    "Content-Type": "application/vnd.android.package-archive",
    "Content-Disposition": 'attachment; filename="tiktok-auto.apk"',
    "Cache-Control": "no-store",
  });
  // Sin el tamaño, la barra de progreso del móvil no sabe cuánto queda.
  const largo = arriba.headers.get("content-length");
  if (largo) cabeceras.set("Content-Length", largo);

  return new Response(arriba.body, { headers: cabeceras });
}
