"use client";

import {
  ClipboardCopy,
  Download,
  Loader2,
  ShoppingBag,
  Sparkles,
  Store,
} from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useEstadoDeUsuario } from "@/lib/hooks/useEstadoRecordado";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import {
  gorraFotoLimpiaUrl,
  gorraFotoUrl,
  useExtraerTextosGorras,
  useGorras,
  useGorrasCarpetas,
  useGorrasPrompts,
  useSetEstadoGorras,
} from "@/lib/queries/nichoGorras";
import type { Gorra } from "@/lib/types/nichoGorras";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

export default function NichoGorrasPage() {
  const carpetas = useGorrasCarpetas();
  const [carpeta, setCarpeta] = useEstadoDeUsuario("gorras:carpeta", "");
  const activa = carpeta || carpetas.data?.[0]?.slug || "";
  const gorras = useGorras(activa);
  const extraer = useExtraerTextosGorras();
  const prompts = useGorrasPrompts();

  const items = gorras.data?.items ?? [];
  const conTexto = items.filter((g) => g.titulo).length;
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const pendientesEscaparate = items.filter((g) => !g.en_escaparate).length;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <div className="relative h-28 w-full overflow-hidden rounded-xl sm:h-40">
        <Image
          src={portadaDe("nicho-gorras")}
          alt="Nicho Gorras"
          fill
          className="object-cover"
          priority
        />
        <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/80 to-transparent p-3">
          <div>
            <h1 className="text-lg font-bold text-white sm:text-xl">Nicho Gorras</h1>
            <p className="text-[11px] text-white/70">
              El vídeo se publica tal cual · módulo 11
            </p>
          </div>
        </div>
      </div>

      {/* Los 6 prompts del curso: uno de imagen y cinco de escenario. Se
          eligen aquí porque el vídeo se genera fuera y no vuelve a la app. */}
      <CollapsibleCard title="🧾 Prompts del curso" defaultOpen>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {(prompts.data ?? []).map((p) => (
            <button
              key={p.slug}
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(p.texto);
                toast.success(`${p.label} copiado`);
              }}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
            >
              <ClipboardCopy className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{p.label}</span>
            </button>
          ))}
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Con el de imagen creas la foto en Flow; los otros cinco son el mismo
          vídeo en distintos sitios. Elige el que quieras según la gorra.
        </p>
      </CollapsibleCard>

      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-orange-500" />
          <p className="flex-1 text-sm font-semibold">Gorras</p>
          <span className="text-[11px] text-muted-foreground">
            {conTexto}/{items.length} con textos
          </span>
        </div>

        <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-8">
          {(carpetas.data ?? []).map((c) => (
            <button
              key={c.slug}
              type="button"
              onClick={() => setCarpeta(c.slug)}
              className={`rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
                activa === c.slug
                  ? "border-orange-500 bg-orange-500/15 text-orange-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {c.slug}
            </button>
          ))}
        </div>

        <button
          type="button"
          disabled={extraer.isPending || !activa}
          onClick={() =>
            extraer.mutate(activa, {
              onSuccess: () => toast.success("Textos extraídos"),
              onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
            })
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-orange-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-orange-600 disabled:opacity-50"
        >
          {extraer.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Extrayendo…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5" /> Obtener textos ({conTexto}/{items.length})
            </>
          )}
        </button>

        {/* El ranking de vendidos es ÚNICO y global: dice qué tipo de producto
            buscar, así que se abre desde cualquier nicho. */}
        <button
          type="button"
          onClick={() => setVerVendidos(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-500 transition hover:bg-amber-500/20"
        >
          <ShoppingBag className="h-3.5 w-3.5" />
          Productos que vendieron
        </button>

        {verVendidos && (
          <VendidosModal conBuscador={false} onClose={() => setVerVendidos(false)} />
        )}

        {/* El escaparate es común a todos los nichos: si el producto ya se
            metió desde el POV BOF o desde otra carpeta, aquí sale hecho. */}
        {activa && items.length > 0 && (
          <button
            type="button"
            onClick={() => setVerEscaparate(true)}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-500 transition hover:bg-sky-500/20"
          >
            <Store className="h-3.5 w-3.5" />
            Meter en el escaparate
            <span
              className={`rounded-full px-1.5 text-[10px] font-bold ${
                pendientesEscaparate ? "bg-sky-500 text-black" : "bg-emerald-500 text-black"
              }`}
            >
              {`${items.length - pendientesEscaparate}/${items.length}`}
            </span>
          </button>
        )}

        {verEscaparate && activa && (
          <EscaparateModalGorras
            carpeta={activa}
            gorras={items}
            onClose={() => setVerEscaparate(false)}
          />
        )}

        {gorras.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando gorras…
          </div>
        )}
        {gorras.isError && (
          <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
            {(gorras.error as Error)?.message ?? "No se pudieron cargar las gorras."}
          </p>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {items.map((g) => (
            <GorraCard key={g.producto} carpeta={activa} gorra={g} />
          ))}
        </div>
      </section>
    </div>
  );
}

function GorraCard({ carpeta, gorra }: { carpeta: string; gorra: Gorra }) {
  const [verFoto, setVerFoto] = useState(false);
  const limpia = gorra.clean_photo_id ? gorraFotoUrl(gorra.clean_photo_id) : null;
  const ficha = gorra.titled_photo_id ? gorraFotoUrl(gorra.titled_photo_id) : null;

  return (
    <div className="space-y-2 rounded-lg border border-border/60 p-2">
      <div className="flex items-start gap-2">
        {limpia ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            className="shrink-0 rounded-md transition hover:ring-2 hover:ring-orange-500"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={limpia}
              alt={gorra.titulo || gorra.producto}
              loading="lazy"
              className="h-16 w-16 rounded-md object-cover"
            />
          </button>
        ) : (
          <div className="h-16 w-16 shrink-0 rounded-md bg-muted" />
        )}
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-1.5 text-xs font-semibold">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {gorra.producto}
            </span>
            <span className="truncate">{gorra.titulo || "sin título"}</span>
          </p>
          {gorra.titulo_tiktok_completo && (
            <p className="truncate text-[10px] text-muted-foreground">
              {gorra.titulo_tiktok_completo}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        <CopyChip label="📝 Título" text={gorra.titulo} siempre />
        <CopyChip label="🔎 Título TikTok" text={gorra.titulo_tiktok_completo} />
        <CopyChip label="🏪 Tienda" text={gorra.tienda} siempre />
        <CopyChip
          label="✍️ Caption"
          text={[gorra.caption, gorra.emojis].filter(Boolean).join(" ")}
        />
      </div>

      {gorra.foto_aviso && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          🖼️ {gorra.foto_aviso}
        </p>
      )}
      {gorra.caption_riesgo && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          ⚠️ {gorra.caption_riesgo}
        </p>
      )}

      <a
        href={gorraFotoLimpiaUrl(carpeta, gorra.producto)}
        className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
      >
        <Download className="h-3.5 w-3.5" /> Descargar la foto
      </a>

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={gorra.titulo || `Gorra ${gorra.producto}`}
        urlLimpia={limpia}
        urlTitulo={ficha}
        urlDescarga={gorraFotoLimpiaUrl(carpeta, gorra.producto)}
      />
    </div>
  );
}

/** El escaparate de las gorras escribe en el índice común (su propio
 *  endpoint), pero su Drive es otro: las fotos no se piden por
 *  `source/folder` sino por file ID, así que se le pasan las URLs a mano. */
function EscaparateModalGorras({
  carpeta,
  gorras,
  onClose,
}: {
  carpeta: string;
  gorras: Gorra[];
  onClose: () => void;
}) {
  const setEstado = useSetEstadoGorras(carpeta);
  return (
    <EscaparateModal
      source=""
      folder={carpeta}
      productos={gorras as unknown as ProductoItem[]}
      onClose={onClose}
      marcarEstado={(vars, opts) =>
        setEstado.mutate(
          { producto: vars.producto, en_escaparate: vars.en_escaparate },
          opts,
        )
      }
      // El endpoint de foto de este nicho no redimensiona: se ignora el ancho.
      fotoUrl={(p) => (p.clean_photo_id ? gorraFotoUrl(p.clean_photo_id) : null)}
      fotoFichaUrl={(p) => (p.titled_photo_id ? gorraFotoUrl(p.titled_photo_id) : null)}
      descargaUrl={(p) => gorraFotoLimpiaUrl(carpeta, p.producto)}
    />
  );
}
