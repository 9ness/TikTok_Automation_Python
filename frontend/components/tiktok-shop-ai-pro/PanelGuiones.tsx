"use client";

import { Loader2, PenLine } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useSources } from "@/lib/queries/nichoPovBof";
import { useGuionesLote } from "@/lib/queries/povBofLargo";
import { useDrawerStore } from "@/lib/stores/drawerStore";

/** Los guiones de TODO un catálogo, de una tacada.
 *
 *  Va detrás de los textos y en el mismo sitio porque es el mismo gesto: saca
 *  los textos de todas las carpetas y luego los guiones de todas. El botón de
 *  la pantalla del POV BOF Largo sigue estando para hacer solo la carpeta que
 *  tengas abierta.
 *
 *  Es el ÚNICO panel de aquí que sirve a un solo nicho: el guion habla de ESE
 *  producto y solo lo usa el POV BOF Largo. Los textos, los hashtags y la copia
 *  valen para todos.
 */
export function PanelGuiones() {
  const sources = useSources();
  const lote = useGuionesLote();
  const openQueue = useDrawerStore((s) => s.openQueue);
  const [source, setSource] = useState("aleatorios_1");
  const [rehacer, setRehacer] = useState(false);

  function lanzar() {
    lote.mutate(
      { source, rehacer },
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
        <PenLine className="h-4 w-4 shrink-0 text-fuchsia-500" />
        <p className="text-sm font-semibold">Guiones de todo un catálogo</p>
        <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          POV BOF Largo
        </span>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Escribe el guion locutado de cada producto de TODAS las carpetas. Hazlo
        después de los textos: el guion se escribe a partir del título y la ficha,
        y las carpetas que no los tengan se saltan.
      </p>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {(sources.data?.items ?? []).map((s) => (
          <button
            key={s.slug}
            type="button"
            onClick={() => setSource(s.slug)}
            className={`break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
              source === s.slug
                ? "border-fuchsia-500 bg-fuchsia-500/15 text-fuchsia-400"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Rehacer cuesta una llamada de IA por producto para reescribir lo que ya
          está. Lo normal es dejarlo apagado: el trabajo ya rehace solo los que
          cambiaron de modo de precio. */}
      <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
        <input
          type="checkbox"
          className="h-4 w-4 accent-fuchsia-500"
          checked={rehacer}
          onChange={(e) => setRehacer(e.target.checked)}
        />
        Reescribir también los guiones que ya están
      </label>

      <button
        type="button"
        disabled={lote.isPending}
        onClick={lanzar}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-fuchsia-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-fuchsia-600 disabled:opacity-50"
      >
        {lote.isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Encolando…
          </>
        ) : (
          <>
            <PenLine className="h-4 w-4" /> Escribir los guiones que falten
          </>
        )}
      </button>
    </section>
  );
}
