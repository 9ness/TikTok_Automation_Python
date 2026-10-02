"use client";

import { ListChecks } from "lucide-react";

import { GuiaIA } from "@/components/tiktok-shop-ai-pro/GuiaIA";
import { MisTandas } from "@/components/tiktok-shop-ai-pro/MisTandas";

/** «Mis tandas»: lo montado en TODOS tus nichos, para publicarlo de diez en
 *  diez. No es un nicho: solo junta y marca (ver `src/mis_tandas/`). */
export default function MisTandasPage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <ListChecks className="h-5 w-5 shrink-0 text-violet-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Mis tandas</h1>
            <p className="text-[11px] text-muted-foreground">
              Tus vídeos listos para subir, de diez en diez y con el día que toca
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
      <MisTandas />
    </div>
  );
}
