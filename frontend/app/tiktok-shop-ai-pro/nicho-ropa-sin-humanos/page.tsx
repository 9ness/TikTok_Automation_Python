"use client";

import {
  Check,
  ClipboardCopy,
  Download,
  Loader2,
  Sparkles,
  Store,
  Upload,
  ShoppingBag,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";
import {
  buildFotoLimpiaRopaUrl,
  buildFotoRopaUrl,
  buildVideoRopaUrl,
  useCarpetasRopa,
  useExtraerTextosRopa,
  usePrendas,
  usePromptsRopa,
  useSetEstadoRopa,
  useSubirVideoRopa,
  type PrendaItem,
} from "@/lib/queries/nichoRopa";
import { VideoModal } from "@/components/ui/video-modal";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

export default function NichoRopaPage() {
  // Las carpetas de mujer son las del nicho CON personas, pero la misma prenda
  // vale aquí colgada en percha: lo que cambia es el prompt, no la foto.
  const [carpeta, setCarpeta] = useEstadoRecordado("ropa:carpeta", "camisetas");
  const carpetas = useCarpetasRopa();
  const prendas = usePrendas(carpeta);
  const prompts = usePromptsRopa();
  const extraer = useExtraerTextosRopa();

  const items = prendas.data?.items ?? [];
  const conTexto = items.filter((p) => p.titulo).length;
  const conVideo = items.filter((p) => p.video_path).length;
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const pendientesEscaparate = items.filter((p) => !p.en_escaparate).length;

  function copiar(label: string, texto?: string) {
    if (!texto) return;
    navigator.clipboard.writeText(texto);
    toast.success(`${label} copiado`);
  }

  async function descargarFotos() {
    const conFoto = items.filter((p) => p.clean_photo_id);
    if (!conFoto.length) return;
    // Una a una con retardo: el navegador móvil cancela las simultáneas.
    for (const [i, p] of conFoto.entries()) {
      const a = document.createElement("a");
      a.href = buildFotoLimpiaRopaUrl(p.producto, carpeta);
      a.download = `ropa_${p.producto}.jpg`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < conFoto.length - 1) await new Promise((r) => setTimeout(r, 600));
    }
    toast.success(`${conFoto.length} foto(s) descargadas`);
  }

  return (
    <div className="container mx-auto space-y-3 p-3 sm:space-y-4 sm:p-6 md:p-10">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={portadaDe("nicho-ropa-sin-humanos")}
        alt="Creación de Nicho Ropa Sin Humanos"
        className="h-auto w-full rounded-xl border border-border/60"
      />

      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <div className="grid grid-cols-2 gap-2">
          {(carpetas.data?.items ?? []).map((c) => (
            <button
              key={c.slug}
              type="button"
              onClick={() => setCarpeta(c.slug)}
              className={`truncate rounded-lg border px-3 py-2 text-xs transition ${
                carpeta === c.slug
                  ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <p className="text-xs font-medium sm:text-sm">
          {items.length} prenda(s) · {conTexto} con texto · {conVideo} con vídeo
        </p>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Este nicho NO lleva texto en pantalla: ni gancho, ni título, ni CTA. Y
          el vídeo sale <strong>mudo</strong> — la música se la pones tú al
          publicar.
        </p>
      </section>

      {/* Paso 1 — textos */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <p className="text-sm font-semibold">1 · Textos</p>
        <button
          type="button"
          disabled={extraer.isPending || items.length === 0}
          onClick={() =>
            extraer.mutate(carpeta, {
              onSuccess: () => toast.success("Textos extraídos"),
              onError: (e) =>
                toast.error(e instanceof ApiError ? e.message : String(e)),
            })
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-700 disabled:opacity-50"
        >
          {extraer.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Leyendo capturas…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5" /> Obtener textos ({conTexto}/
              {items.length})
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
        {items.length > 0 && (
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
              {pendientesEscaparate ? `${pendientesEscaparate} sin meter` : "al día"}
            </span>
          </button>
        )}
      </section>

      {verEscaparate && (
        <EscaparateModalRopa
          carpeta={carpeta}
          prendas={items}
          onClose={() => setVerEscaparate(false)}
        />
      )}

      {/* Paso 2 — prompts */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <p className="text-sm font-semibold">2 · Generar fuera</p>
        <p className="text-[11px] text-muted-foreground">
          Copia el prompt y la foto de la prenda al generador.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <button
            type="button"
            onClick={() => copiar("Prompt de imagen", prompts.data?.imagen)}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
          >
            <ClipboardCopy className="h-3.5 w-3.5" /> Prompt imagen
          </button>
          {/* Las dos versiones del prompt de vídeo. La única diferencia es la
              frase de la mano acariciando la ropa. */}
          <button
            type="button"
            onClick={() => copiar("Prompt con manos", prompts.data?.video_con_manos)}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
          >
            <ClipboardCopy className="h-3.5 w-3.5" /> Vídeo · con manos
          </button>
          <button
            type="button"
            onClick={() => copiar("Prompt sin manos", prompts.data?.video_sin_manos)}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
          >
            <ClipboardCopy className="h-3.5 w-3.5" /> Vídeo · sin manos
          </button>
          {/* Otro escenario distinto, no una variante del de alfombra. */}
          <button
            type="button"
            onClick={() => copiar("Prompt percha", prompts.data?.video_percha)}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
          >
            <ClipboardCopy className="h-3.5 w-3.5" /> Vídeo · percha
          </button>
        </div>
        <button
          type="button"
          onClick={descargarFotos}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground"
        >
          <Download className="h-3.5 w-3.5" /> Descargar todas las fotos
        </button>
      </section>

      {prendas.isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Leyendo la carpeta de Drive…
        </div>
      )}
      {prendas.isError && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
          {(prendas.error as Error)?.message ?? "No se pudo leer la carpeta."}
        </p>
      )}

      <section className="space-y-2">
        <p className="text-sm font-semibold">3 · Prendas</p>
        {items.map((p) => (
          <PrendaCard
            key={p.producto}
            prenda={p}
            carpeta={carpeta}
            onCopiar={copiar}
          />
        ))}
      </section>
    </div>
  );
}

function PrendaCard({
  prenda,
  carpeta,
  onCopiar,
}: {
  prenda: PrendaItem;
  carpeta: string;
  onCopiar: (label: string, texto?: string) => void;
}) {
  const subir = useSubirVideoRopa();
  // Vacío = mudo, que es el modo por defecto de este nicho.
  const [sexo, setSexo] = useState("");
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);

  function elegirArchivo(file: File | null) {
    if (!file) return;
    subir.mutate(
      { producto: prenda.producto, carpeta, file, sexo },
      {
        onSuccess: (r) => toast.success(r.message),
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  const caption = prenda.caption
    ? `${prenda.emojis ? `${prenda.emojis} ` : ""}${prenda.caption}`
    : "";

  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex gap-2.5">
        {prenda.clean_photo_id ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            title="Ver la foto limpia y la captura con título"
            className="shrink-0"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={buildFotoRopaUrl(prenda.clean_photo_id)}
              alt={`Prenda ${prenda.producto}`}
              loading="lazy"
              className="h-20 w-20 rounded-lg object-cover transition hover:opacity-80"
            />
          </button>
        ) : (
          <div className="h-20 w-20 shrink-0 rounded-lg bg-muted" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold">
            {prenda.producto}
            {prenda.video_path && (
              <span className="ml-1.5 text-[10px] font-normal text-emerald-500">
                <Check className="inline h-3 w-3" /> vídeo listo
              </span>
            )}
            {prenda.montando && (
              <span className="ml-1.5 text-[10px] font-normal text-amber-500">
                montando…
              </span>
            )}
          </p>
          <p className="line-clamp-2 whitespace-pre-line text-[11px] leading-snug">
            {prenda.titulo || "— sin textos todavía —"}
          </p>
          {prenda.tienda && (
            <p className="truncate text-[10px] text-muted-foreground">{prenda.tienda}</p>
          )}
        </div>
      </div>

      {prenda.foto_aviso && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-500">
          {prenda.foto_aviso}
        </p>
      )}
      {prenda.caption_riesgo && (
        <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-500">
          Caption arriesgado: {prenda.caption_riesgo}
        </p>
      )}

      {/* Los mismos tres botones que en el Nicho POV BOF: el caption para
          publicar, y el título de TikTok y la tienda para poder BUSCAR el
          producto en el Centro de Afiliados. */}
      <div className="flex flex-wrap gap-1">
        <CopyChip label="✍️ Caption" text={caption} siempre />
        <CopyChip label="🔎 Título TikTok" text={prenda.titulo_tiktok_completo} siempre />
        <CopyChip label="🏪 Tienda" text={prenda.tienda} siempre />
      </div>
      {caption && (
        <p className="rounded-lg border border-border/60 px-2.5 py-1.5 text-[11px] text-muted-foreground">
          {caption}
        </p>
      )}

      <div className="grid grid-cols-3 gap-1">
        {/* Mudo primero: es lo que el operador quiere casi siempre. */}
        {[
          { v: "", label: "Mudo" },
          { v: "hombre", label: "Voz H" },
          { v: "mujer", label: "Voz M" },
        ].map((op) => (
          <button
            key={op.v || "mudo"}
            type="button"
            onClick={() => setSexo(op.v)}
            className={`rounded-md border px-2 py-1 text-[10px] transition ${
              sexo === op.v
                ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-500"
                : "border-border/60 text-muted-foreground hover:border-foreground/30"
            }`}
          >
            {op.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30">
          {subir.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5" />
          )}
          Subir vídeo
          <input
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => elegirArchivo(e.target.files?.[0] ?? null)}
          />
        </label>
        <button
          type="button"
          disabled={!prenda.video_path}
          onClick={() => setVerVideo(true)}
          className="rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30 disabled:opacity-40"
        >
          Ver / descargar
        </button>
      </div>

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={`Prenda ${prenda.producto}`}
        urlLimpia={
          prenda.clean_photo_id ? buildFotoRopaUrl(prenda.clean_photo_id) : null
        }
        urlTitulo={
          prenda.titled_photo_id ? buildFotoRopaUrl(prenda.titled_photo_id) : null
        }
        urlDescarga={
          prenda.clean_photo_id
            ? buildFotoLimpiaRopaUrl(prenda.producto, carpeta)
            : null
        }
      />

      <VideoModal
        open={verVideo}
        onOpenChange={setVerVideo}
        title={`Prenda ${prenda.producto}`}
        filename={`ropa_${prenda.producto}.mp4`}
        videoUrl={
          prenda.video_path
            ? buildVideoRopaUrl(prenda.producto, carpeta, prenda.video_listo_at)
            : null
        }
        downloadUrl={
          prenda.video_path
            ? buildVideoRopaUrl(prenda.producto, carpeta, prenda.video_listo_at, true)
            : null
        }
        localPath={prenda.video_path}
      />
    </div>
  );
}

/** El escaparate de la ropa escribe en el índice común (su propio endpoint),
 *  pero su Drive es otro: las fotos no se piden por `source/folder` sino por
 *  file ID, así que se le pasan las URLs a mano. Tampoco hay `source`: es UNA
 *  carpeta compartida por enlace. */
function EscaparateModalRopa({
  carpeta,
  prendas,
  onClose,
}: {
  carpeta: string;
  prendas: PrendaItem[];
  onClose: () => void;
}) {
  const setEstado = useSetEstadoRopa(carpeta);
  return (
    <EscaparateModal
      source=""
      folder={carpeta}
      productos={prendas as unknown as ProductoItem[]}
      onClose={onClose}
      marcarEstado={(vars, opts) =>
        setEstado.mutate(
          { producto: vars.producto, en_escaparate: vars.en_escaparate },
          opts,
        )
      }
      // El endpoint de foto de este nicho no redimensiona: se ignora el ancho.
      fotoUrl={(p) => (p.clean_photo_id ? buildFotoRopaUrl(p.clean_photo_id) : null)}
      fotoFichaUrl={(p) => (p.titled_photo_id ? buildFotoRopaUrl(p.titled_photo_id) : null)}
      descargaUrl={(p) => buildFotoLimpiaRopaUrl(p.producto, carpeta)}
    />
  );
}
