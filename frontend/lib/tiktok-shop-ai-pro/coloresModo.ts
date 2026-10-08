/** Un color FIJO por nicho, modo y catálogo, para reconocerlos de un vistazo
 *  en listas que los mezclan (Mis tandas).
 *
 *  - Nicho: píldora rellena fuerte.
 *  - Modo / estilo: píldora rellena suave.
 *  - Catálogo: píldora con BORDE (así no se confunde con un modo del mismo
 *    color).
 *
 *  Las clases van escritas enteras: Tailwind solo genera las que ve literales.
 *
 *  ⚠️ Modo NUEVO (estilo de guion del Largo, formato del multimodo) o nicho
 *  nuevo en Mis tandas → se le da color AQUÍ en el mismo cambio, sin repetir
 *  el de otro modo del mismo nicho. `tests/mis_tandas/test_colores.py` falla
 *  si falta alguno. */

export const COLOR_NICHO: Record<string, string> = {
  pov: "bg-sky-500/25 text-sky-700 dark:text-sky-300",
  largo: "bg-violet-500/25 text-violet-700 dark:text-violet-300",
  mm: "bg-pink-500/25 text-pink-700 dark:text-pink-300",
  alea: "bg-rose-500/25 text-rose-700 dark:text-rose-300",
};

export const NOMBRE_NICHO: Record<string, string> = {
  pov: "POV BOF",
  largo: "POV Largo",
  mm: "Moda Mujer",
  alea: "Moda Aleatorios",
};

/** Estilos de guion del POV BOF Largo. */
const ESTILOS_LARGO: Record<string, string> = {
  precio: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  dolor: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  epico: "bg-red-600/25 text-red-700 dark:text-red-300",
  inversa: "bg-teal-500/15 text-teal-700 dark:text-teal-300",
  viral: "bg-sky-600/20 text-sky-700 dark:text-sky-300",
};

/** Familias de formatos del multimodo (por cómo empieza su clave): mismo
 *  color para los formatos de una familia (Bolso 1, 2 y 3). */
const FAMILIAS_MM: [string, string, string][] = [
  ["mm_zapatillas_pov20", "Zapatillas 20s", "bg-yellow-500/15 text-yellow-700 dark:text-yellow-300"],
  ["mm_zapatillas_sentado20", "Zapatillas 20s", "bg-yellow-500/15 text-yellow-700 dark:text-yellow-300"],
  ["mm_espejo", "🪞 Espejo", "bg-pink-500/15 text-pink-700 dark:text-pink-300"],
  ["mm_maniqui", "👕 Camisetas", "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300"],
  ["mm_sarcastica", "👕 Camisetas", "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300"],
  ["mm_zapatillas", "👟 Zapatillas", "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300"],
  ["mm_zapatos", "👠 Zapatos", "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300"],
  ["mm_botas", "🍂 Botas", "bg-orange-500/15 text-orange-700 dark:text-orange-300"],
  ["mm_bolso", "👜 Bolsos", "bg-lime-500/15 text-lime-700 dark:text-lime-300"],
  ["mm_habla", "🎙️ Hablados", "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"],
];

/** Modos de Moda Mujer · Aleatorios (los que hablan). */
const MODOS_ALEA: Record<string, string> = {
  tienda_colores: "bg-purple-500/15 text-purple-700 dark:text-purple-300",
  calle_dividido: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
};

const NEUTRO = "bg-muted text-muted-foreground";

export function colorModo(nicho: string, modo: string): string {
  if (nicho === "largo") return ESTILOS_LARGO[modo] ?? NEUTRO;
  if (nicho === "mm") return FAMILIAS_MM.find(([p]) => modo.startsWith(p))?.[2] ?? NEUTRO;
  if (nicho === "alea") return MODOS_ALEA[modo] ?? NEUTRO;
  return NEUTRO;
}

/** Para el resumen de una tanda: la familia del vídeo (con su color). */
export function familiaModo(nicho: string, modo: string, modoLabel: string) {
  if (nicho === "pov") return { clave: "pov", label: "POV BOF", color: COLOR_NICHO.pov ?? NEUTRO };
  if (nicho === "largo") return { clave: `largo|${modo}`, label: `Largo · ${modoLabel}`, color: colorModo(nicho, modo) };
  if (nicho === "alea") return { clave: `alea|${modo}`, label: modoLabel || modo, color: colorModo(nicho, modo) };
  const f = FAMILIAS_MM.find(([p]) => modo.startsWith(p));
  return f
    ? { clave: `mm|${f[1]}`, label: f[1], color: f[2] }
    : { clave: `mm|${modo}`, label: modoLabel || modo, color: NEUTRO };
}

/** Catálogos: los del POV (fuentes) y los de Moda Mujer (zapatos, accesorios…). */
const CATALOGOS: [string, string][] = [
  ["mujer_zapatos", "border-indigo-500/60 text-indigo-700 dark:text-indigo-300"],
  ["mujer_accesorios", "border-lime-500/60 text-lime-700 dark:text-lime-300"],
  ["mujer_muestras", "border-slate-400/70 text-slate-600 dark:text-slate-300"],
  ["mujer_tareas", "border-stone-400/70 text-stone-600 dark:text-stone-300"],
  ["mujer_temporada", "border-red-500/70 text-red-600 dark:text-red-400"],
  ["mujer", "border-pink-500/60 text-pink-700 dark:text-pink-300"],
  ["inventario_general", "border-blue-500/60 text-blue-700 dark:text-blue-300"],
  ["productos_web", "border-cyan-500/60 text-cyan-700 dark:text-cyan-300"],
  ["top_vendidos", "border-yellow-500/60 text-yellow-700 dark:text-yellow-300"],
  ["mis_productos", "border-slate-400/70 text-slate-600 dark:text-slate-300"],
  ["tareas_productos", "border-stone-400/70 text-stone-600 dark:text-stone-300"],
  ["temporada_q4", "border-red-500/70 text-red-600 dark:text-red-400"],
  ["carruseles_virales", "border-violet-500/60 text-violet-700 dark:text-violet-300"],
  ["aleatorios", "border-zinc-400/70 text-zinc-600 dark:text-zinc-300"],
];

export function colorCatalogo(catalogo: string): string {
  return CATALOGOS.find(([p]) => catalogo.startsWith(p))?.[1] ?? "border-border text-muted-foreground";
}
