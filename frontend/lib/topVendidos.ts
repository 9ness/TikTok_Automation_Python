/** Lo común de la fuente "Top vendidos" en los tres nichos.
 *
 *  Los productos de esa carpeta llevan `ventas` y `vendido_at` del producto de
 *  ORIGEN (el que está en el ranking). El sitio en la carpeta es de por vida
 *  —moverlo perdería el progreso, que se guarda por carpeta—, así que ordenar
 *  por ventas es cosa de la pantalla y se hace aquí, igual en los tres.
 */

export const FUENTE_TOP_VENDIDOS = "top_vendidos";

/** Cuánto dura el cartel de "nuevo". Una semana: es cada cuánto se mira. */
const NUEVO_S = 7 * 24 * 3600;

export interface ConVentas {
  ventas: number;
  vendido_at: number;
}

/** ¿Entró en el ranking hace poco? Es lo que se busca al abrir la pantalla. */
export function esVentaNueva(vendidoAt: number): boolean {
  return vendidoAt > 0 && Date.now() / 1000 - vendidoAt < NUEVO_S;
}

/** Los que más venden primero; a igualdad, el más reciente. */
export function ordenarPorVentas<T extends ConVentas>(items: T[]): T[] {
  return items.slice().sort((a, b) => b.ventas - a.ventas || b.vendido_at - a.vendido_at);
}

/** Ordena y, si se pide, esconde los que ya tienen vídeo subido.
 *
 *  `yaSubido` lo pone cada nicho porque "subido" no significa lo mismo en
 *  todos: en Creativos Pro es el creativo y en los de vídeo es el vídeo.
 */
export function verTopVendidos<T extends ConVentas>(
  items: T[],
  opciones: { activo: boolean; soloSinSubir: boolean; yaSubido: (item: T) => boolean },
): T[] {
  if (!opciones.activo) return items;
  const visibles = opciones.soloSinSubir
    ? items.filter((it) => !opciones.yaSubido(it))
    : items;
  return ordenarPorVentas(visibles);
}
