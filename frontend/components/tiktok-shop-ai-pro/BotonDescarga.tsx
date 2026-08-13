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
      className={`flex items-center justify-center gap-1 rounded-lg border px-2 py-2 text-[11px] transition disabled:opacity-40 ${
        acento
          ? "border-violet-500/50 text-violet-400 hover:border-violet-500"
          : "border-border/60 hover:border-foreground/30"
      }`}
    >
      {cargando ? (
        <>
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
          <span className="truncate">{progreso}</span>
        </>
      ) : (
        <>
          <Download className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{etiqueta}</span>
        </>
      )}
    </button>
  );
}
