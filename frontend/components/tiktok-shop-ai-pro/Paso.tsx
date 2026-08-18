"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";

/** Un paso del flujo de trabajo, con su número y su color.
 *
 *  Existe porque las tres pantallas de nicho hacen LO MISMO en el mismo orden
 *  (preparar → generar fuera → traer los vídeos → descargar) y antes se veían
 *  como una lista plana de botones: no se distinguía dónde acababa un paso y
 *  empezaba otro, y cosas tan distintas como "copiar el prompt" y "subir todos
 *  los vídeos" parecían la misma clase de acción. Entran tres personas nuevas a
 *  usar esto, así que el orden tiene que leerse sin explicación.
 *
 *  Cada paso lleva SU color y se mantiene igual en los tres nichos: quien
 *  aprende uno sabe usar los otros.
 */
export type ColorPaso = "violeta" | "fucsia" | "esmeralda" | "azul";

const COLORES: Record<ColorPaso, { borde: string; fondo: string; texto: string; num: string }> = {
  violeta: {
    borde: "border-violet-500/40",
    fondo: "bg-violet-500/[0.06]",
    texto: "text-violet-400",
    num: "bg-violet-500 text-white",
  },
  fucsia: {
    borde: "border-fuchsia-500/40",
    fondo: "bg-fuchsia-500/[0.06]",
    texto: "text-fuchsia-400",
    num: "bg-fuchsia-500 text-white",
  },
  esmeralda: {
    borde: "border-emerald-500/40",
    fondo: "bg-emerald-500/[0.06]",
    texto: "text-emerald-400",
    num: "bg-emerald-500 text-white",
  },
  azul: {
    borde: "border-sky-500/40",
    fondo: "bg-sky-500/[0.06]",
    texto: "text-sky-400",
    num: "bg-sky-500 text-white",
  },
};

export function Paso({
  n,
  titulo,
  hint,
  color,
  extra,
  plegable,
  abiertoPorDefecto = true,
  children,
}: {
  /** El número que se ve. Es el orden en que se hacen las cosas. */
  n: number;
  titulo: string;
  /** Una línea de qué se hace aquí. Se lee más que el título. */
  hint: string;
  color: ColorPaso;
  /** Contador o estado a la derecha del título (p. ej. "9/10"). */
  extra?: ReactNode;
  /** Se pliega tocando la cabecera, y plegado NO se monta el contenido: los
   *  pasos de generar fotos traen decenas de miniaturas y, una vez hecho ese
   *  trabajo, solo sirven para que la pantalla tarde en abrir. */
  plegable?: boolean;
  abiertoPorDefecto?: boolean;
  children: ReactNode;
}) {
  const c = COLORES[color];
  // Se recuerda: quien lo pliega no quiere volver a plegarlo cada vez.
  const [abierto, setAbierto] = useEstadoRecordado(
    `paso-abierto:${n}:${titulo}`,
    abiertoPorDefecto,
  );
  const desplegado = !plegable || abierto;
  return (
    <section className={`space-y-2 rounded-xl border ${c.borde} ${c.fondo} p-3`}>
      <div
        className={`flex items-start gap-2 ${plegable ? "cursor-pointer" : ""}`}
        onClick={plegable ? () => setAbierto(!abierto) : undefined}
      >
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${c.num}`}
        >
          {n}
        </span>
        <div className="min-w-0 flex-1">
          <p className={`flex items-center gap-1 text-xs font-semibold sm:text-sm ${c.texto}`}>
            {plegable &&
              (desplegado ? (
                <ChevronDown className="h-3.5 w-3.5 shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 shrink-0" />
              ))}
            {titulo}
          </p>
          {desplegado && (
            <p className="text-[10px] leading-relaxed text-muted-foreground sm:text-[11px]">
              {hint}
            </p>
          )}
        </div>
        {extra ? <div className="shrink-0 text-[10px] text-muted-foreground">{extra}</div> : null}
      </div>
      {desplegado && <div className="space-y-1.5">{children}</div>}
    </section>
  );
}

/** Separador de "esto o lo otro" dentro de un paso: dos caminos que llevan al
 *  mismo sitio (Magnific o copiar los prompts a mano). */
export function OSepara() {
  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="h-px flex-1 bg-border/60" />
      <span className="text-[10px] font-semibold uppercase text-muted-foreground">o</span>
      <span className="h-px flex-1 bg-border/60" />
    </div>
  );
}

/** Caja con cabecera, para lo que NO es un paso del flujo: elegir dónde
 *  trabajas, la carpeta abierta, el ranking de ventas…
 *
 *  Comparte lenguaje con `Paso` (mismo radio, misma cabecera, mismos tamaños)
 *  pero en gris, para que se lea a la primera qué es contexto y qué es trabajo
 *  por hacer. Antes todo eran recuadros iguales, sin título, y había que
 *  deducir de qué iba cada uno por los botones que tenía dentro.
 */
export function Caja({
  icono,
  titulo,
  hint,
  extra,
  children,
}: {
  icono: ReactNode;
  titulo: string;
  hint?: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-start gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted text-[12px]">
          {icono}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold sm:text-sm">{titulo}</p>
          {hint ? (
            <p className="text-[10px] leading-relaxed text-muted-foreground sm:text-[11px]">
              {hint}
            </p>
          ) : null}
        </div>
        {extra ? <div className="shrink-0 text-[10px] text-muted-foreground">{extra}</div> : null}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

/** Rotulillo para separar bloques dentro de una caja ("Fuente", "Carpetas"). */
export function Sub({ children }: { children: ReactNode }) {
  return (
    <p className="pt-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </p>
  );
}
