"use client";

import { Link2 } from "lucide-react";
import { toast } from "sonner";

/** Abre la ficha del producto en TikTok Shop.
 *
 *  Meter un producto en el escaparate es entrar en su ficha, y buscarla a mano
 *  cada vez es lo que hace lento ese trabajo — más con tres cuentas. Las fichas
 *  se pegan una vez en Configuración › "Fichas de TikTok Shop" (por producto,
 *  así que valen para todas sus carpetas y para los tres usuarios) y aquí solo
 *  se abren.
 *
 *  Verde = ya tiene ficha. Apagado = falta pegarla.
 */
export function BotonUrl({ url }: { url?: string | null }) {
  if (!url) {
    return (
      <button
        type="button"
        onClick={() =>
          toast.info("Sin ficha: pégala en Configuración › Fichas de TikTok Shop")
        }
        className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40"
      >
        <Link2 className="h-3 w-3" /> URL
      </button>
    );
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-emerald-500 bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold text-emerald-500 transition hover:bg-emerald-500/25"
    >
      <Link2 className="h-3 w-3" /> URL
    </a>
  );
}
