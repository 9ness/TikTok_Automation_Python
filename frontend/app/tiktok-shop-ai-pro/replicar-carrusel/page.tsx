"use client";

import { useEffect, useState } from "react";
import { Download, GalleryHorizontalEnd, Loader2, Plus, Repeat, Upload } from "lucide-react";
import { toast } from "sonner";

import { BotonFotosEnOrden } from "@/components/tiktok-shop-ai-pro/BotonFotosEnOrden";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { GuiaIA } from "@/components/tiktok-shop-ai-pro/GuiaIA";
import { MusicaCarrusel } from "@/components/tiktok-shop-ai-pro/MusicaCarrusel";
import { Caja, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { useMe } from "@/lib/queries/auth";
import { useBuscarProductos, useSources } from "@/lib/queries/nichoPovBof";
import {
  type CarruselReplica,
  type Diapositiva,
  type ProductoCarrusel,
  urlFotoCarrusel,
  useCarrusel,
  useCarruseles,
  useCatalogoCarrusel,
  useCrearProductoCarrusel,
  useReleerTextosCarrusel,
  useReplicarCarrusel,
  useReplicarOtraVez,
  useSubirFotoCarrusel,
  useTextoCarrusel,
} from "@/lib/queries/replicarCarrusel";

/** Los botones que sacan texto hacia la herramienta de IA (UI_NICHOS.md). */
const BTN_PROMPT =
  "flex items-center justify-center gap-1.5 rounded-lg border border-violet-500/50" +
  " bg-gradient-to-r from-violet-500/20 to-fuchsia-500/20 px-3 py-2 text-xs" +
  " font-semibold text-violet-400 transition hover:border-violet-400" +
  " hover:from-violet-500/30 hover:to-fuchsia-500/30 disabled:opacity-40";

const ROL: Record<string, string> = {
  gancho: "Gancho",
  problema: "Problema",
  producto: "Producto",
  prueba: "Prueba",
  cta: "CTA",
};

interface Elegido {
  source: string;
  folder: string;
  producto: string;
  titulo: string;
}

/** «Replicar carrusel»: un carrusel de fotos viral de TikTok + un producto
 *  nuestro → texto y prompt de Flow por diapositiva; las fotos se generan a
 *  mano en Flow, se suben aquí y salen con el texto quemado en un ZIP
 *  (`src/replicar_viral/carrusel.py`). */
export default function ReplicarCarruselPage() {
  const sources = useSources();
  const [source, setSource] = useState("");
  const [busca, setBusca] = useState("");
  const [elegido, setElegido] = useState<Elegido | null>(null);
  const [url, setUrl] = useState("");
  const [abierto, setAbierto] = useState<string | null>(null);
  const [para, setPara] = useState("");
  const me = useMe();
  const esAdmin = me.data?.rol === "admin";
  const otros = (me.data?.usuarios ?? []).filter((u) => u.username !== me.data?.username);

  useEffect(() => {
    const primero = sources.data?.items?.[0]?.slug;
    if (!source && primero) setSource(primero);
  }, [source, sources.data]);

  const resultados = useBuscarProductos(source, busca);
  const lista = useCarruseles();
  const replicar = useReplicarCarrusel();
  const doc = useCarrusel(abierto);

  const analizar = () => {
    if (!elegido || !url.trim()) return;
    replicar.mutate(
      {
        source: elegido.source, folder: elegido.folder, producto: elegido.producto, url: url.trim(),
        para: esAdmin ? para : "",
      },
      {
        onSuccess: (d) => {
          setUrl("");
          if (para && esAdmin) {
            toast.success(`Carrusel replicado para ${para}: lo verá en su «Replicar carrusel» y en sus tandas`);
          } else {
            setAbierto(d.id);
            toast.success(`Carrusel analizado: ${d.total} diapositivas`);
          }
        },
        onError: (e) => toast.error(e.message),
      },
    );
  };

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <GalleryHorizontalEnd className="h-5 w-5 shrink-0 text-violet-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Replicar carrusel</h1>
            <p className="text-[11px] text-muted-foreground">
              Un carrusel viral de TikTok, con nuestro producto y otro ambiente
            </p>
          </div>
          <GuiaIA guia="replicar-carrusel" />
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Pega el enlace de un carrusel de fotos (de Social1) y elige un producto del catálogo del
          POV BOF. La IA lee cada diapositiva y te da su texto adaptado y el prompt para generar la
          foto en Google Flow. Las fotos las generas tú (no gasta créditos); al subirlas, la app
          les pone el texto y te las da todas juntas.
        </p>
      </header>

      <Caja
        icono="📁"
        titulo="Dónde trabajas"
        hint="El producto sale del catálogo del POV BOF (necesita sus textos)."
      >
        <Sub>Catálogo</Sub>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => setSource(s.slug)}
              className={`truncate rounded-lg border px-2 py-1.5 text-[11px] ${
                source === s.slug
                  ? "border-sky-500 bg-sky-500/10 text-sky-400"
                  : "border-border/60 text-muted-foreground hover:text-foreground"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <Sub>Producto</Sub>
        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Busca por nombre, tienda o carpeta…"
          className="w-full rounded-lg border border-border/60 bg-background px-3 py-2 text-xs"
        />
        {resultados.isFetching && (
          <p className="text-[10px] text-muted-foreground">Buscando…</p>
        )}
        {busca.trim().length >= 2 && (
          <div className="flex max-h-48 flex-wrap gap-1 overflow-y-auto">
            {(resultados.data?.items ?? []).map((p) => {
              const sel =
                elegido?.source === p.source &&
                elegido.folder === p.folder &&
                elegido.producto === p.producto;
              return (
                <button
                  key={`${p.source}|${p.folder}|${p.producto}`}
                  type="button"
                  onClick={() =>
                    setElegido({ source: p.source, folder: p.folder, producto: p.producto, titulo: p.titulo })
                  }
                  className={`max-w-full truncate rounded border px-2 py-1 text-[10px] ${
                    sel
                      ? "border-sky-500 bg-sky-500/10 text-sky-400"
                      : "border-border/60 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {p.folder} · {p.producto} — {p.titulo || "(sin textos)"}
                </button>
              );
            })}
            {resultados.data && !resultados.data.items.length && (
              <p className="text-[10px] text-muted-foreground">Nada con ese nombre.</p>
            )}
          </div>
        )}
        {elegido && (
          <p className="break-words rounded-lg border border-emerald-500/40 bg-emerald-500/[0.06] px-2 py-1.5 text-[11px]">
            ✓ {elegido.titulo || elegido.producto}{" "}
            <span className="text-[10px] text-muted-foreground">
              ({elegido.folder} · {elegido.producto})
            </span>
          </p>
        )}
      </Caja>

      <CatalogoCarruseles
        onUsar={(p) => {
          setSource(p.source);
          setElegido({ source: p.source, folder: p.folder, producto: p.producto, titulo: p.titulo });
          if (p.carrusel_url) setUrl(p.carrusel_url);
        }}
      />

      <Paso
        n={1}
        color="violeta"
        titulo="Pega el carrusel viral"
        hint="Enlace de TikTok de un carrusel de FOTOS (no vídeo). Una llamada de IA, ~1 minuto, hasta 12 diapositivas."
      >
        <div className="flex flex-col gap-1.5 sm:flex-row">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tiktok.com/@cuenta/photo/…"
            className="min-w-0 flex-1 rounded-lg border border-border/60 bg-background px-3 py-2 text-xs"
          />
          <button
            type="button"
            disabled={!elegido || !url.trim() || replicar.isPending}
            onClick={analizar}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
          >
            {replicar.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {replicar.isPending ? "Analizando…" : "Analizar y adaptar"}
          </button>
        </div>
        {esAdmin && otros.length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-muted-foreground">Para:</span>
            {[{ username: "", nombre: "Mí" }, ...otros].map((u) => (
              <button
                key={u.username || "yo"}
                type="button"
                onClick={() => setPara(u.username)}
                className={`rounded border px-2 py-1 text-[10px] ${
                  para === u.username
                    ? "border-sky-500 bg-sky-500/10 text-sky-400"
                    : "border-border/60 text-muted-foreground hover:text-foreground"
                }`}
              >
                {u.nombre || u.username}
              </button>
            ))}
          </div>
        )}
        {!elegido && (
          <p className="text-[10px] text-amber-400">Elige antes el producto (arriba).</p>
        )}
      </Paso>

      <Caja
        icono="🗂️"
        titulo="Tus carruseles"
        hint="Los últimos que has replicado. Toca uno para abrirlo."
        extra={lista.data ? `${lista.data.items.length}` : undefined}
      >
        <div className="flex flex-wrap gap-1">
          {(lista.data?.items ?? []).map((c) => {
            const completo = c.diapositivas > 0 && c.hechas >= c.diapositivas;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => setAbierto(c.id)}
                className={`max-w-full truncate rounded border px-2 py-1 text-[10px] ${
                  abierto === c.id
                    ? "border-sky-500 bg-sky-500/10 text-sky-400"
                    : "border-border/60 text-muted-foreground hover:text-foreground"
                }`}
              >
                {completo ? "✓ " : ""}
                {c.subido ? "📤 " : ""}
                {c.producto?.titulo || c.producto?.producto}
                <span
                  className={`ml-1 rounded-full px-1.5 text-[9px] font-semibold ${
                    completo ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"
                  }`}
                >
                  {c.hechas}/{c.diapositivas}
                </span>
              </button>
            );
          })}
          {lista.data && !lista.data.items.length && (
            <p className="text-[10px] text-muted-foreground">Aún no has replicado ninguno.</p>
          )}
        </div>
      </Caja>

      {abierto && doc.isLoading && (
        <p className="text-[11px] text-muted-foreground">Cargando el carrusel…</p>
      )}
      {doc.data && <CarruselAbierto doc={doc.data} />}
      {doc.data && (
        <ReplicarOtraVez
          doc={doc.data}
          esAdmin={esAdmin}
          otros={otros.map((u) => ({ username: u.username, nombre: u.nombre }))}
          onHecho={(id, paraQuien) => {
            if (!paraQuien) setAbierto(id);
          }}
        />
      )}
    </div>
  );
}

function CarruselAbierto({ doc }: { doc: CarruselReplica }) {
  return (
    <>
      {!doc.apto && (
        <p className="rounded-xl border border-amber-500/40 bg-amber-500/[0.06] p-3 text-[11px] text-amber-400">
          La IA cree que este carrusel no encaja con el producto: {doc.motivo_no_apto || "sin motivo"}.
        </p>
      )}
      <Paso
        n={2}
        color="fucsia"
        titulo="Genera las fotos en Flow y súbelas"
        hint={`Una por diapositiva, en formato ${doc.formato}. Donde dice «con foto del producto», adjunta su foto limpia en Flow. Al subirla, la app le pone el texto.`}
        extra={`${doc.hechas}/${doc.total}`}
      >
        {doc.original?.tema && (
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            <b>De qué va:</b> {doc.original.tema}
            {doc.original.por_que_funciona ? ` · ${doc.original.por_que_funciona}` : ""}
          </p>
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {doc.diapositivas.map((d) => (
            <TarjetaDiapositiva key={d.n} id={doc.id} d={d} />
          ))}
        </div>
      </Paso>
      <Paso
        n={3}
        color="azul"
        titulo="Descarga el carrusel"
        hint="Las fotos con su texto, una a una y en orden (01, 02…). El caption, con su botón. También está en Mis tandas."
        extra={doc.completo ? "✓ completo" : `${doc.hechas}/${doc.total}`}
      >
        <div className="flex flex-wrap gap-1.5">
          <BotonFotosEnOrden id={doc.id} disabled={!doc.hechas} className="px-3 py-2 text-xs" />
          <CopyChip label="Caption" text={doc.caption} siempre />
          <CopyChip label="Hashtags" text={doc.hashtags.join(" ")} />
        </div>
        <MusicaCarrusel musica={doc.musica} />
        {!doc.completo && doc.hechas > 0 && (
          <p className="text-[10px] text-amber-400">
            Faltan {doc.total - doc.hechas} fotos: se bajan solo las que ya están.
          </p>
        )}
      </Paso>
    </>
  );
}

function TarjetaDiapositiva({ id, d }: { id: string; d: Diapositiva }) {
  const subir = useSubirFotoCarrusel(id);
  const cambiar = useTextoCarrusel(id);
  const [texto, setTexto] = useState(d.texto);
  useEffect(() => setTexto(d.texto), [d.texto]);

  const copiarPrompt = async () => {
    try {
      await navigator.clipboard.writeText(d.prompt_imagen);
      toast.success("Prompt copiado");
    } catch {
      toast.error("No se pudo copiar");
    }
  };

  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-card p-2">
      <div className="flex items-center gap-1.5">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold">
          {d.n}
        </span>
        <span className="rounded-full bg-violet-500/20 px-1.5 text-[9px] font-semibold text-violet-400">
          {ROL[d.rol] ?? d.rol}
        </span>
        {d.usa_foto_producto && (
          <span className="rounded-full bg-amber-500/20 px-1.5 text-[9px] font-semibold text-amber-400">
            con foto del producto
          </span>
        )}
        {d.lista && (
          <span className="ml-auto rounded-full bg-emerald-500/20 px-1.5 text-[9px] font-semibold text-emerald-400">
            ✓ lista
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <figure className="space-y-0.5">
          {d.tiene_original ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={urlFotoCarrusel(id, d.n, "orig")}
              alt={`Original ${d.n}`}
              loading="lazy"
              className="aspect-[3/4] w-full rounded-lg object-cover"
            />
          ) : (
            <div className="aspect-[3/4] w-full rounded-lg bg-muted" />
          )}
          <figcaption className="text-center text-[9px] text-muted-foreground">Original</figcaption>
        </figure>
        <figure className="space-y-0.5">
          {d.tiene_imagen ? (
            <a href={urlFotoCarrusel(id, d.n, "final", d.version, true)}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={urlFotoCarrusel(id, d.n, "final", d.version)}
                alt={`Nuestra ${d.n}`}
                loading="lazy"
                className="aspect-[3/4] w-full rounded-lg object-cover"
              />
            </a>
          ) : (
            <div className="flex aspect-[3/4] w-full items-center justify-center rounded-lg border border-dashed border-border/60 text-[10px] text-muted-foreground">
              Sin foto
            </div>
          )}
          <figcaption className="text-center text-[9px] text-muted-foreground">La nuestra</figcaption>
        </figure>
      </div>
      {d.texto_original && (
        <p className="break-words text-[10px] text-muted-foreground">
          <b>Original:</b> {d.texto_original}
        </p>
      )}
      <div className="space-y-1">
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={2}
          placeholder="(sin texto)"
          className="w-full rounded-lg border border-border/60 bg-background px-2 py-1 text-[11px]"
        />
        {texto !== d.texto && (
          <button
            type="button"
            disabled={cambiar.isPending}
            onClick={() =>
              cambiar.mutate(
                { n: d.n, texto },
                { onError: (e) => toast.error(e.message), onSuccess: () => toast.success("Texto guardado") },
              )
            }
            className="rounded-lg border border-violet-500/50 px-2 py-1 text-[10px] font-semibold text-violet-400"
          >
            {cambiar.isPending ? "Guardando…" : "Guardar texto"}
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <button type="button" className={BTN_PROMPT} disabled={!d.prompt_imagen} onClick={copiarPrompt}>
          Prompt imagen
        </button>
        <label
          className={`flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-fuchsia-500/50 px-3 py-2 text-xs font-semibold text-fuchsia-400 hover:bg-fuchsia-500/10 ${
            subir.isPending ? "pointer-events-none opacity-50" : ""
          }`}
        >
          {subir.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
          {d.tiene_imagen ? "Cambiar foto" : "Subir foto"}
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file)
                subir.mutate({ n: d.n, file }, { onError: (err) => toast.error(err.message) });
            }}
          />
        </label>
      </div>
    </div>
  );
}

/** Alta de producto + catálogo COMPARTIDO «🖼️ Carruseles virales»: lo que se
 *  da de alta aquí lo ven todos los usuarios y cualquiera puede replicarlo. */
function CatalogoCarruseles({ onUsar }: { onUsar: (p: ProductoCarrusel) => void }) {
  const catalogo = useCatalogoCarrusel();
  const crear = useCrearProductoCarrusel();
  const releer = useReleerTextosCarrusel();
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const [productUrl, setProductUrl] = useState("");
  const [viralUrl, setViralUrl] = useState("");
  const [abierta, setAbierta] = useState(false);
  const items = catalogo.data?.items ?? [];

  const guardar = () => {
    if (!limpia || !ficha || !productUrl.trim()) return;
    crear.mutate(
      { limpia, ficha, product_url: productUrl.trim(), carrusel_url: viralUrl.trim() },
      {
        onSuccess: (p) => {
          setLimpia(null);
          setFicha(null);
          setProductUrl("");
          setViralUrl("");
          setAbierta(false);
          if (p.aviso) toast.warning(p.aviso);
          else toast.success(`Producto guardado: ${p.titulo || p.producto}`);
          onUsar(p);
        },
        onError: (e) => toast.error(e.message),
      },
    );
  };

  const inputFile = (label: string, f: File | null, set: (f: File | null) => void) => (
    <label className="flex min-w-0 cursor-pointer items-center gap-1.5 rounded-lg border border-dashed border-border/60 px-2 py-2 text-[11px] text-muted-foreground hover:text-foreground">
      <Upload className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{f ? `✓ ${f.name}` : label}</span>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(e) => set(e.target.files?.[0] ?? null)}
      />
    </label>
  );

  return (
    <Caja
      icono="🖼️"
      titulo="Carruseles virales"
      hint="Catálogo compartido: un producto que no está en el POV BOF se da de alta aquí y lo ven todos."
      extra={catalogo.data ? `${items.length}` : undefined}
    >
      {!abierta ? (
        <button
          type="button"
          onClick={() => setAbierta(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 px-3 py-2 text-xs font-semibold text-violet-400 hover:bg-violet-500/10 sm:w-auto"
        >
          <Plus className="h-3.5 w-3.5" /> Dar de alta un producto
        </button>
      ) : (
        <div className="space-y-1.5 rounded-lg border border-violet-500/40 bg-violet-500/[0.04] p-2">
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {inputFile("Foto limpia del producto", limpia, setLimpia)}
            {inputFile("Captura de la ficha (título, precio)", ficha, setFicha)}
          </div>
          <input
            value={productUrl}
            onChange={(e) => setProductUrl(e.target.value)}
            placeholder="URL del producto en TikTok Shop"
            className="w-full rounded-lg border border-border/60 bg-background px-3 py-2 text-xs"
          />
          <input
            value={viralUrl}
            onChange={(e) => setViralUrl(e.target.value)}
            placeholder="Enlace del carrusel viral (opcional)"
            className="w-full rounded-lg border border-border/60 bg-background px-3 py-2 text-xs"
          />
          <div className="flex flex-col gap-1.5 sm:flex-row">
            <button
              type="button"
              disabled={!limpia || !ficha || !productUrl.trim() || crear.isPending}
              onClick={guardar}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
            >
              {crear.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {crear.isPending ? "Guardando y leyendo la ficha…" : "Guardar producto"}
            </button>
            <button
              type="button"
              onClick={() => setAbierta(false)}
              className="rounded-lg border border-border/60 px-3 py-2 text-xs text-muted-foreground"
            >
              Cancelar
            </button>
          </div>
          <p className="text-[10px] text-muted-foreground">
            La app lee el título, la tienda y el precio de la captura (una llamada de IA).
          </p>
        </div>
      )}
      {items.length > 0 && (
        <div className="max-h-56 space-y-1 overflow-y-auto">
          {items.map((p) => (
            <div
              key={`${p.folder}|${p.producto}`}
              className="flex items-center gap-1.5 rounded-lg border border-border/60 px-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-medium">{p.titulo || "(sin textos)"}</p>
                <p className="truncate text-[10px] text-muted-foreground">
                  {p.folder} · {p.producto}
                  {p.tienda ? ` · ${p.tienda}` : ""}
                  {p.creado_por ? ` · de ${p.creado_por}` : ""}
                  {p.carrusel_url ? " · 🔗 viral" : ""}
                </p>
              </div>
              {!p.titulo && (
                <button
                  type="button"
                  disabled={releer.isPending}
                  onClick={() =>
                    releer.mutate(
                      { folder: p.folder, producto: p.producto },
                      { onError: (e) => toast.error(e.message), onSuccess: () => toast.success("Textos leídos") },
                    )
                  }
                  className="shrink-0 rounded border border-amber-500/50 px-2 py-1 text-[10px] text-amber-400 disabled:opacity-40"
                >
                  Leer textos
                </button>
              )}
              <button
                type="button"
                onClick={() => onUsar(p)}
                className="shrink-0 rounded border border-sky-500/50 px-2 py-1 text-[10px] font-semibold text-sky-400 hover:bg-sky-500/10"
              >
                Usar
              </button>
            </div>
          ))}
        </div>
      )}
    </Caja>
  );
}

/** Replicar el MISMO carrusel viral + producto otra vez: para uno mismo
 *  (otros textos) o, si eres admin, para otro usuario. Vuelve a llamar a la IA. */
function ReplicarOtraVez({
  doc, esAdmin, otros, onHecho,
}: {
  doc: CarruselReplica;
  esAdmin: boolean;
  otros: { username: string; nombre: string }[];
  onHecho: (id: string, para: string) => void;
}) {
  const otra = useReplicarOtraVez();
  const lanzar = (para: string) =>
    otra.mutate(
      { id: doc.id, para },
      {
        onSuccess: (d) => {
          toast.success(para ? `Replicado para ${para}` : "Replicado otra vez");
          onHecho(d.id, para);
        },
        onError: (e) => toast.error(e.message),
      },
    );
  const destinos = [{ username: "", nombre: "Mí (otra versión)" }, ...(esAdmin ? otros : [])];
  return (
    <Caja
      icono="🔁"
      titulo="Replicar otra vez"
      hint={
        esAdmin
          ? "El mismo carrusel viral con el mismo producto, para otra cuenta. Textos nuevos (una llamada de IA)."
          : "El mismo carrusel viral con el mismo producto, con textos nuevos (una llamada de IA)."
      }
    >
      {doc.replica_de && (
        <p className="text-[10px] text-muted-foreground">Copiado de otra réplica ({doc.replica_de}).</p>
      )}
      <div className="flex flex-wrap gap-1.5">
        {destinos.map((u) => (
          <button
            key={u.username || "yo"}
            type="button"
            disabled={otra.isPending}
            onClick={() => lanzar(u.username)}
            className="flex items-center gap-1.5 rounded-lg border border-violet-500/50 px-3 py-2 text-xs text-violet-400 hover:bg-violet-500/10 disabled:opacity-40"
          >
            {otra.isPending && otra.variables?.para === u.username ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Repeat className="h-3.5 w-3.5" />
            )}
            {u.username ? `Para ${u.nombre || u.username}` : u.nombre}
          </button>
        ))}
      </div>
    </Caja>
  );
}
