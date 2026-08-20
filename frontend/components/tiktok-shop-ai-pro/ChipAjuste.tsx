"use client";

/** Un ajuste de la tarjeta, plegado en un chip.
 *
 *  Nace de mirar qué se usa de verdad: el guion no se lee (se escribe una vez y
 *  ya), las herramientas van siempre las cuatro y la voz siempre en Auto. Cada
 *  una ocupaba una fila entera de la tarjeta —tres filas por producto, diez
 *  productos por carpeta— para enseñar algo que no se toca.
 *
 *  Ahora las tres caben en UNA fila de chips: cada uno enseña su valor actual
 *  (que es lo único que se mira de reojo) y se despliega al tocarlo cuando de
 *  verdad hay que cambiarlo. No se esconde nada, solo deja de ocupar sitio.
 *
 *  `aviso` pinta el chip en ámbar: sirve para lo que hay que ver SIN abrirlo,
 *  como un guion que se escribió con el modo de plazos equivocado.
 */
export function ChipAjuste({
  icono,
  valor,
  abierto,
  onToggle,
  aviso = false,
  title,
}: {
  /** Emoji o símbolo corto, para reconocerlo sin leer. */
  icono: string;
  /** Lo que vale ahora mismo ("Auto", "4/4", "470 car."). */
  valor: string;
  abierto: boolean;
  onToggle: () => void;
  aviso?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={abierto}
      title={title}
      className={`flex min-w-0 flex-1 items-center justify-center gap-1 rounded-md border px-1.5 py-1 text-[10px] leading-tight transition ${
        aviso
          ? "border-amber-500/50 text-amber-500"
          : abierto
            ? "border-violet-500/60 text-violet-400"
            : "border-border/60 text-muted-foreground hover:border-foreground/30"
      }`}
    >
      <span className="shrink-0">{icono}</span>
      <span className="min-w-0 break-words font-medium">{valor}</span>
      <span className="shrink-0 opacity-60">{abierto ? "▾" : "▸"}</span>
    </button>
  );
}
