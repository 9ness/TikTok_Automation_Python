"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  useRepararTopVendidos,
  useSincronizarTopVendidos,
  useSources,
} from "@/lib/queries/nichoPovBof";
import { FUENTE_TOP_VENDIDOS } from "@/lib/topVendidos";

/** Trae al Top vendidos los productos del ranking que aún no estén.
 *
 *  Vive aquí y no dentro de una página porque la carpeta "Top vendidos" es la
 *  MISMA para todos los nichos: se sincroniza una vez y la ven el POV BOF, el
 *  Largo y los demás. Estaba solo en el POV BOF y desde el Largo no había
 *  manera de traerse un producto nuevo ni de refrescar el ranking.
 */
export function SincronizarTopVendidos({ folder }: { folder?: string | null }) {
  const qc = useQueryClient();
  const sincronizar = useSincronizarTopVendidos();
  const reparar = useRepararTopVendidos();
  const [omitidos, setOmitidos] = useState<{ producto: string; motivo: string }[]>([]);
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
              setOmitidos(r.omitidos ?? []);
              return r.añadidos
                ? toast.success(`${r.añadidos} producto(s) nuevos · ${r.total} en total`)
                : toast.info(
                    r.omitidos?.length
                      ? "No pude traer ninguno; mira el aviso de abajo"
                      : "Ya estaban todos los que han vendido",
                  );
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

      {/* Una copia puede quedarse torcida: la foto de un producto con el texto
          de otro. Extraer los textos no arregla la foto, así que aquí se
          rehacen las dos cosas desde el original, que es la única fuente
          fiable. Va debajo y en gris porque es un remedio, no rutina. */}
      {folder ? (
        <button
          type="button"
          disabled={reparar.isPending}
          onClick={() => {
            if (
              !window.confirm(
                `Volver a copiar fotos y textos de "${folder}" desde el producto original. ` +
                  "Lo que hayas marcado (subido, escaparate, vídeos) NO se toca. ¿Sigo?",
              )
            )
              return;
            reparar.mutate(
              { folder },
              {
                onSuccess: (r) => {
                  toast.success(
                    `${r.fotos} foto(s) y ${r.textos} texto(s) traídos del original`,
                  );
                  for (const a of r.avisos ?? []) toast.warning(a);
                },
                onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
              },
            );
          }}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
        >
          {reparar.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Reparando…
            </>
          ) : (
            <>🛠️ Reparar “{folder}” desde el original</>
          )}
        </button>
      ) : null}

      {/* Los que se quedan fuera. Antes solo iban al log del servidor: el
          producto no aparecía nunca en la lista y el botón seguía diciendo que
          quedaba uno por traer. */}
      {omitidos.length > 0 && (
        <div className="space-y-0.5 rounded-md border border-amber-500/50 bg-amber-500/5 p-2">
          <p className="text-[10px] font-semibold text-amber-500">
            {omitidos.length} vendido(s) no se pudieron traer
          </p>
          {omitidos.map((o) => (
            <p key={o.producto} className="text-[10px] text-muted-foreground">
              · {o.producto}: {o.motivo}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
