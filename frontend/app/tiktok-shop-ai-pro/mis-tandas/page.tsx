"use client";

import { useState } from "react";
import { ListChecks } from "lucide-react";

import { CarruselesReplicados } from "@/components/tiktok-shop-ai-pro/CarruselesReplicados";
import { GuiaIA } from "@/components/tiktok-shop-ai-pro/GuiaIA";
import { MisTandas } from "@/components/tiktok-shop-ai-pro/MisTandas";
import { useMisTandas, useTandasFotos } from "@/lib/queries/misTandas";

/** «Mis tandas»: lo montado en TODOS tus nichos, para publicarlo de diez en
 *  diez. No es un nicho: solo junta y marca (ver `src/mis_tandas/`). */
export default function MisTandasPage() {
  const [pestana, setPestana] = useState<"videos" | "fotos">("videos");
  // Cada pestaña lleva su contador: los vídeos y los carruseles no se mezclan.
  const videos = useMisTandas(false).data;
  const fotos = useTandasFotos(false).data;
  const pestanas = [
    { id: "videos" as const, label: "🎬 Vídeos", cuenta: videos ? `${videos.subidos}/${videos.total}` : "" },
    { id: "fotos" as const, label: "🖼️ Fotos", cuenta: fotos ? `${fotos.subidos}/${fotos.total}` : "" },
  ];
  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <ListChecks className="h-5 w-5 shrink-0 text-violet-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Mis tandas</h1>
            <p className="text-[11px] text-muted-foreground">
              Tus vídeos y carruseles listos para subir, de diez en diez y con el día que toca
            </p>
          </div>
          <GuiaIA guia="mis-tandas" />
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Junta lo que ya está montado en POV BOF, POV BOF Largo y Moda Mujer · Multimodo. Aquí
          no se monta nada: cuando un vídeo se termina en su nicho (lo haga una persona o un
          agente), aparece solo al final de la cola. Subido, sin stock y rehacer se guardan en
          el propio nicho, así que su pantalla lo ve igual.
        </p>
      </header>
      <div className="grid grid-cols-2 gap-1.5" role="tablist">
        {pestanas.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            aria-selected={pestana === p.id}
            onClick={() => setPestana(p.id)}
            className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold sm:text-sm ${
              pestana === p.id
                ? "border-violet-500 bg-violet-500/10 text-violet-400"
                : "border-border/60 text-muted-foreground hover:text-foreground"
            }`}
          >
            {p.label}
            {p.cuenta ? (
              <span className="rounded-full bg-muted px-1.5 py-px text-[9px] font-semibold text-muted-foreground">
                {p.cuenta} subidos
              </span>
            ) : null}
          </button>
        ))}
      </div>
      {pestana === "videos" ? <MisTandas /> : <CarruselesReplicados />}
    </div>
  );
}
