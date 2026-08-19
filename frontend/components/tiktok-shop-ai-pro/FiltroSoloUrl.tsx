"use client";

import { Link2, Link2Off } from "lucide-react";

/** "Solo los que tienen URL" — el interruptor de trabajar con lo que se va a
 *  subir.
 *
 *  Es un COMPONENTE compartido y no una casilla copiada en cada nicho: el POV
 *  BOF y el POV BOF Largo se usan seguidos —se empieza en uno y se pasa al
 *  otro— y cualquier diferencia entre los dos se paga en desconcierto. Aquí
 *  vale doble porque son la misma acción con el mismo nombre.
 *
 *  Botón entero y no una casilla suelta: en un móvil, un `checkbox` de 16 px es
 *  un blanco pequeño, y la mitad de las veces se toca al lado y no pasa nada.
 *  Así se pulsa la fila completa y, encendido, se ve de un vistazo que lo que
 *  hay en pantalla NO es todo (que es lo que despista si se olvida puesto).
 */
export function FiltroSoloUrl({
  activo,
  onChange,
  conUrl,
  total,
}: {
  activo: boolean;
  onChange: (v: boolean) => void;
  /** Cuántos de la carpeta tienen la ficha enlazada. */
  conUrl: number;
  /** Cuántos hay en total. */
  total: number;
}) {
  if (!total) return null;
  const Icono = activo ? Link2 : Link2Off;
  return (
    <button
      type="button"
      onClick={() => onChange(!activo)}
      aria-pressed={activo}
      className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-[11px] transition ${
        activo
          ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
          : "border-border/60 text-muted-foreground hover:border-emerald-500/40"
      }`}
    >
      <Icono className="h-4 w-4 shrink-0" strokeWidth={2} />
      <span className="min-w-0 break-words font-medium leading-tight">
        Solo los que tienen URL
      </span>
      <span
        className={`ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums ${
          activo ? "bg-emerald-500/20" : "bg-muted-foreground/10"
        }`}
      >
        {conUrl}/{total}
      </span>
    </button>
  );
}
