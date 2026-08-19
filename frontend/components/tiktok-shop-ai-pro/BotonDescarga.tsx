"use client";

import { Download, Loader2 } from "lucide-react";

/** Un botón de la fila "Descargar".
 *
 *  Hay seis por pantalla (fotos y vídeos × todas / normal / plazos) y en dos
 *  nichos: escritos a mano serían doce copias, con la garantía de que alguna
 *  acabaría distinta de las demás.
 *
 *  `acento` es para los de plazos, que van en violeta como el resto de lo que
 *  tiene que ver con ese flujo.
 *
 *  El texto SE PARTE, no se corta. Van de tres en tres y en un móvil de 360 px
 *  cada uno se queda en ~70 px de texto: con `truncate`, "💳 Plazos (12)" se
 *  quedaba en "💳 Pla…" y no había forma de saber qué bajaba cada botón. Roto
 *  en dos renglones cabe entero y la fila sigue siendo de tres.
 */
export function BotonDescarga({
  onClick,
  cargando,
  progreso = "",
  disabled = false,
  etiqueta,
  acento = false,
}: {
  onClick: () => void;
  cargando: boolean;
  /** Lo que se pinta mientras baja ("3/8"). */
  progreso?: string;
  disabled?: boolean;
  etiqueta: string;
  acento?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || cargando}
      className={`flex min-w-0 items-center justify-center gap-1 rounded-lg border px-1.5 py-2 text-center text-[11px] leading-tight transition disabled:opacity-40 ${
        acento
          ? "border-violet-500/50 text-violet-400 hover:border-violet-500"
          : "border-border/60 hover:border-foreground/30"
      }`}
    >
      {cargando ? (
        <>
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
          <span className="min-w-0 break-words">{progreso}</span>
        </>
      ) : (
        <>
          <Download className="h-3.5 w-3.5 shrink-0" />
          <span className="min-w-0 break-words">{etiqueta}</span>
        </>
      )}
    </button>
  );
}
