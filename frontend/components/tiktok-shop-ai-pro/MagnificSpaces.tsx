"use client";

import { useState } from "react";
import { ChevronDown, ExternalLink, Wand2 } from "lucide-react";

/** Los flows de Magnific (spaces) que ya están montados.
 *
 *  Magnific es la ALTERNATIVA a copiar los prompts a mano: el space ya lleva
 *  el prompt dentro, así que o se entra ahí o se copian los prompts. Por eso
 *  en la UI van con una "o" entre medias.
 *
 *  Cada nicho enseña solo los suyos: el POV BOF Largo monta DOS clips por foto
 *  tanto en normal como a plazos, así que le vale únicamente el de plazos.
 */
export type MagnificSpaceId =
  | "foto_limpia_normal"
  | "foto_limpia_plazos"
  | "foto_ia"
  | "foto_ia_2"
  | "carrusel";

/** `fila`: los spaces que la comparten se pintan en la misma línea (los de foto
 *  con IA son dos para repartir las fotos y que no se sature un space). */
const SPACES: Record<
  MagnificSpaceId,
  { label: string; hint: string; url: string; fila?: string }
> = {
  foto_limpia_normal: {
    label: "Foto limpia → vídeo (pago normal)",
    hint: "1 clip por foto",
    url: "https://www.magnific.com/app/spaces/a27c380f-a674-49e7-9434-29fb441f4a08?page=1",
  },
  foto_limpia_plazos: {
    label: "Foto limpia → vídeo (pago a plazos)",
    hint: "2 clips por foto",
    url: "https://www.magnific.com/app/spaces/a27da99c-562d-4289-bef5-7e0f591d4dc6?page=1",
  },
  foto_ia: {
    label: "Foto con IA → vídeo",
    hint: "cuando ya tienes la foto generada con IA, no la limpia",
    url: "https://www.magnific.com/app/spaces/a271e815-cff4-46b6-8597-16153024b453",
    fila: "foto_ia",
  },
  foto_ia_2: {
    label: "Foto con IA → vídeo (2)",
    hint: "mismo flow, otro space para repartir las fotos",
    url: "https://www.magnific.com/app/spaces/a285a2e7-03d4-426c-9053-4ef927673519?page=1",
    fila: "foto_ia",
  },
  carrusel: {
    label: "Crear carrusel de 1 foto",
    hint: "una sola foto de partida",
    url: "https://www.magnific.com/app/spaces/a279e062-6d19-44bf-bb6c-2775ab35d74c",
  },
};

export function MagnificSpaces({ spaces }: { spaces: MagnificSpaceId[] }) {
  const [abierto, setAbierto] = useState(false);
  if (!spaces.length) return null;

  // Agrupa en filas: los que comparten `fila` van juntos, el resto va solo.
  const filas: MagnificSpaceId[][] = [];
  for (const id of spaces) {
    const fila = SPACES[id].fila;
    const ultima = filas[filas.length - 1];
    const primeroDeUltima = ultima?.[0];
    if (fila && ultima && primeroDeUltima && SPACES[primeroDeUltima].fila === fila)
      ultima.push(id);
    else filas.push([id]);
  }

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-fuchsia-500/50 bg-fuchsia-500/10 px-3 py-2 text-xs font-semibold text-fuchsia-400 transition hover:bg-fuchsia-500/20"
      >
        <Wand2 className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">Magnific ({spaces.length})</span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition ${abierto ? "rotate-180" : ""}`}
        />
      </button>

      {abierto && (
        <div className="space-y-1.5 rounded-lg border border-border/60 p-1.5">
          {filas.map((fila) => (
            <div
              key={fila.join("+")}
              className={fila.length > 1 ? "grid grid-cols-2 gap-1.5" : undefined}
            >
              {fila.map((id) => {
                const s = SPACES[id];
                return (
                  <a
                    key={id}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-2 transition hover:border-fuchsia-500/50 hover:bg-fuchsia-500/5"
                  >
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-fuchsia-400" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11px] font-semibold">{s.label}</span>
                      <span className="block truncate text-[10px] text-muted-foreground">
                        {s.hint}
                      </span>
                    </span>
                  </a>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
