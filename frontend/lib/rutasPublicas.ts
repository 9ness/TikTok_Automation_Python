/** Rutas que se abren SIN login y sin el marco de la app (sidebar, cola,
 *  barra de cuota…). Hoy solo la página de enlaces de afiliado
 *  `/links/<cuenta>`, que va en la bio de Instagram/Facebook. */
export const PREFIJOS_PUBLICOS = ["/links/"] as const;

export function esRutaPublica(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return PREFIJOS_PUBLICOS.some((p) => pathname.startsWith(p));
}
