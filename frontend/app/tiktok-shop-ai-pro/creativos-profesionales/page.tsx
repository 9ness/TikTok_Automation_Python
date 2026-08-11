"use client";

import {
  Check,
  ClipboardCopy,
  Download,
  Loader2,
  Sparkles,
  Store,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import {
  useCompletarCarpetaCreativos,
  useFoldersCreativos,
  usePromptCreativos,
} from "@/lib/queries/nichoCreativos";
// El catálogo es EL MISMO del Nicho POV BOF: fuentes, fotos, textos, hashtags,
// escaparate y vendidos. Duplicarlo habría significado extraer los textos dos
// veces con Gemini y que las dos copias se separaran a la primera corrección.
import {
  buildCleanPhotoDownloadUrl,
  buildPhotoUrl,
  useExtraerTextos,
  useHashtags,
  useProductos,
  useSetEstado,
  useSources,
  ANCHO_VISOR,
} from "@/lib/queries/nichoPovBof";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export default function CreativosProPage() {
  const sources = useSources();
  const [source, setSource] = useEstadoRecordado("creativos:fuente", "aleatorios_1");
  const folders = useFoldersCreativos(source);
  const [picked, setPicked] = useEstadoRecordado<string | null>("creativos:carpeta", null);
  const folder = picked ?? folders.data?.current ?? null;
  const productos = useProductos(source, folder);
  const prompt = usePromptCreativos();
  const extraer = useExtraerTextos();
  const completar = useCompletarCarpetaCreativos();

  const [bajando, setBajando] = useState("");
  const [verEscaparate, setVerEscaparate] = useState(false);

  const items = productos.data ?? [];
  const conTexto = items.filter((p) => p.titulo).length;
  const pendientesEscaparate = items.filter((p) => !p.en_escaparate).length;
  const hecha = folders.data?.items.find((f) => f.name === folder)?.completed ?? false;

  // Se bajan las fotos CON LA DESCRIPCIÓN (la captura de la ficha), no las
  // limpias: el prompt del creativo pide integrar los beneficios del producto,
  // y esos solo están en la ficha. Con la foto limpia el generador no tiene de
  // dónde sacarlos y se los inventa — que es justo lo que el prompt prohíbe.
  async function descargarFotos() {
    const conFoto = items.filter((p) => p.titled_photo_id);
    if (!folder || !conFoto.length) {
      toast.error("Ningún producto de esta carpeta tiene foto de la ficha");
      return;
    }
    // Una a una con un respiro: varias descargas simultáneas se bloquean o se
    // cancelan solas en el navegador del móvil.
    for (const [i, p] of conFoto.entries()) {
      setBajando(`${i + 1}/${conFoto.length}`);
      const a = document.createElement("a");
      // Por el endpoint de descarga, NO por el de ver: `download` se ignora
      // entre orígenes distintos y la API es otro origen, así que quien fuerza
      // la descarga es el Content-Disposition del backend. Con la URL de ver,
      // el móvil abría las fotos en pestañas y no bajaba ninguna.
      a.href = buildCleanPhotoDownloadUrl(source, folder, p.producto, "ficha");
      a.download = `${folder}_${p.producto}_ficha`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < conFoto.length - 1) await new Promise((r) => setTimeout(r, 600));
    }
    setBajando("");
    toast.success(`${conFoto.length} foto(s) descargadas`);
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 shrink-0 text-cyan-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Creativos Pro</h1>
            <p className="text-[11px] text-muted-foreground">
              Un creativo publicitario por producto · sin vídeo
            </p>
          </div>
        </div>
      </header>

      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="grid grid-cols-3 gap-1.5">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => {
                setSource(s.slug);
                setPicked(null);
              }}
              className={`truncate rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
                source === s.slug
                  ? "border-cyan-500 bg-cyan-500/15 text-cyan-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Progreso: es SUYO. Haber hecho una carpeta en POV BOF no la deja
            hecha aquí — un creativo no es un vídeo. */}
        {folders.data && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>
                {folders.data.done}/{folders.data.total} carpetas
              </span>
              <span className="truncate font-medium text-foreground">{folder}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-cyan-500 transition-all"
                style={{
                  width: `${folders.data.total ? (folders.data.done / folders.data.total) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-1">
          {(folders.data?.items ?? []).map((f) => (
            <button
              key={f.name}
              type="button"
              onClick={() => setPicked(f.name)}
              className={`truncate rounded border px-2 py-1 text-[10px] transition ${
                folder === f.name
                  ? "border-cyan-500 bg-cyan-500/15 text-cyan-500"
                  : f.completed
                    ? "border-emerald-500/40 text-emerald-500"
                    : "border-border/60 text-muted-foreground"
              }`}
            >
              {f.completed && "✓ "}
              {f.name}
            </button>
          ))}
        </div>
      </section>

      {/* Un solo prompt, y el formato pegado a él: copiarlo y generar en
          cuadrado es el error fácil de este nicho. */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <button
          type="button"
          disabled={!prompt.data}
          onClick={() => {
            navigator.clipboard.writeText(prompt.data?.imagen ?? "");
            toast.success("Prompt copiado");
          }}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
        >
          <ClipboardCopy className="h-3.5 w-3.5" /> Prompt imagen
        </button>
        <p className="text-center text-[11px] font-semibold text-cyan-500">
          Genera en formato {prompt.data?.formato ?? "3:4"}
        </p>
      </section>

      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            disabled={extraer.isPending || !folder}
            onClick={() =>
              extraer.mutate(
                { source, folder: folder! },
                {
                  onSuccess: () => toast.success("Textos extraídos"),
                  onError: (e) => toast.error(err(e)),
                },
              )
            }
            className="flex items-center justify-center gap-1.5 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-cyan-600 disabled:opacity-50"
          >
            {extraer.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Extrayendo…
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" /> Textos ({conTexto}/{items.length})
              </>
            )}
          </button>
          <button
            type="button"
            disabled={Boolean(bajando) || !items.length}
            onClick={descargarFotos}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            {bajando
              ? `Bajando ${bajando}`
              : `Fotos ficha (${items.filter((p) => p.titled_photo_id).length})`}
          </button>
        </div>

        {productos.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando productos…
          </div>
        )}

        {/* El escaparate es el mismo para todos los nichos: si el producto ya
            se metió desde el POV BOF (o desde otra carpeta), aquí sale hecho. */}
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
          <EscaparateModal
            source={source}
            folder={folder}
            productos={items}
            onClose={() => setVerEscaparate(false)}
          />
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {items.map((p) => (
            <CreativoCard key={p.producto} source={source} folder={folder!} producto={p} />
          ))}
        </div>

        {folder && (
          <button
            type="button"
            disabled={completar.isPending}
            onClick={() =>
              completar.mutate(
                { source, folder, completed: !hecha },
                { onError: (e) => toast.error(err(e)) },
              )
            }
            className={`flex w-full items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${
              hecha
                ? "border-border/60 text-muted-foreground"
                : "border-emerald-500 bg-emerald-500/15 text-emerald-500"
            }`}
          >
            <Check className="h-3.5 w-3.5" />
            {hecha ? "Desmarcar carpeta" : "Carpeta completada"}
          </button>
        )}
      </section>
    </div>
  );
}

/** Ficha de producto SIN nada de vídeo: aquí no se sube nada ni se marca
 *  "Subido". Solo lo que hace falta para publicar el creativo — buscar el
 *  producto (título TikTok + tienda) y la descripción (caption + hashtags). */
function CreativoCard({
  source,
  folder,
  producto: p,
}: {
  source: string;
  folder: string;
  producto: ProductoItem;
}) {
  const [verFoto, setVerFoto] = useState(false);
  const setEstado = useSetEstado();
  const hashtags = useHashtags();
  const [enEscaparate, setEnEscaparate] = useState(p.en_escaparate);
  const [sold, setSold] = useState(p.sold);
  const [eligiendoNicho, setEligiendoNicho] = useState(false);

  // Dos tamaños a propósito: la tarjeta pinta una miniatura y el visor pide una
  // más grande solo al abrirlo. A tamaño original una carpeta se llevaba ~300 MB
  // de RAM en el móvil y Chrome cerraba la app (ver `ANCHO_MINIATURA`).
  const limpia = p.clean_photo_id ? buildPhotoUrl(source, folder, p.clean_photo_id) : null;
  const ficha = p.titled_photo_id ? buildPhotoUrl(source, folder, p.titled_photo_id) : null;
  const limpiaVisor = p.clean_photo_id
    ? buildPhotoUrl(source, folder, p.clean_photo_id, ANCHO_VISOR)
    : null;
  const fichaVisor = p.titled_photo_id
    ? buildPhotoUrl(source, folder, p.titled_photo_id, ANCHO_VISOR)
    : null;

  // Los hashtags son COMUNES a todos los nichos: si se añade uno en POV BOF
  // aparece aquí. Lo pidió así el operador.
  const caption = [p.caption, p.emojis, (hashtags.data ?? []).join(" ")]
    .filter(Boolean)
    .join(" ");

  const push = (patch: Record<string, unknown>) =>
    setEstado.mutate(
      { source, folder, producto: p.producto, ...patch },
      { onError: (e) => toast.error(err(e)) },
    );

  return (
    <div className="space-y-2 rounded-lg border border-border/60 p-2">
      <div className="flex items-start gap-2">
        {limpia ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            className="shrink-0 rounded-md transition hover:ring-2 hover:ring-cyan-500"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={limpia}
              alt={p.titulo ?? p.producto}
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
            <span className="truncate">{p.titulo ?? "sin título"}</span>
          </p>
          {p.tienda && (
            <p className="truncate text-[10px] text-muted-foreground">{p.tienda}</p>
          )}
        </div>
      </div>

      {/* Solo lo que se usa al publicar un creativo. */}
      <div className="flex flex-wrap gap-1">
        <CopyChip label="🔎 Título TikTok" text={p.titulo_tiktok_completo ?? ""} siempre />
        <CopyChip label="🏪 Tienda" text={p.tienda ?? ""} siempre />
        <CopyChip label="✍️ Caption" text={caption} siempre />
      </div>

      {p.caption_riesgo && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          ⚠️ {p.caption_riesgo}
        </p>
      )}

      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => {
            const v = !enEscaparate;
            setEnEscaparate(v);
            push({ en_escaparate: v });
          }}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            enEscaparate
              ? "border-cyan-500 bg-cyan-500/15 text-cyan-500"
              : "border-border/60 text-muted-foreground"
          }`}
        >
          🏪 Escaparate
        </button>
        <button
          type="button"
          onClick={() => {
            if (sold) {
              setSold(false);
              push({ sold: false });
              return;
            }
            setEligiendoNicho(true);
          }}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            sold
              ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
              : "border-border/60 text-muted-foreground"
          }`}
        >
          💰 Vendió
        </button>
      </div>

      {/* La venta se atribuye a un nicho: el mismo producto se trabaja con
          varios y adivinarlo sería inventar el dato. Aquí se propone
          "creativos" por defecto, pero puede haber vendido por otro. */}
      {eligiendoNicho && (
        <div className="space-y-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2">
          <p className="text-[11px] font-semibold">¿Con qué nicho vendió?</p>
          <div className="grid grid-cols-2 gap-1">
            {(
              [
                ["creativos", "Creativos Pro"],
                ["pov_bof", "POV BOF"],
                ["pov_bof_largo", "POV BOF Largo"],
                ["bof_cine", "BOF Cine"],
                ["ropa", "Ropa"],
                ["gorras", "Gorras"],
                ["otro", "Otro"],
              ] as [string, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setEligiendoNicho(false);
                  setSold(true);
                  push({ sold: true, nicho: key });
                }}
                className="truncate rounded border border-border/60 px-2 py-1 text-[10px] transition hover:border-emerald-500 hover:text-emerald-500"
              >
                {label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setEligiendoNicho(false)}
            className="w-full rounded px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground"
          >
            Cancelar
          </button>
        </div>
      )}

      {/* Se baja la de la FICHA también aquí, no solo en la descarga masiva:
          el creativo necesita los beneficios del producto y solo están ahí. */}
      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={p.titulo ?? `Producto ${p.producto}`}
        urlLimpia={limpiaVisor}
        urlTitulo={fichaVisor}
        urlDescarga={buildCleanPhotoDownloadUrl(source, folder, p.producto, "ficha")}
        textoDescarga="Descargar la foto con la descripción"
      />
    </div>
  );
}
