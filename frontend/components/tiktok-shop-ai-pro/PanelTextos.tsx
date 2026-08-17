"use client";

import { Loader2, Type } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useSources, useTextosLote } from "@/lib/queries/nichoPovBof";
import { useDrawerStore } from "@/lib/stores/drawerStore";

/** Extraer los textos de TODAS las carpetas de un catálogo de una tacada.
 *
 *  El botón de cada nicho hace UNA carpeta, y eso obliga a ir entrando carpeta
 *  por carpeta antes de poder trabajar. En Carruseles se nota más que en
 *  ninguno: el filtro de categoría LEE los títulos, así que sin textos no se
 *  sabe qué productos valen.
 *
 *  Está en Configuración y no dentro de un nicho porque los textos son del
 *  catálogo COMPARTIDO: hacerlos una vez sirve para POV BOF, POV BOF Largo,
 *  Creativos Pro y Carruseles a la vez.
 */
export function PanelTextos() {
  const sources = useSources();
  const lote = useTextosLote();
  const openQueue = useDrawerStore((s) => s.openQueue);
  const [source, setSource] = useState("aleatorios_1");
  const [rehacer, setRehacer] = useState(false);
  const [unoAUno, setUnoAUno] = useState(false);

  function lanzar() {
    lote.mutate(
      { source, rehacer, unoAUno },
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
        <Type className="h-4 w-4 shrink-0 text-violet-500" />
        <p className="text-sm font-semibold">Textos de todo un catálogo</p>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Lee las fichas de TODAS las carpetas del catálogo y guarda título,
        tienda, caption y precio de cada producto. Sirve para todos los nichos a
        la vez —el catálogo es el mismo— y va por la cola, porque es alrededor
        de un minuto de IA por carpeta.
      </p>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {(sources.data?.items ?? []).map((s) => (
          <button
            key={s.slug}
            type="button"
            onClick={() => setSource(s.slug)}
            className={`truncate rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
              source === s.slug
                ? "border-violet-500 bg-violet-500/15 text-violet-400"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Rehacer cuesta una llamada de IA por carpeta para reescribir lo que ya
          está, así que va apagado y con el aviso delante. */}
      <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
        <input
          type="checkbox"
          className="h-4 w-4 accent-violet-500"
          checked={rehacer}
          onChange={(e) => setRehacer(e.target.checked)}
        />
        Rehacer también las carpetas que ya tienen textos
      </label>

      {/* Una captura por llamada: es la única forma de que el modelo no pueda
          cruzar los títulos entre productos de la misma carpeta. Tarda más y
          cuesta una llamada por producto, pero deja el catálogo fiable. */}
      <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
        <input
          type="checkbox"
          className="h-4 w-4 accent-violet-500"
          checked={unoAUno}
          onChange={(e) => setUnoAUno(e.target.checked)}
        />
        Leer las capturas de una en una (más lento, imposible que se crucen)
      </label>

      <button
        type="button"
        disabled={lote.isPending}
        onClick={lanzar}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
      >
        {lote.isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Encolando…
          </>
        ) : (
          <>
            <Type className="h-4 w-4" /> Sacar los textos que falten
          </>
        )}
      </button>
    </section>
  );
}
