"use client";

import { useEffect, useRef } from "react";

import { useQueueStore } from "@/lib/stores/queueStore";
import type { ActiveJob } from "@/lib/types/queue";

/** Llama a `fn` cuando un job TERMINA, en cuanto lo dice la cola.
 *
 *  Hasta ahora la ficha del producto se enteraba solo por sondeo: la lista se
 *  repregunta cada 5 s MIENTRAS hay un montaje en curso. Funciona, pero llega
 *  tarde —y ni eso si la pestaña no está en primer plano, porque ahí el sondeo
 *  se pausa—, así que el vídeo terminado tardaba en aparecer y parecía que no
 *  se había guardado.
 *
 *  Los jobs ya terminados al montar NO disparan nada: si no, entrar en una
 *  pantalla recargaría todo por trabajos de ayer.
 */
export function useAlTerminarJob(fn: (job: ActiveJob) => void): void {
  const recientes = useQueueStore((s) => s.recent);
  // En una ref para que cambiar la función no vuelva a disparar el efecto.
  const cb = useRef(fn);
  cb.current = fn;
  const vistos = useRef<Set<string> | null>(null);

  useEffect(() => {
    if (vistos.current === null) {
      vistos.current = new Set(recientes.map((j) => j.job_id));
      return;
    }
    for (const job of recientes) {
      if (vistos.current.has(job.job_id)) continue;
      vistos.current.add(job.job_id);
      cb.current(job);
    }
  }, [recientes]);
}
