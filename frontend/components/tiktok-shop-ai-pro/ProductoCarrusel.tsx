"use client";

import { ExternalLink } from "lucide-react";

import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { buildCleanPhotoDownloadUrl } from "@/lib/queries/nichoPovBof";

/** El producto de un carrusel de un vistazo: miniatura de su foto limpia +
 *  «Ver producto» (la ficha de TikTok Shop) o, si el catálogo no la tiene,
 *  el título para copiarlo y buscarlo en TikTok. */
export function ProductoCarrusel({
  source,
  folder,
  producto,
  titulo,
  productUrl,
}: {
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  productUrl?: string;
}) {
  const limpio = titulo.replace(/\s+/g, " ").trim();
  return (
    <div className="flex min-w-0 items-center gap-2">
      {source ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={buildCleanPhotoDownloadUrl(source, folder, producto, "limpia", 160)}
          alt={limpio}
          loading="lazy"
          className="h-12 w-12 shrink-0 rounded-md border border-border/60 bg-muted object-cover"
          onError={(e) => (e.currentTarget.style.visibility = "hidden")}
        />
      ) : null}
      <div className="flex min-w-0 flex-wrap items-center gap-1">
        {productUrl ? (
          <a
            href={productUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 rounded border border-sky-500/50 px-2 py-1 text-[10px] font-semibold text-sky-400 hover:bg-sky-500/10"
          >
            <ExternalLink className="h-3 w-3" /> Ver producto
          </a>
        ) : null}
        <CopyChip label="Título" text={limpio} />
      </div>
    </div>
  );
}
