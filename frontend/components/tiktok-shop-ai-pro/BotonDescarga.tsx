"use client";

import { Download, Loader2 } from "lucide-react";

/** Un botón de la fila "Descargar".
 *
 *  Hay seis por pantalla (fotos y vídeos × todas / normal / plazos) y en dos
 *  nichos: escritos a mano serían doce copias, con la garantía de que alguna
 *  acabaría distinta de las demás.
 *
 *  `tono` pinta el botón del color de lo que baja, para que se reconozca sin
 *  leer: violeta = plazos, verde = tiene la ficha del producto enlazada, y un
 *  color por NÚMERO DE CLIPS (el mismo del borde de esas tarjetas, para que se
 *  lea como una sola cosa).
 *
 *  La escala de clips es común a los dos nichos: el POV BOF pide uno o dos y el
 *  Largo tres o cuatro, así que un color por número deja las dos pantallas
 *  hablando el mismo idioma. Se evitan a propósito el verde y el violeta, que
 *  aquí ya significan "tiene ficha enlazada" y "plazos".
 *
 *  El texto SE PARTE, no se corta. Van de tres en tres y en un móvil de 360 px
 *  cada uno se queda en ~70 px de texto: con `truncate`, "💳 Plazos (12)" se
 *  quedaba en "💳 Pla…" y no había forma de saber qué bajaba cada botón. Roto
 *  en dos renglones cabe entero y la fila sigue siendo de tres.
 */
export type Tono =
  | "normal"
  | "plazos"
  | "url"
  | "clips1"
  | "clips2"
  | "clips3"
  | "clips4";

const TONOS: Record<Tono, string> = {
  normal: "border-border/60 hover:border-foreground/30",
  plazos: "border-violet-500/50 text-violet-400 hover:border-violet-500",
  // Verde, el mismo del botón «URL» de cada tarjeta.
  url: "border-emerald-500/50 text-emerald-400 hover:border-emerald-500",
  clips1: "border-sky-500/50 text-sky-400 hover:border-sky-500",
  clips2: "border-lime-500/50 text-lime-400 hover:border-lime-500",
  clips3: "border-amber-500/50 text-amber-400 hover:border-amber-500",
  clips4: "border-rose-500/50 text-rose-400 hover:border-rose-500",
};

export function BotonDescarga({
  onClick,
  cargando,
  progreso = "",
  disabled = false,
  etiqueta,
  tono = "normal",
}: {
  onClick: () => void;
  cargando: boolean;
  /** Lo que se pinta mientras baja ("3/8"). */
  progreso?: string;
  disabled?: boolean;
  etiqueta: string;
  tono?: Tono;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || cargando}
      className={`flex min-w-0 items-center justify-center gap-1 rounded-lg border px-1.5 py-2 text-center text-[11px] leading-tight transition disabled:opacity-40 ${TONOS[tono]}`}
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
