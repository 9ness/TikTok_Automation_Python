"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useSincronizarTopVendidos, useSources } from "@/lib/queries/nichoPovBof";
import { FUENTE_TOP_VENDIDOS } from "@/lib/topVendidos";

/** Trae al Top vendidos los productos del ranking que aún no estén.
 *
 *  Vive aquí y no dentro de una página porque la carpeta "Top vendidos" es la
 *  MISMA para todos los nichos: se sincroniza una vez y la ven el POV BOF, el
 *  Largo y los demás. Estaba solo en el POV BOF y desde el Largo no había
 *  manera de traerse un producto nuevo ni de refrescar el ranking.
 */
export function SincronizarTopVendidos() {
  const qc = useQueryClient();
  const sincronizar = useSincronizarTopVendidos();
  // Cuántos hay esperando, para decirlo en el propio botón en vez de tener que
  // pulsarlo para averiguarlo.
  const faltan =
    useSources().data?.items.find((s) => s.slug === FUENTE_TOP_VENDIDOS)?.pendientes ?? 0;
  return (
    <div className="space-y-1 rounded-lg border border-border/60 p-2">
      <p className="text-[10px] leading-relaxed text-muted-foreground">
        Trae aquí los productos que ya vendieron, de diez en diez, con sus
        textos ya extraídos. Cada uno se queda siempre en su carpeta aunque
        luego venda más — moverlo perdería lo que ya llevas marcado. El orden
        por ventas se hace al pintar la lista.
      </p>
      <button
        type="button"
        disabled={sincronizar.isPending}
        onClick={() =>
          sincronizar.mutate(undefined, {
            onSuccess: (r) => {
              // El ranking lo leen todos los nichos: se refresca todo, no solo
              // la pantalla desde la que se pulsó.
              void qc.invalidateQueries();
              return r.añadidos
                ? toast.success(`${r.añadidos} producto(s) nuevos · ${r.total} en total`)
                : toast.info("Ya estaban todos los que han vendido");
            },
            onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
          })
        }
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/60 px-3 py-1.5 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/10 disabled:opacity-50"
      >
        {sincronizar.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Copiando fotos…
          </>
        ) : (
          <>
            <RefreshCw className="h-3.5 w-3.5" />
            {faltan > 0
              ? `Traer ${faltan} producto${faltan > 1 ? "s" : ""} nuevo${faltan > 1 ? "s" : ""}`
              : "Buscar productos vendidos nuevos"}
          </>
        )}
      </button>
    </div>
  );
}
