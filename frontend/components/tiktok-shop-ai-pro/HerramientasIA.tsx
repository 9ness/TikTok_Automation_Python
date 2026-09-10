"use client";

import { ExternalLink } from "lucide-react";

/** Dónde se generan hoy las imágenes y los vídeos.
 *
 *  Sustituye a los spaces de Magnific, que se dejaron de pagar (sep 2026). La
 *  diferencia de fondo: Magnific llevaba el prompt DENTRO del space, así que
 *  era "o entras ahí o copias el prompt". Estas dos no: el prompt se copia
 *  igual y la herramienta solo es el sitio donde pegarlo, así que van juntas
 *  con los botones de copiar y no como alternativa.
 *
 *  Qué se usa dónde, según el nicho:
 *    - foto: siempre Google Flow (Nano Banana 2, 9:16).
 *    - vídeo del POV BOF y del Largo: GenAI Pro.
 *    - vídeo de los nichos con voz dentro del clip (ropa hombre/mujer, UGC):
 *      Google Flow, que es lo que sabe locutar.
 */
export const FLOW_URL = "https://flow.google.com/";
export const GENAIPRO_URL = "https://genaipro.io/video-image-ai";

/** Las opciones que hay que dejar puestas en GenAI Pro. Se escriben aquí y no
 *  en cada pantalla porque son las mismas para todos los vídeos. */
export const GENAIPRO_AJUSTES = "Frames · start + end frame · Portrait 9:16 · 1 vídeo · Original";

export function BotonHerramienta({
  url,
  label,
  hint,
}: {
  url: string;
  label: string;
  hint?: string;
}) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-card px-3 py-2 text-xs transition hover:border-violet-500/60"
    >
      <span className="min-w-0">
        <span className="font-semibold">{label}</span>
        {hint && (
          <span className="block truncate text-[10px] text-muted-foreground">
            {hint}
          </span>
        )}
      </span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
    </a>
  );
}

/** Los dos accesos, o solo el de Flow en los nichos que no usan GenAI Pro. */
export function HerramientasIA({ video = "genaipro" }: { video?: "genaipro" | "flow" }) {
  return (
    <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
      <BotonHerramienta
        url={FLOW_URL}
        label="🖼️ Google Flow"
        hint="la foto · Nano Banana 2 · 9:16"
      />
      {video === "genaipro" ? (
        <BotonHerramienta
          url={GENAIPRO_URL}
          label="🎬 GenAI Pro"
          hint={GENAIPRO_AJUSTES}
        />
      ) : (
        <BotonHerramienta
          url={FLOW_URL}
          label="🎬 Google Flow"
          hint="el vídeo, que aquí lleva la voz dentro"
        />
      )}
    </div>
  );
}
