/** Rutas que se abren SIN login y sin el marco de la app (sidebar, cola,
 *  barra de cuota…). Hoy solo la página de enlaces de afiliado
 *  `/links/<cuenta>`, que va en la bio de Instagram/Facebook. */
export const PREFIJOS_PUBLICOS = ["/links/"] as const;

/** `links.nebulabsmedia.com/<cuenta>`: Caddy reescribe a `/links/<cuenta>`,
 *  pero el navegador sigue viendo `/<cuenta>` (sin prefijo). En ese host todo
 *  es público: Caddy no deja pasar nada más. */
function esHostLinks(): boolean {
  return typeof window !== "undefined" && window.location.hostname.startsWith("links.");
}

export function esRutaPublica(pathname: string | null | undefined): boolean {
  if (esHostLinks()) return true;
  if (!pathname) return false;
  return PREFIJOS_PUBLICOS.some((p) => pathname.startsWith(p));
}
