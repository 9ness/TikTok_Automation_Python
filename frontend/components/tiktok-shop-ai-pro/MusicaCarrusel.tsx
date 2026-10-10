"use client";

import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import type { MusicaCarrusel as Musica } from "@/lib/queries/replicarCarrusel";

/** La canción del carrusel: la del viral para TikTok (se pone a mano al
 *  publicar) y la Mixkit sin copyright para Instagram/Facebook. */
export function MusicaCarrusel({ musica }: { musica?: Musica }) {
  const tk = musica?.tiktok;
  const meta = musica?.meta;
  if (!tk && !meta?.pista) return null;
  return (
    <div className="space-y-0.5 text-[10px] text-muted-foreground">
      {tk ? (
        <p className="flex flex-wrap items-center gap-1 break-words">
          🎵 TikTok:{" "}
          <a href={tk.enlace} target="_blank" rel="noreferrer" className="font-semibold text-sky-400 hover:underline">
            {tk.titulo || "sonido del viral"}
          </a>
          {tk.autor ? ` · ${tk.autor}` : ""}
          {tk.titulo ? <CopyChip label="Canción" text={tk.titulo} /> : null}
        </p>
      ) : null}
      {meta?.pista ? (
        <p className="break-words">
          📸 Meta (sin copyright):{" "}
          {meta.url ? (
            <a href={meta.url} target="_blank" rel="noreferrer" className="font-semibold text-sky-400 hover:underline">
              {meta.pista}
            </a>
          ) : (
            <b>{meta.pista}</b>
          )}
          {meta.autor ? ` · ${meta.autor}` : ""} · {meta.estilo}
        </p>
      ) : null}
    </div>
  );
}
