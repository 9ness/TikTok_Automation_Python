"use client";

import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { FotoProducto } from "./FotoProducto";

/** Las dos fotos de un producto: la limpia y la captura con el título.
 *
 *  Compartido entre nichos a propósito. Las URLs se pasan ya construidas
 *  porque cada nicho lee de un Drive distinto (uno por "Compartido conmigo",
 *  otro por enlace), pero lo que ve el operador es exactamente lo mismo.
 */
export function FotoModal({
  open,
  onOpenChange,
  titulo,
  urlLimpia,
  urlTitulo,
  urlDescarga,
  textoDescarga = "Descargar la foto del producto",
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  titulo: string;
  urlLimpia: string | null;
  urlTitulo: string | null;
  urlDescarga?: string | null;
  /** Qué foto baja el botón. Se dice porque no siempre es la misma: Creativos
   *  Pro baja la de la ficha y el POV BOF la limpia, y un botón que no aclara
   *  cuál de las dos trae hace dudar antes de pulsarlo. */
  textoDescarga?: string;
}) {
  const [cual, setCual] = useState<"limpia" | "titulo">("limpia");
  const src = cual === "limpia" ? urlLimpia : urlTitulo;

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open || typeof document === "undefined") return null;

  // Colgado del `<body>` y no de donde se usa. `position: fixed` deja de
  // referirse a la pantalla en cuanto CUALQUIER ancestro tiene `transform`,
  // `filter` o `contain`, y entonces el visor se recorta a ese ancestro: eso
  // es exactamente lo que se veía en el móvil —una tira con el título cortado
  // por abajo— mientras que en el escritorio salía bien. Sacándolo del árbol
  // no hay ancestro que valga.
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      onClick={() => onOpenChange(false)}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        // El alto mínimo es un seguro: si algo vuelve a encoger el visor, que
        // se note que es el visor y no una tira sin sentido.
        className="flex max-h-[92vh] min-h-[16rem] w-[calc(100vw-1rem)] max-w-lg flex-col gap-2 overflow-y-auto rounded-lg border bg-card p-3"
      >
        <div className="flex items-start justify-between gap-2">
          <p className="min-w-0 flex-1 truncate text-sm font-semibold">{titulo}</p>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Cerrar"
            className="rounded-sm p-1 text-muted-foreground hover:text-foreground"
          >
            ✕
          </button>
        </div>

        {/* El selector solo aparece si hay las dos: en algunas carpetas solo
            está la foto limpia y un botón muerto confunde. */}
        {urlTitulo && (
          <div className="grid grid-cols-2 gap-1">
            {(["limpia", "titulo"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setCual(k)}
                className={`rounded-md border px-2 py-1 text-[11px] transition ${
                  cual === k
                    ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                    : "border-border/60 text-muted-foreground"
                }`}
              >
                {k === "limpia" ? "Foto del producto" : "Captura con título"}
              </button>
            ))}
          </div>
        )}

        {/* Con reintento, igual que las miniaturas, pero SIN carga perezosa:
            eso último es lo que dejaba el visor con solo la cabecera. La imagen
            se inserta ya montada y el WebView la daba por fuera de pantalla, así
            que no la pedía nunca — ni cargaba ni fallaba, y por eso tampoco
            saltaba el reintento. */}
        {src ? (
          <FotoProducto
            src={src}
            alt={titulo}
            className="h-[70vh] w-full shrink-0 rounded-md border border-border/60 object-contain"
            claseHueco="min-h-[12rem]"
            perezoso={false}
          />
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">
            No hay esta foto en Drive.
          </p>
        )}

        {/* Salida de emergencia: si la foto no viene, abrirla aparte enseña el
            error de verdad (un 502, un 401, lo que sea) en vez de dejar un
            hueco que no explica nada. */}
        {src && (
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            className="text-center text-[10px] text-muted-foreground underline decoration-dotted"
          >
            ¿No sale? Ábrela aparte
          </a>
        )}

        {urlDescarga && (
          <a
            href={urlDescarga}
            className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] font-medium transition hover:border-foreground/30"
          >
            <Download className="h-3.5 w-3.5" /> {textoDescarga}
          </a>
        )}
      </div>
    </div>,
    document.body,
  );
}
