"use client";

import {
  Download,
  FlaskConical,
  Loader2,
  Plus,
  Sparkles,
  Store,
  Trash2,
  Upload,
  ShoppingBag,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import {
  fotoPilotoUrl,
  useBorrarProductoPiloto,
  useCrearProductoPiloto,
  useExtraerTextosPiloto,
  useProductosPiloto,
  useSetEstadoPiloto,
  useSubirVideoPiloto,
  videoPilotoUrl,
} from "@/lib/queries/cuentaPiloto";
import type { ProductoPiloto } from "@/lib/types/cuentaPiloto";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

function error(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export default function CuentaPilotoPage() {
  const productos = useProductosPiloto();
  const extraer = useExtraerTextosPiloto();

  const items = productos.data ?? [];
  const sinTitulo = items.filter((p) => p.tiene_ficha && !p.titulo).length;
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const pendientesEscaparate = items.filter((p) => !p.en_escaparate).length;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5 shrink-0 text-sky-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Cuenta Piloto</h1>
            <p className="text-[11px] text-muted-foreground">
              Vídeo orgánico + la edición del POV BOF · tus productos, solo tuyos
            </p>
          </div>
        </div>
      </header>

      <AltaProducto />

      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-sky-500" />
          <p className="flex-1 text-sm font-semibold">Mis productos</p>
          <span className="text-[11px] text-muted-foreground">{items.length}</span>
        </div>

        {sinTitulo > 0 && (
          <button
            type="button"
            disabled={extraer.isPending}
            onClick={() =>
              extraer.mutate(undefined, {
                onSuccess: () => toast.success("Textos extraídos"),
                onError: (e) => toast.error(error(e)),
              })
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-sky-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-600 disabled:opacity-50"
          >
            {extraer.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Leyendo fichas…
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" /> Obtener textos ({sinTitulo} sin
                título)
              </>
            )}
          </button>
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
          <VendidosModal conBuscador={false} onClose={() => setVerVendidos(false)} />
        )}

        {/* El escaparate es común a todos los nichos: si el mismo producto ya
            se metió desde el POV BOF, aquí sale hecho. */}
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
              {`${items.length - pendientesEscaparate}/${items.length}`}
            </span>
          </button>
        )}

        {verEscaparate && (
          <EscaparateModalPiloto
            productos={items}
            onClose={() => setVerEscaparate(false)}
          />
        )}

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
        {!productos.isLoading && items.length === 0 && (
          <p className="rounded-lg border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
            Todavía no hay productos. Sube las dos fotos de uno aquí arriba.
          </p>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {items.map((p) => (
            <ProductoCard key={p.id} producto={p} />
          ))}
        </div>
      </section>
    </div>
  );
}

/** El escaparate de este nicho escribe en el índice común (por su propio
 *  endpoint). Dos adaptaciones: aquí el producto se identifica por `id` y el
 *  modal espera `producto`, así que se mapea antes; y las fotos no salen del
 *  Drive del POV BOF sino de este nicho, por eso `source`/`folder` van vacíos
 *  y se le pasan las URLs propias. */
function EscaparateModalPiloto({
  productos,
  onClose,
}: {
  productos: ProductoPiloto[];
  onClose: () => void;
}) {
  const setEstado = useSetEstadoPiloto();
  return (
    <EscaparateModal
      source=""
      // Aquí no hay carpetas: `folder` solo se usa como rótulo de la cabecera
      // del modal, y dejarlo vacío deja un “·” colgando.
      folder="Mis productos"
      productos={
        productos.map((p) => ({ ...p, producto: p.id })) as unknown as ProductoItem[]
      }
      onClose={onClose}
      marcarEstado={(vars, opts) =>
        setEstado.mutate(
          { producto: vars.producto, en_escaparate: vars.en_escaparate },
          opts,
        )
      }
      fotoUrl={(p) => fotoPilotoUrl(p.producto, "limpia")}
      descargaUrl={(p) => fotoPilotoUrl(p.producto, "limpia", true)}
    />
  );
}

/** Alta del producto: las dos fotos. En este nicho NO salen de Drive — las
 *  sube el operador, que es quien sabe cuál es la limpia y cuál la ficha. */
function AltaProducto() {
  const crear = useCrearProductoPiloto();
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const refLimpia = useRef<HTMLInputElement>(null);
  const refFicha = useRef<HTMLInputElement>(null);

  function enviar() {
    if (!limpia) {
      toast.error("Falta la foto del producto.");
      return;
    }
    crear.mutate(
      { fotoLimpia: limpia, fotoFicha: ficha },
      {
        onSuccess: (p) => {
          toast.success(
            p.titulo ? `Producto ${p.id}: ${p.titulo}` : `Producto ${p.id} creado`,
          );
          setLimpia(null);
          setFicha(null);
          if (refLimpia.current) refLimpia.current.value = "";
          if (refFicha.current) refFicha.current.value = "";
        },
        onError: (e) => toast.error(error(e)),
      },
    );
  }

  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-center gap-2">
        <Plus className="h-4 w-4 shrink-0 text-sky-500" />
        <p className="text-sm font-semibold">Nuevo producto</p>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FotoInput
          inputRef={refLimpia}
          label="Foto del producto"
          ayuda="La limpia, sin texto encima"
          archivo={limpia}
          onChange={setLimpia}
        />
        <FotoInput
          inputRef={refFicha}
          label="Captura de la ficha"
          ayuda="De aquí salen título, tienda y caption (opcional)"
          archivo={ficha}
          onChange={setFicha}
        />
      </div>

      <button
        type="button"
        disabled={crear.isPending || !limpia}
        onClick={enviar}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-sky-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-600 disabled:opacity-50"
      >
        {crear.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Creando y leyendo la
            ficha…
          </>
        ) : (
          <>
            <Plus className="h-3.5 w-3.5" /> Crear producto
          </>
        )}
      </button>
    </section>
  );
}

function FotoInput({
  inputRef,
  label,
  ayuda,
  archivo,
  onChange,
}: {
  inputRef: React.RefObject<HTMLInputElement>;
  label: string;
  ayuda: string;
  archivo: File | null;
  onChange: (f: File | null) => void;
}) {
  return (
    <label className="flex cursor-pointer flex-col gap-1 rounded-lg border border-dashed border-border/60 p-2.5 transition hover:border-sky-500/60">
      <span className="text-[11px] font-semibold">{label}</span>
      <span className="text-[10px] text-muted-foreground">{ayuda}</span>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
        className="mt-1 block w-full text-[10px] text-muted-foreground file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-[10px]"
      />
      {archivo && (
        <span className="truncate text-[10px] text-sky-500">✓ {archivo.name}</span>
      )}
    </label>
  );
}

function ProductoCard({ producto: p }: { producto: ProductoPiloto }) {
  const [verFoto, setVerFoto] = useState(false);
  const subir = useSubirVideoPiloto();
  // Progreso de la tanda que se está mandando (null = no hay ninguna).
  const [enviando, setEnviando] = useState<{ hechos: number; total: number } | null>(null);
  const borrar = useBorrarProductoPiloto();
  const extraer = useExtraerTextosPiloto();
  const refVideo = useRef<HTMLInputElement>(null);

  const [sexo, setSexo] = useState<"hombre" | "mujer">("hombre");
  const [gancho, setGancho] = useState(true);
  const [titulo, setTitulo] = useState(true);
  const [cta, setCta] = useState(true);
  const [flecha, setFlecha] = useState(true);

  /** Manda a editar TODOS los vídeos elegidos, uno detrás de otro.
   *
   *  De uno en uno a propósito: son ficheros grandes y subir nueve a la vez
   *  desde el móvil satura la conexión y hace que fallen a medias. La cola ya
   *  se encarga de que los montajes vayan seguidos.
   *
   *  Cada vídeo sale con distinto rótulo, emoji y color sin hacer nada: el
   *  montaje los sortea a partir del número de vídeo dentro del producto.
   */
  async function subirTanda(files: File[]) {
    if (!files.length) return;
    setEnviando({ hechos: 0, total: files.length });
    let ok = 0;
    for (const [i, file] of files.entries()) {
      setEnviando({ hechos: i, total: files.length });
      try {
        await subir.mutateAsync({
          producto: p.id,
          file,
          sexo,
          conGancho: gancho,
          conTitulo: titulo,
          conCta: cta,
          conFlecha: flecha,
          // Solo el primero abre el contador de la tanda.
          lote: i === 0 ? files.length : 0,
        });
        ok++;
      } catch (e) {
        toast.error(`Vídeo ${i + 1}: ${error(e)}`);
      }
    }
    setEnviando(null);
    if (refVideo.current) refVideo.current.value = "";
    if (ok) {
      toast.success(
        ok === 1 ? "En la cola, editando…" : `${ok} vídeos en la cola, editando…`,
      );
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-border/60 p-2">
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => setVerFoto(true)}
          className="shrink-0 rounded-md transition hover:ring-2 hover:ring-sky-500"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={fotoPilotoUrl(p.id, "limpia")}
            alt={p.titulo || `Producto ${p.id}`}
            loading="lazy"
            className="h-16 w-16 rounded-md object-cover"
          />
        </button>
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-1.5 text-xs font-semibold">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {p.id}
            </span>
            <span className="truncate">{p.titulo || "sin título"}</span>
          </p>
          {p.tienda && (
            <p className="truncate text-[10px] text-muted-foreground">{p.tienda}</p>
          )}
        </div>
        <button
          type="button"
          title="Borrar producto"
          onClick={() => {
            if (!confirm(`¿Borrar el producto ${p.id} y sus vídeos?`)) return;
            borrar.mutate(p.id, { onError: (e) => toast.error(error(e)) });
          }}
          className="shrink-0 rounded p-1 text-muted-foreground/50 transition hover:text-red-500"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex flex-wrap gap-1">
        <CopyChip label="📝 Título" text={p.titulo} siempre />
        <CopyChip label="🏪 Tienda" text={p.tienda} siempre />
        <CopyChip
          label="✍️ Caption"
          text={[p.caption, p.emojis].filter(Boolean).join(" ")}
        />
        <CopyChip label="🎣 Gancho" text={p.gancho} />
        <CopyChip label="👉 CTA" text={p.cta} />
      </div>

      {p.caption_riesgo && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          ⚠️ {p.caption_riesgo}
        </p>
      )}
      {p.tiene_ficha && !p.titulo && (
        <button
          type="button"
          disabled={extraer.isPending}
          onClick={() =>
            extraer.mutate(p.id, { onError: (e) => toast.error(error(e)) })
          }
          className="w-full rounded border border-sky-500/40 bg-sky-500/10 px-2 py-1 text-[10px] text-sky-500 disabled:opacity-50"
        >
          {extraer.isPending ? "Leyendo la ficha…" : "Leer la ficha con IA"}
        </button>
      )}
      {!p.tiene_ficha && (
        <p className="rounded border border-border/60 px-2 py-1 text-[10px] text-muted-foreground">
          Sin captura de la ficha — no hay textos que leer.
        </p>
      )}

      {/* Opciones del montaje: las mismas del POV BOF. */}
      <div className="grid grid-cols-2 gap-1">
        {(["hombre", "mujer"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSexo(s)}
            className={`rounded-md border px-2 py-1 text-[11px] capitalize transition ${
              sexo === s
                ? "border-sky-500 bg-sky-500/15 text-sky-500"
                : "border-border/60 text-muted-foreground"
            }`}
          >
            Voz {s}
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
                ? "border-sky-500/60 bg-sky-500/10 text-sky-500"
                : "border-border/60 text-muted-foreground/50 line-through"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Se eligen VARIOS de la galería y se mandan todos a editar de una
          vez: en el Piloto lo normal es probar el mismo producto muchas veces
          y hacerlo de uno en uno eran nueve viajes. */}
      <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-md bg-sky-500 px-2 py-2 text-[11px] font-semibold text-white transition hover:bg-sky-600">
        {enviando ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Mandando a editar{" "}
            {enviando.hechos + 1}/{enviando.total}…
          </>
        ) : (
          <>
            <Upload className="h-3.5 w-3.5" />
            {p.videos.length > 0 ? "Mandar más vídeos a editar" : "Mandar vídeos a editar"}
          </>
        )}
        <input
          ref={refVideo}
          type="file"
          accept="video/*"
          multiple
          disabled={Boolean(enviando)}
          onChange={(e) => {
            const elegidos = Array.from(e.target.files ?? []);
            if (elegidos.length) void subirTanda(elegidos);
          }}
          className="hidden"
        />
      </label>

      {/* De la ÚLTIMA tanda, no del total histórico del producto: mandas nueve
          y lo que quieres saber es cuántos de esos nueve están. */}
      {p.lote_total > 1 && (
        <p
          className={`flex items-center gap-1.5 rounded border px-2 py-1 text-[10px] ${
            p.lote_listos >= p.lote_total
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"
              : "border-sky-500/40 bg-sky-500/10 text-sky-500"
          }`}
        >
          {p.lote_listos >= p.lote_total ? (
            <>✅ Listos {p.lote_listos}/{p.lote_total} vídeos — ya se pueden descargar</>
          ) : (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Editando {p.lote_listos}/
              {p.lote_total} vídeos…
            </>
          )}
        </p>
      )}
      {p.montando && p.lote_total <= 1 && (
        <p className="flex items-center gap-1.5 rounded border border-sky-500/40 bg-sky-500/10 px-2 py-1 text-[10px] text-sky-500">
          <Loader2 className="h-3 w-3 animate-spin" /> Montando un vídeo…
        </p>
      )}

      {/* Varios vídeos por producto: es lo que distingue a este nicho. */}
      {p.videos.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold text-muted-foreground">
            {p.videos.length} vídeo{p.videos.length > 1 ? "s" : ""} montado
            {p.videos.length > 1 ? "s" : ""}
          </p>
          {p.videos.map((v) => (
            <div key={v.n} className="flex items-center gap-1">
              <a
                href={videoPilotoUrl(p.id, v.n)}
                target="_blank"
                rel="noreferrer"
                className="flex-1 truncate rounded border border-border/60 px-2 py-1 text-[10px] transition hover:border-foreground/30"
              >
                ▶️ Vídeo {v.n} · voz {v.sexo || "?"}
              </a>
              <a
                href={videoPilotoUrl(p.id, v.n, true)}
                title="Descargar"
                className="rounded border border-border/60 p-1 text-muted-foreground transition hover:text-foreground"
              >
                <Download className="h-3 w-3" />
              </a>
            </div>
          ))}
        </div>
      )}

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={p.titulo || `Producto ${p.id}`}
        urlLimpia={fotoPilotoUrl(p.id, "limpia")}
        urlTitulo={p.tiene_ficha ? fotoPilotoUrl(p.id, "ficha") : null}
        urlDescarga={fotoPilotoUrl(p.id, "limpia", true)}
      />
    </div>
  );
}
