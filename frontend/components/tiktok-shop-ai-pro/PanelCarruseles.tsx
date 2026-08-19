"use client";

import { GalleryHorizontalEnd, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { usePrepararCatalogo } from "@/lib/queries/nichoCarruseles";
import { useSources } from "@/lib/queries/nichoPovBof";
import { useDrawerStore } from "@/lib/stores/drawerStore";

/** Filtrar y escribir los mensajes de TODO un catálogo para Carruseles.
 *
 *  Los dos primeros botones de la pantalla del nicho, pero para las 35 carpetas
 *  de golpe: de una en una son 70 pulsaciones. Las dos cosas son llamadas de
 *  TEXTO (leen los títulos ya extraídos, sin imágenes), así que salen baratas.
 *
 *  Va después de los textos: sin título no hay nada que clasificar.
 */
export function PanelCarruseles() {
  const sources = useSources();
  const preparar = usePrepararCatalogo();
  const openQueue = useDrawerStore((s) => s.openQueue);
  const [source, setSource] = useState("aleatorios_1");
  const [soloFiltrar, setSoloFiltrar] = useState(false);
  const [soloMensajes, setSoloMensajes] = useState(false);
  const [rehacer, setRehacer] = useState(false);

  function lanzar() {
    preparar.mutate(
      { source, solo_filtrar: soloFiltrar, solo_mensajes: soloMensajes, rehacer },
      {
        onSuccess: (r) => {
          toast.success(`${r.title} en la cola`);
          openQueue();
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-center gap-2">
        <GalleryHorizontalEnd className="h-4 w-4 shrink-0 text-cyan-500" />
        <p className="text-sm font-semibold">Preparar un catálogo entero</p>
        <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          Carruseles
        </span>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Mira TODAS las carpetas y decide qué productos valen para carrusel (y en
        qué sitio va su chica), y luego escribe los dos mensajes de cada uno.
        Hazlo después de los textos: las carpetas que no los tengan se saltan.
      </p>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {(sources.data?.items ?? []).map((s) => (
          <button
            key={s.slug}
            type="button"
            onClick={() => setSource(s.slug)}
            className={`break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
              source === s.slug
                ? "border-cyan-500 bg-cyan-500/15 text-cyan-500"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Para ver primero cuántos productos pasan el filtro sin gastar las
          llamadas de los mensajes. */}
      <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
        <input
          type="checkbox"
          className="h-4 w-4 accent-cyan-500"
          checked={soloFiltrar}
          onChange={(e) => setSoloFiltrar(e.target.checked)}
        />
        Solo filtrar (sin escribir los mensajes todavía)
      </label>

      {/* Para cuando cambia el prompt de los mensajes (por ejemplo, al quitar
          las promesas de salud): reescribe los dos mensajes de todos los aptos
          sin volver a pasar el filtro, que podría cambiarle la categoría a un
          producto dudoso y dejar su chica en otro sitio. */}
      <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
        <input
          type="checkbox"
          className="h-4 w-4 accent-cyan-500"
          checked={soloMensajes}
          onChange={(e) => setSoloMensajes(e.target.checked)}
        />
        Solo reescribir los mensajes (sin volver a filtrar)
      </label>

      {/* Hace falta cuando los TEXTOS cambian: la categoría y los mensajes se
          calcularon con los títulos de antes y hay que rehacerlos. Sin esto,
          el trabajo se salta todo lo que ya estuviera hecho. */}
      <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
        <input
          type="checkbox"
          className="h-4 w-4 accent-cyan-500"
          checked={rehacer}
          onChange={(e) => setRehacer(e.target.checked)}
        />
        Rehacer lo que ya estaba (hazlo si has vuelto a sacar los textos)
      </label>

      <button
        type="button"
        disabled={preparar.isPending}
        onClick={lanzar}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-cyan-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-cyan-600 disabled:opacity-50"
      >
        {preparar.isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Encolando…
          </>
        ) : (
          <>
            <GalleryHorizontalEnd className="h-4 w-4" />
            {soloFiltrar
              ? "Filtrar todo el catálogo"
              : soloMensajes
                ? "Reescribir los mensajes"
                : "Filtrar y escribir los mensajes"}
          </>
        )}
      </button>
    </section>
  );
}
