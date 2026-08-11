"use client";

import {
  Check,
  Clapperboard,
  Download,
  ShoppingBag,
  Image as ImageIcon,
  Loader2,
  Sparkles,
  Store,
  Upload,
} from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { VideoModal } from "@/components/ui/video-modal";
import { portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import {
  cineFotoLimpiaUrl,
  cineFotoUrl,
  cineVideoUrl,
  useCineExtraerTextos,
  useCineFolders,
  useCineMarcarCarpeta,
  useCineProductos,
  useCinePrompts,
  useCineSources,
  useCineSubirClip,
  useSetEstadoCine,
  ANCHO_VISOR,
} from "@/lib/queries/nichoBofCine";
import type { CineProducto } from "@/lib/types/nichoBofCine";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

function copiar(label: string, texto: string) {
  navigator.clipboard.writeText(texto);
  toast.success(`${label} copiado`);
}

export default function NichoBofCinePage() {
  const sources = useCineSources();
  const [source, setSource] = useEstadoRecordado("cine:fuente", "aleatorios_1");
  const [picked, setPicked] = useEstadoRecordado<string | null>("cine:carpeta", null);
  const folders = useCineFolders(source);
  const folder = picked ?? folders.data?.current ?? null;
  const productos = useCineProductos(source, folder);
  const extraer = useCineExtraerTextos();
  const marcar = useCineMarcarCarpeta();
  const prompts = useCinePrompts();

  const items = productos.data?.items ?? [];
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const pendientesEscaparate = items.filter((p) => !p.en_escaparate).length;
  const conTexto = items.filter((p) => p.titulo).length;
  const listos = items.filter((p) => p.clip1 && p.clip2).length;
  const hecha = folders.data?.items.find((f) => f.name === folder)?.completed ?? false;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <div className="relative h-28 w-full overflow-hidden rounded-xl sm:h-40">
        <Image
          src={portadaDe("nicho-bof-cinematografico")}
          alt="Nicho BOF Cinematográfico"
          fill
          className="object-cover"
          priority
        />
        <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/80 to-transparent p-3">
          <div>
            <h1 className="text-lg font-bold text-white sm:text-xl">
              Nicho BOF Cinematográfico
            </h1>
            <p className="text-[11px] text-white/70">
              Dos clips de 5s con paneo de cámara · módulo 10
            </p>
          </div>
        </div>
      </div>

      {/* Fuente y carpeta. El progreso es de ESTE nicho: la misma carpeta
          puede estar hecha en POV BOF y pendiente aquí. */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <div className="grid grid-cols-2 gap-1.5">
          {(sources.data ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => {
                setSource(s.slug);
                setPicked(null);
              }}
              className={`truncate rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
                source === s.slug
                  ? "border-indigo-500 bg-indigo-500/15 text-indigo-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <select
            value={folder ?? ""}
            onChange={(e) => setPicked(e.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-border/60 bg-background px-2 py-2 text-xs outline-none"
          >
            {(folders.data?.items ?? []).map((f) => (
              <option key={f.name} value={f.name}>
                {f.completed ? "✅ " : ""}
                {f.name}
              </option>
            ))}
          </select>
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {folders.data?.completed_count ?? 0}/{folders.data?.total ?? 0}
          </span>
        </div>

        {folder && (
          <button
            type="button"
            disabled={marcar.isPending}
            onClick={() =>
              marcar.mutate(
                { source, folder, completed: !hecha },
                {
                  onSuccess: () => {
                    toast.success(hecha ? "Desmarcada" : "Carpeta completada");
                    if (!hecha) setPicked(null);
                  },
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : String(e)),
                },
              )
            }
            className={`flex w-full items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              hecha
                ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                : "border-border/60 text-muted-foreground hover:border-emerald-500 hover:text-emerald-500"
            }`}
          >
            <Check className="h-3.5 w-3.5" />
            {hecha ? "Completada" : "Marcar completada · siguiente"}
          </button>
        )}
      </section>

      {/* Los dos prompts. El de imagen se usa DOS veces. */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <p className="text-sm font-semibold">Prompts</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            type="button"
            disabled={!prompts.data?.imagen}
            onClick={() => copiar("Prompt de imagen", prompts.data?.imagen ?? "")}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <ImageIcon className="h-3.5 w-3.5" /> Prompt imagen (×2)
          </button>
          <button
            type="button"
            disabled={!prompts.data?.video}
            onClick={() => copiar("Prompt de vídeo", prompts.data?.video ?? "")}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <Clapperboard className="h-3.5 w-3.5" /> Prompt vídeo
          </button>
        </div>
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          Con el prompt de imagen sacas <strong>dos</strong> imágenes del
          producto, y de cada una un clip de ~5s. Los dos se pegan aquí: hasta
          que no subes los dos no se monta nada.
        </p>
      </section>

      {/* Productos */}
      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-indigo-500" />
          <p className="flex-1 text-sm font-semibold">Productos</p>
          <span className="text-[11px] text-muted-foreground">
            {listos}/{items.length} con los 2 clips
          </span>
        </div>

        <button
          type="button"
          disabled={extraer.isPending || !folder}
          onClick={() =>
            folder &&
            extraer.mutate(
              { source, folder },
              {
                onSuccess: () => toast.success("Textos extraídos"),
                onError: (e) =>
                  toast.error(e instanceof ApiError ? e.message : String(e)),
              },
            )
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-600 disabled:opacity-50"
        >
          {extraer.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Extrayendo…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5" /> Obtener textos ({conTexto}/
              {items.length})
            </>
          )}
        </button>

        {productos.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando productos…
          </div>
        )}
        {productos.isError && (
          <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
            {(productos.error as Error)?.message ?? "No se pudieron cargar los productos."}
          </p>
        )}

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
          <VendidosModal source={source} onClose={() => setVerVendidos(false)} />
        )}

        {/* El escaparate es común a todos los nichos: si el producto ya se
            metió desde el POV BOF o desde otra carpeta, aquí sale hecho. */}
        {folder && items.length > 0 && (
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

        {verEscaparate && folder && (
          <EscaparateModalCine source={source} folder={folder} productos={items}
            onClose={() => setVerEscaparate(false)} />
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {folder &&
            items.map((p) => (
              <CineCard key={p.producto} source={source} folder={folder} producto={p} />
            ))}
        </div>
      </section>
    </div>
  );
}

function CineCard({
  source,
  folder,
  producto,
}: {
  source: string;
  folder: string;
  producto: CineProducto;
}) {
  const subir = useCineSubirClip();
  const [sexo, setSexo] = useState<"hombre" | "mujer">(producto.sexo_sugerido);
  const [verFoto, setVerFoto] = useState(false);
  const [verVideo, setVerVideo] = useState(false);
  const [subiendo, setSubiendo] = useState<1 | 2 | null>(null);
  const ref1 = useRef<HTMLInputElement>(null);
  const ref2 = useRef<HTMLInputElement>(null);

  const limpia = producto.clean_photo_id
    ? cineFotoUrl(source, folder, producto.clean_photo_id)
    : null;
  const ficha = producto.titled_photo_id
    ? cineFotoUrl(source, folder, producto.titled_photo_id)
    : null;
  // El visor pide una copia mayor solo al abrirse; la tarjeta se conforma con
  // la miniatura. A tamaño original el móvil se quedaba sin memoria.
  const limpiaVisor = producto.clean_photo_id
    ? cineFotoUrl(source, folder, producto.clean_photo_id, ANCHO_VISOR)
    : null;
  const fichaVisor = producto.titled_photo_id
    ? cineFotoUrl(source, folder, producto.titled_photo_id, ANCHO_VISOR)
    : null;

  function onFile(slot: 1 | 2) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      setSubiendo(slot);
      subir.mutate(
        { source, folder, producto: producto.producto, slot, sexo, file },
        {
          onSettled: () => setSubiendo(null),
          onSuccess: (r) =>
            r.encolado ? toast.success(r.message) : toast.info(r.message),
          onError: (err) =>
            toast.error(err instanceof ApiError ? err.message : String(err)),
        },
      );
    };
  }

  function botonClip(slot: 1 | 2, puesto: boolean, ref: React.RefObject<HTMLInputElement>) {
    return (
      <button
        type="button"
        disabled={subiendo !== null || producto.montando}
        onClick={() => ref.current?.click()}
        className={`flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-semibold transition disabled:opacity-50 ${
          puesto
            ? "border border-emerald-500 bg-emerald-500/15 text-emerald-500"
            : "bg-indigo-500 text-white hover:bg-indigo-600"
        }`}
      >
        {subiendo === slot ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : puesto ? (
          <Check className="h-3.5 w-3.5" />
        ) : (
          <Upload className="h-3.5 w-3.5" />
        )}
        Clip {slot}
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-border/60 p-2">
      <div className="flex items-start gap-2">
        {limpia ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            className="shrink-0 rounded-md transition hover:ring-2 hover:ring-indigo-500"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={limpia}
              alt={producto.titulo || producto.producto}
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
              {producto.producto}
            </span>
            <span className="truncate">{producto.titulo || "sin título"}</span>
          </p>
          {producto.titulo_tiktok_completo && (
            <p className="truncate text-[10px] text-muted-foreground">
              {producto.titulo_tiktok_completo}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        <CopyChip label="📝 Título" text={producto.titulo} siempre />
        <CopyChip label="🔎 Título TikTok" text={producto.titulo_tiktok_completo} />
        <CopyChip label="🏪 Tienda" text={producto.tienda} siempre />
        <CopyChip label="✍️ Caption" text={producto.caption} />
        <CopyChip label="🎣 Gancho" text={producto.gancho} />
        <CopyChip label="👉 CTA" text={producto.cta} />
      </div>

      {producto.caption_riesgo && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          ⚠️ {producto.caption_riesgo}
        </p>
      )}

      {/* Voz: se elige ANTES de subir, porque el montaje arranca solo en
          cuanto entra el segundo clip. */}
      <div className="flex gap-1.5">
        {(["hombre", "mujer"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSexo(s)}
            className={`flex-1 rounded-md border px-2 py-1 text-[11px] font-medium transition ${
              sexo === s
                ? "border-indigo-500 bg-indigo-500/15 text-indigo-500"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            {s === "hombre" ? "👨 Hombre" : "👩 Mujer"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        <a
          href={cineFotoLimpiaUrl(source, folder, producto.producto)}
          className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
        >
          <Download className="h-3.5 w-3.5" /> Foto
        </a>
        {botonClip(1, producto.clip1, ref1)}
        {botonClip(2, producto.clip2, ref2)}
        <input ref={ref1} type="file" accept="video/*" className="hidden" onChange={onFile(1)} />
        <input ref={ref2} type="file" accept="video/*" className="hidden" onChange={onFile(2)} />
      </div>

      {producto.montando && (
        <p className="flex items-center justify-center gap-1.5 rounded border border-indigo-500/40 bg-indigo-500/10 px-2 py-1 text-[10px] text-indigo-500">
          <Loader2 className="h-3 w-3 animate-spin" /> Montando el vídeo…
        </p>
      )}
      {!producto.montando && (producto.clip1 !== producto.clip2) && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          Falta el clip {producto.clip1 ? 2 : 1} — el montaje empieza solo cuando
          están los dos.
        </p>
      )}

      {producto.video_path && (
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            onClick={() => setVerVideo(true)}
            className="rounded-md border border-emerald-500/60 px-2 py-1.5 text-[11px] font-medium text-emerald-500 transition hover:bg-emerald-500/10"
          >
            ▶ Ver vídeo
          </button>
          <a
            href={cineVideoUrl(source, folder, producto.producto, producto.video_listo_at, true)}
            className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
          >
            <Download className="h-3.5 w-3.5" /> Descargar
          </a>
        </div>
      )}

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={producto.titulo || `Producto ${producto.producto}`}
        urlLimpia={limpiaVisor}
        urlTitulo={fichaVisor}
        urlDescarga={cineFotoLimpiaUrl(source, folder, producto.producto)}
      />
      <VideoModal
        open={verVideo}
        onOpenChange={setVerVideo}
        title={producto.titulo || `Producto ${producto.producto}`}
        filename={`cine_${producto.producto}.mp4`}
        videoUrl={cineVideoUrl(source, folder, producto.producto, producto.video_listo_at)}
        downloadUrl={cineVideoUrl(
          source, folder, producto.producto, producto.video_listo_at, true,
        )}
      />
    </div>
  );
}


/** El escaparate del BOF Cine escribe en el índice común (su propio endpoint),
 *  pero sus productos son LOS MISMOS del POV BOF, así que el modal vale tal
 *  cual: mismas fotos, mismas carpetas. */
function EscaparateModalCine({
  source,
  folder,
  productos,
  onClose,
}: {
  source: string;
  folder: string;
  productos: CineProducto[];
  onClose: () => void;
}) {
  const setEstado = useSetEstadoCine(source, folder);
  return (
    <EscaparateModal
      source={source}
      folder={folder}
      productos={productos as unknown as ProductoItem[]}
      onClose={onClose}
      marcarEstado={(vars, opts) =>
        setEstado.mutate(
          { producto: vars.producto, en_escaparate: vars.en_escaparate },
          opts,
        )
      }
    />
  );
}
