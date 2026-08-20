"use client";

import { Download } from "lucide-react";
import { useEffect, useState } from "react";

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

  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={() => onOpenChange(false)}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 overflow-y-auto rounded-lg border bg-card p-3"
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
            className="min-h-[12rem] w-full rounded-md border border-border/60 object-contain"
            claseHueco="min-h-[12rem]"
            perezoso={false}
          />
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">
            No hay esta foto en Drive.
          </p>
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
    </div>
  );
}
