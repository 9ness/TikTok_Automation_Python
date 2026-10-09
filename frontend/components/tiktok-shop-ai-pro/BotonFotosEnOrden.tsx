"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { descargarFotosCarrusel } from "@/lib/queries/replicarCarrusel";

/** Baja las fotos de un carrusel una a una, en orden (01, 02…), sin ZIP. Lo
 *  usan Replicar carrusel y Mis tandas › Fotos. */
export function BotonFotosEnOrden({
  id,
  disabled = false,
  etiqueta = "Descargar todas",
  className = "",
}: {
  id: string;
  disabled?: boolean;
  etiqueta?: string;
  className?: string;
}) {
  const [bajando, setBajando] = useState(false);
  return (
    <button
      type="button"
      disabled={disabled || bajando}
      onClick={async () => {
        setBajando(true);
        try {
          const n = await descargarFotosCarrusel(id);
          if (n) toast.success(`${n} fotos descargadas en orden`);
          else toast.error("Aún no hay ninguna foto subida en este carrusel.");
        } catch (e) {
          toast.error(`No se pudieron descargar: ${(e as Error).message}`);
        } finally {
          setBajando(false);
        }
      }}
      className={`flex items-center gap-1.5 rounded-lg border border-sky-500/50 font-semibold text-sky-400 hover:bg-sky-500/10 disabled:pointer-events-none disabled:opacity-40 ${className}`}
    >
      {bajando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
      {etiqueta}
    </button>
  );
}
