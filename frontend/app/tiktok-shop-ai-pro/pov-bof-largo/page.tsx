"use client";

import {
  Download,
  Loader2,
  Mic,
  RefreshCw,
  Sparkles,
  Upload,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import {
  fotoLargoUrl,
  useEscribirGuion,
  useFoldersLargo,
  useProductosLargo,
  useSourcesLargo,
  useSubirClipLargo,
  useVocesLargo,
  videoLargoUrl,
} from "@/lib/queries/povBofLargo";
import type { ProductoLargo } from "@/lib/types/povBofLargo";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export default function PovBofLargoPage() {
  const sources = useSourcesLargo();
  const [source, setSource] = useState("");
  const activaSource = source || sources.data?.[0]?.slug || "";
  const folders = useFoldersLargo(activaSource);
  const [folder, setFolder] = useState("");
  const activaFolder = folder || folders.data?.[0] || "";
  const productos = useProductosLargo(activaSource, activaFolder);
  const voces = useVocesLargo();

  const items = productos.data?.items ?? [];
  const conGuion = items.filter((p) => p.guion).length;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Mic className="h-5 w-5 shrink-0 text-violet-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">POV BOF Largo</h1>
            <p className="text-[11px] text-muted-foreground">
              Guion escrito para cada producto y locutado · DOS clips de 10s
            </p>
          </div>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Es el POV BOF con la voz cambiada: en vez de una frase del banco, un
          guion que habla de ESE producto. Dura ~20s, por eso van dos clips. El
          vídeo se recorta a lo que dure la voz.
          {voces.data && (
            <>
              {" "}Banco de voces: {voces.data.hombre.length} de hombre y{" "}
              {voces.data.mujer.length} de mujer, se sortea una.
            </>
          )}
        </p>
      </header>

      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="grid grid-cols-2 gap-1.5">
          {(sources.data ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => {
                setSource(s.slug);
                setFolder("");
              }}
              className={`truncate rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
                activaSource === s.slug
                  ? "border-violet-500 bg-violet-500/15 text-violet-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {folders.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando carpetas…
          </div>
        )}
        <div className="flex flex-wrap gap-1.5">
          {(folders.data ?? []).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFolder(f)}
              className={`truncate rounded-lg border px-2 py-1 text-[11px] transition ${
                activaFolder === f
                  ? "border-violet-500 bg-violet-500/15 text-violet-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-violet-500" />
          <p className="flex-1 text-sm font-semibold">Productos</p>
          <span className="text-[11px] text-muted-foreground">
            {conGuion}/{items.length} con guion
          </span>
        </div>

        {productos.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando productos…
          </div>
        )}
        {productos.isError && (
          <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
            {(productos.error as Error)?.message ?? "No se pudieron cargar."}
          </p>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {items.map((p) => (
            <ProductoCard
              key={p.producto}
              source={activaSource}
              folder={activaFolder}
              producto={p}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function ProductoCard({
  source,
  folder,
  producto: p,
}: {
  source: string;
  folder: string;
  producto: ProductoLargo;
}) {
  const [verFoto, setVerFoto] = useState(false);
  const guion = useEscribirGuion();
  const subir = useSubirClipLargo();
  const refs = { 1: useRef<HTMLInputElement>(null), 2: useRef<HTMLInputElement>(null) };

  const [sexo, setSexo] = useState<"hombre" | "mujer">(
    (p.sexo_sugerido as "hombre" | "mujer") || "hombre",
  );
  const [gancho, setGancho] = useState(true);
  const [titulo, setTitulo] = useState(true);
  const [cta, setCta] = useState(true);
  const [flecha, setFlecha] = useState(true);

  const limpia = p.clean_photo_id ? fotoLargoUrl(source, folder, p.clean_photo_id) : null;
  const ficha = p.titled_photo_id ? fotoLargoUrl(source, folder, p.titled_photo_id) : null;

  function subirClip(slot: 1 | 2, file: File) {
    subir.mutate(
      {
        source, folder, producto: p.producto, slot, sexo, file,
        conGancho: gancho, conTitulo: titulo, conCta: cta, conFlecha: flecha,
      },
      {
        onSuccess: (r) => toast.success(r.message),
        onError: (e) => toast.error(err(e)),
        onSettled: () => {
          const r = refs[slot].current;
          if (r) r.value = "";
        },
      },
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-border/60 p-2">
      <div className="flex items-start gap-2">
        {limpia ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            className="shrink-0 rounded-md transition hover:ring-2 hover:ring-violet-500"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={limpia}
              alt={p.titulo || p.producto}
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
              {p.producto}
            </span>
            <span className="truncate">{p.titulo || "sin título"}</span>
          </p>
          {p.tienda && (
            <p className="truncate text-[10px] text-muted-foreground">{p.tienda}</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        <CopyChip label="📝 Título" text={p.titulo} siempre />
        <CopyChip label="✍️ Caption" text={[p.caption, p.emojis].filter(Boolean).join(" ")} />
        <CopyChip label="🎬 Guion" text={p.guion} />
        <CopyChip label="💬 Subliminal" text={p.subliminal} />
      </div>

      {p.caption_riesgo && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          ⚠️ {p.caption_riesgo}
        </p>
      )}

      {/* El guion es lo primero: sin él no se puede subir clip, porque es
          quien decide cuánto dura el vídeo. */}
      {p.guion ? (
        <div className="space-y-1 rounded border border-border/60 bg-muted/30 p-2">
          <p className="text-[10px] leading-relaxed">{p.guion}</p>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground">
              {p.guion_caracteres} car. · ~{Math.round(p.guion_caracteres / 18.2)}s
            </span>
            <button
              type="button"
              disabled={guion.isPending}
              onClick={() =>
                guion.mutate(
                  { source, folder, producto: p.producto, rehacer: true },
                  { onError: (e) => toast.error(err(e)) },
                )
              }
              className="ml-auto flex items-center gap-1 rounded border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw className={`h-3 w-3 ${guion.isPending ? "animate-spin" : ""}`} />
              Otro guion
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          disabled={guion.isPending || !p.titulo}
          onClick={() =>
            guion.mutate(
              { source, folder, producto: p.producto },
              {
                onSuccess: () => toast.success("Guion escrito"),
                onError: (e) => toast.error(err(e)),
              },
            )
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
        >
          {guion.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Escribiendo…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5" />
              {p.titulo ? "Escribir el guion" : "Falta extraer los textos"}
            </>
          )}
        </button>
      )}

      <div className="grid grid-cols-2 gap-1">
        {(["hombre", "mujer"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSexo(s)}
            className={`rounded-md border px-2 py-1 text-[11px] capitalize transition ${
              sexo === s
                ? "border-violet-500 bg-violet-500/15 text-violet-500"
                : "border-border/60 text-muted-foreground"
            }`}
          >
            Voz {s}
            {p.sexo_sugerido === s && " ★"}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        {(
          [
            ["Gancho", gancho, setGancho],
            ["Título", titulo, setTitulo],
            ["CTA", cta, setCta],
            ["Flecha", flecha, setFlecha],
          ] as const
        ).map(([label, valor, set]) => (
          <button
            key={label}
            type="button"
            onClick={() => (set as (v: boolean) => void)(!valor)}
            className={`rounded-md border px-2 py-1 text-[10px] transition ${
              valor
                ? "border-violet-500/60 bg-violet-500/10 text-violet-500"
                : "border-border/60 text-muted-foreground/50 line-through"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Los DOS clips. No se encola hasta tener los dos. */}
      <div className="grid grid-cols-2 gap-1.5">
        {([1, 2] as const).map((slot) => {
          const puesto = slot === 1 ? p.clip1 : p.clip2;
          return (
            <label
              key={slot}
              className={`flex cursor-pointer items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-[11px] font-medium transition ${
                puesto
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 hover:border-violet-500/60"
              } ${!p.guion ? "pointer-events-none opacity-40" : ""}`}
            >
              <Upload className="h-3.5 w-3.5 shrink-0" />
              {puesto ? `Clip ${slot} ✓` : `Clip ${slot}`}
              <input
                ref={refs[slot]}
                type="file"
                accept="video/*"
                disabled={subir.isPending || !p.guion}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) subirClip(slot, f);
                }}
                className="hidden"
              />
            </label>
          );
        })}
      </div>
      {!p.guion && (
        <p className="text-[10px] text-muted-foreground">
          Escribe el guion antes de subir los clips: la voz decide la duración.
        </p>
      )}

      {p.montando && (
        <p className="flex items-center gap-1.5 rounded border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-[10px] text-violet-500">
          <Loader2 className="h-3 w-3 animate-spin" /> Locutando y montando…
        </p>
      )}

      {p.video_path && (
        <div className="flex items-center gap-1">
          <a
            href={videoLargoUrl(source, folder, p.producto)}
            target="_blank"
            rel="noreferrer"
            className="flex-1 truncate rounded border border-border/60 px-2 py-1 text-[10px] transition hover:border-foreground/30"
          >
            ▶️ Ver vídeo{p.voz_label && ` · ${p.voz_label}`}
          </a>
          <a
            href={videoLargoUrl(source, folder, p.producto, true)}
            title="Descargar"
            className="rounded border border-border/60 p-1 text-muted-foreground transition hover:text-foreground"
          >
            <Download className="h-3 w-3" />
          </a>
        </div>
      )}

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={p.titulo || `Producto ${p.producto}`}
        urlLimpia={limpia}
        urlTitulo={ficha}
      />
    </div>
  );
}
