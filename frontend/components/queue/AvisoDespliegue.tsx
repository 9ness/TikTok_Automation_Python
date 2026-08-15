"use client";

import { Check, Loader2, Rocket } from "lucide-react";

import { useDeployStatus } from "@/lib/queries/deploy";

/** Qué está pasando con el despliegue, dentro de la Cola.
 *
 *  Aquí, y no en una pantalla de admin, porque la pregunta real es siempre
 *  sobre la cola: "¿ya está subido lo nuevo?" y "¿puedo mandar un vídeo o se
 *  va a cortar?". Las dos respuestas dependen de lo mismo.
 *
 *  Lo que hay que saber (y no era visible en ningún sitio):
 *
 *  - Un despliegue NO corta lo que está montándose: `deploy_safe.sh` espera a
 *    que no queden trabajos en curso antes de reiniciar.
 *  - Lo que se encole mientras tanto NO se pierde: la cola se guarda en disco
 *    y el contenedor nuevo la retoma.
 *
 *  Así que esto no bloquea nada: solo lo cuenta, para no tener que adivinar.
 */
export function AvisoDespliegue({ enCurso }: { enCurso: number }) {
  // El estado lo sirve el webhook del VPS; en local no responde y entonces
  // esto no se enseña (`isError`), que es lo correcto: no hay despliegue.
  const q = useDeployStatus({ live: true });
  const d = q.data;
  if (!d) return null;

  const desplegando = Boolean(d.deploy_in_progress);
  const pendientes = d.commits_behind ?? 0;

  // Todo al día: se dice CUÁNDO entró lo último, con hora y segundos. Sin
  // esto, "no sale nada" podía ser tanto "ya está subido" como "el aviso no
  // funciona", y había que preguntar para salir de dudas.
  if (!desplegando && pendientes === 0) {
    const cuando = d.last_deploy?.finished_at ?? d.last_deploy?.started_at ?? 0;
    if (!cuando) return null;
    return (
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-1.5 text-[11px] text-muted-foreground">
        <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
        <p className="truncate">
          Al día · último despliegue{" "}
          <span className="font-medium text-foreground">
            {new Date(cuando * 1000).toLocaleString("es-ES", {
              day: "2-digit",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </span>
        </p>
      </div>
    );
  }

  if (desplegando) {
    return (
      <div className="flex items-start gap-2 border-b border-sky-500/30 bg-sky-500/10 px-4 py-2 text-[11px] text-sky-400">
        <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" />
        <p className="leading-relaxed">
          <span className="font-semibold">Desplegando la versión nueva…</span>{" "}
          {enCurso > 0
            ? `Espera a que terminen los ${enCurso} trabajo(s) en curso: no se cortan.`
            : "Lo que mandes ahora se queda en la cola y arranca al terminar."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-[11px] text-amber-500">
      <Rocket className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <p className="leading-relaxed">
        <span className="font-semibold">
          Hay {pendientes} cambio(s) sin desplegar.
        </span>{" "}
        {enCurso > 0
          ? `El despliegue espera a que acaben los ${enCurso} trabajo(s) en curso.`
          : "Entrará en cuanto se lance el despliegue."}
      </p>
    </div>
  );
}
