"use client";

import {
  Clapperboard,
  Download,
  Image as ImageIcon,
  Loader2,
  Sparkles,
  Upload,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { nombreDescarga } from "@/lib/descargas";
import { useEstadoDeUsuario } from "@/lib/hooks/useEstadoRecordado";
import {
  buildCleanPhotoDownloadUrl,
  useFolders,
  useHashtags,
  useSources,
} from "@/lib/queries/nichoPovBof";
import {
  buildVideoUGCUrl,
  subirClipUGC,
  useConfigUGC,
  useEscenasLote,
  useEstadoUGC,
  useLimpiarClipsUGC,
  useMontarUGC,
  useProductosUGC,
} from "@/lib/queries/nichoGeneral";
import type {
  ConfigUGCResponse,
  OpcionUGC,
  ProductoUGC,
} from "@/lib/types/nichoGeneral";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { Caja, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { MontadoEl } from "@/components/tiktok-shop-ai-pro/MontadoEl";
import { VideoModal } from "@/components/ui/video-modal";

/** Nicho General · UGC — el anuncio de TRES clips.
 *
 *  Se parece a las demás pantallas de nicho a propósito (ver `UI_NICHOS.md`) y
 *  solo cambia en lo que este formato tiene distinto:
 *
 *  - Se elige GANCHO y DURACIÓN, y las dos cosas separan el trabajo: el guion
 *    de 8 s no es el de 10 recortado, así que son anuncios distintos con sus
 *    clips y su vídeo.
 *  - Cada producto trae SEIS textos que copiar (tres fotos y tres vídeos), en
 *    dos bloques para no confundirlos.
 *  - Los clips se adjuntan TODOS DE GOLPE y sin decir cuál es cuál: el montaje
 *    los ordena escuchándolos.
 */
/** El color de cada nicho, para reconocerlo de un vistazo en la tarjeta y en
 *  los botones de descarga. Las clases van completas a propósito: Tailwind no
 *  detecta las que se arman concatenando y las quitaría del bundle. */
const COLOR_NICHO: Record<string, string> = {
  belleza: "border-pink-500/50 bg-pink-500/10 text-pink-400",
  hogar: "border-amber-500/50 bg-amber-500/10 text-amber-500",
  exterior: "border-emerald-500/50 bg-emerald-500/10 text-emerald-500",
  tech: "border-sky-500/50 bg-sky-500/10 text-sky-400",
  fitness: "border-orange-500/50 bg-orange-500/10 text-orange-400",
  bebe: "border-violet-500/50 bg-violet-500/10 text-violet-400",
  viaje: "border-cyan-500/50 bg-cyan-500/10 text-cyan-400",
  generico: "border-border/60 bg-muted text-muted-foreground",
};

export function PantallaUGC() {
  const sources = useSources();
  const cfg = useConfigUGC();
  const [source, setSource] = useEstadoDeUsuario("ugc:source", "aleatorios_2");
  const [folder, setFolder] = useEstadoDeUsuario("ugc:folder", "");
  const [gancho, setGancho] = useEstadoDeUsuario("ugc:gancho", "dolor");
  const [duracion, setDuracion] = useEstadoDeUsuario("ugc:duracion", "10");

  const folders = useFolders(source);
  const carpetas = folders.data?.items ?? [];
  useEffect(() => {
    if (!carpetas.length) return;
    if (!carpetas.some((c) => c.name === folder)) setFolder(carpetas[0]!.name);
  }, [carpetas, folder, setFolder]);

  const productos = useProductosUGC(source, folder, gancho, duracion);
  const items = productos.data?.items ?? [];
  const conEscenas = items.filter((p) => p.escenas.length > 0).length;
  const conVideo = items.filter((p) => p.video_path).length;

  const escenasLote = useEscenasLote();

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Clapperboard className="h-5 w-5 shrink-0 text-emerald-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Nicho General · UGC</h1>
            <p className="text-[11px] text-muted-foreground">
              Un anuncio de TRES clips: dolor o gancho → producto → urgencia y
              CTA
            </p>
          </div>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Cada escena se genera aparte y se pegan al final. La continuidad sale
          del personaje, del escenario y de que la voz sea la misma en las
          tres — por eso los clips hay que generarlos con la misma referencia.
        </p>
      </header>

      <Caja
        icono="📁"
        titulo="Dónde trabajas"
        hint="El catálogo y la carpeta son los del POV BOF; el gancho y la duración, de este nicho."
        extra={`${conVideo}/${items.length} con vídeo`}
      >
        <Sub>Catálogo</Sub>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => setSource(s.slug)}
              className={`break-words leading-tight rounded-lg border px-2 py-2 text-[11px] transition sm:text-xs ${
                source === s.slug
                  ? "border-emerald-500 bg-emerald-500/10 font-semibold text-emerald-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <Sub>Gancho</Sub>
        {/* Los dos enfoques del curso: el documento es el mismo salvo las
            escenas 1 y 2, pero el anuncio que sale no se parece en nada. */}
        <div className="grid grid-cols-2 gap-1.5">
          {(cfg.data?.ganchos ?? []).map((g) => (
            <button
              key={g.clave}
              type="button"
              onClick={() => setGancho(g.clave)}
              className={`rounded-lg border px-2 py-1.5 text-[11px] transition ${
                gancho === g.clave
                  ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-400"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {g.label}
            </button>
          ))}
        </div>

        <Sub>Duración de cada clip</Sub>
        <div className="grid grid-cols-2 gap-1.5">
          {(cfg.data?.duraciones ?? []).map((d) => (
            <button
              key={d.clave}
              type="button"
              onClick={() => setDuracion(d.clave)}
              className={`rounded-lg border px-2 py-1.5 text-[11px] transition ${
                duracion === d.clave
                  ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-400"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          Cada combinación guarda lo suyo: en 8 segundos no cabe lo mismo que
          en 10, así que el guion se escribe entero para esa duración y el
          vídeo es otro. Cambiar aquí no pisa lo que ya tengas hecho.
        </p>

        <Sub>Carpetas</Sub>
        <div className="mt-1 flex flex-wrap gap-1">
          {carpetas.map((c) => (
            <button
              key={c.name}
              type="button"
              onClick={() => setFolder(c.name)}
              className={`break-words leading-tight rounded border px-2 py-1 text-[10px] transition ${
                folder === c.name
                  ? c.completed
                    ? "border-emerald-500 bg-emerald-500/15 font-semibold text-emerald-500"
                    : "border-sky-500 bg-sky-500/15 font-semibold text-sky-400"
                  : c.completed
                    ? "border-emerald-500/40 text-emerald-500"
                    : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {c.completed && "✓ "}
              {c.name}
              {/* Con ficha SOBRE EL TOTAL, igual que en el POV BOF: un "9" solo
                  no dice si faltan enlaces, y eso decide si merece abrirla. */}
              {!!c.total && (
                <span
                  title={`${c.con_url ?? 0} de ${c.total} con la ficha enlazada`}
                  className={`ml-1 rounded-full px-1 py-px text-[9px] font-semibold ${
                    (c.con_url ?? 0) >= c.total
                      ? "bg-emerald-500/15 text-emerald-500"
                      : "bg-amber-500/15 text-amber-500"
                  }`}
                >
                  {(c.con_url ?? 0) >= c.total ? c.total : `${c.con_url ?? 0}/${c.total}`}
                </span>
              )}
            </button>
          ))}
        </div>
        <p className="text-xs font-medium sm:text-sm">
          {items.length} producto(s) · {conEscenas} con escenas · {conVideo} con vídeo
        </p>
      </Caja>

      <Paso
        n={1}
        color="violeta"
        titulo="Escribir las escenas"
        hint="Lee la ficha del producto y escribe las tres escenas: sus prompts de imagen, sus prompts de vídeo y lo que se dice en cada una."
        extra={`${conEscenas}/${items.length}`}
      >
        <button
          type="button"
          disabled={escenasLote.isPending || !folder}
          onClick={() =>
            escenasLote.mutate(
              { source, folder, gancho, duracion },
              {
                onSuccess: () => toast.success("A la cola: mira el progreso arriba"),
                onError: (e) =>
                  toast.error(e instanceof ApiError ? e.message : String(e)),
              },
            )
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-700 disabled:opacity-50"
        >
          <Sparkles className="h-3.5 w-3.5" />
          Escribir las escenas que falten ({items.length - conEscenas})
        </button>
        <button
          type="button"
          disabled={escenasLote.isPending || !folder}
          onClick={() =>
            escenasLote.mutate(
              { source, folder, gancho, duracion, rehacer: true },
              { onSuccess: () => toast.success("Rehaciendo todas") },
            )
          }
          className="w-full rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:border-foreground/30"
        >
          Rehacer todas las de esta carpeta
        </button>
      </Paso>

      <Paso
        n={2}
        color="fucsia"
        titulo="Generar los clips fuera"
        hint="Con el personaje y la foto del producto: primero la imagen de cada escena, y sobre cada imagen, su vídeo."
      >
        {/* El personaje se hace UNA vez por persona, no por producto: busca a
            alguien en Pinterest que pegue con el tipo de producto, pásale su
            foto a ChatGPT con este prompt y lleva lo que devuelva a Flow. Esa
            imagen es la que se adjunta luego en todas las escenas. */}
        <CopyChip
          label="🧍 Prompt del personaje (una vez por persona)"
          text={cfg.data?.prompt_personaje ?? ""}
          siempre
        />
        {/* Lo primero de todo: las fotos de los productos, que es lo que se
            adjunta en Flow junto al personaje. De la carpeta entera, como en
            los demás nichos: se bajan las diez y se trabajan seguidas. */}
        <BajarFotos
          items={items}
          source={source}
          folder={folder}
          nichos={cfg.data?.nichos ?? []}
        />
        <ol className="space-y-1 text-[11px] leading-relaxed text-muted-foreground">
          <li>
            0. ¿Aún no tienes personaje? Busca a alguien en{" "}
            <a
              href="https://es.pinterest.com/"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Pinterest
            </a>{" "}
            que pegue con el producto, pásale su foto a ChatGPT con el prompt de
            arriba y mete el resultado en Flow. Sale de cuerpo entero sobre
            fondo blanco y vale para todas sus escenas.
          </li>
          <li>
            1. En Flow, con el <strong>personaje</strong> y la foto del producto
            adjuntos, pega el prompt de <strong>Foto 1</strong>. Repite con la 2
            y la 3.
          </li>
          <li>
            2. Sobre cada foto generada, pega su prompt de{" "}
            <strong>Vídeo</strong>. Salen los tres clips ya hablados.
          </li>
          <li>
            3. Vuelve aquí y adjúntalos todos de golpe: el orden lo pone el
            montaje, no hace falta que los renombres.
          </li>
        </ol>
      </Paso>

      <Paso
        n={3}
        color="azul"
        titulo="Descargar lo ya montado"
        hint="Los anuncios listos para subir a TikTok. Se bajan en el orden en que los ves."
        extra={`${conVideo}/${items.length}`}
      >
        <BajarVideos
          items={items}
          source={source}
          folder={folder}
          gancho={gancho}
          duracion={duracion}
        />
      </Paso>

      <section className="space-y-2">
        <p className="text-sm font-semibold">Productos</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {items.map((p) => (
            <TarjetaUGC
              key={p.producto}
              producto={p}
              source={source}
              folder={folder}
              gancho={gancho}
              duracion={duracion}
              cfg={cfg.data}
            />
          ))}
        </div>
        {!items.length && !productos.isLoading && (
          <p className="rounded-lg border border-border/60 px-2.5 py-2 text-[11px] text-muted-foreground">
            Esta carpeta no tiene textos extraídos todavía. Sácalos en el Nicho
            POV BOF o en Configuración: valen para todos los nichos.
          </p>
        )}
      </section>
    </div>
  );
}

function TarjetaUGC({
  producto,
  source,
  folder,
  gancho,
  duracion,
  cfg,
}: {
  producto: ProductoUGC;
  source: string;
  folder: string;
  gancho: string;
  duracion: string;
  cfg?: ConfigUGCResponse;
}) {
  const qc = useQueryClient();
  const hashtags = useHashtags().data ?? [];
  const montar = useMontarUGC();
  const rehacer = useEscenasLote();
  const limpiar = useLimpiarClipsUGC();
  const estado = useEstadoUGC();
  const [subiendo, setSubiendo] = useState("");
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);
  const [verMas, setVerMas] = useState(false);
  const [pidiendoAlt, setPidiendoAlt] = useState(false);
  const [enEscaparate, setEnEscaparate] = useState(producto.en_escaparate);
  const [subido, setSubido] = useState(producto.uploaded);
  const [vendio, setVendio] = useState(producto.sold);
  useEffect(() => {
    setEnEscaparate(producto.en_escaparate);
    setSubido(producto.uploaded);
    setVendio(producto.sold);
  }, [producto.en_escaparate, producto.uploaded, producto.sold]);

  const clave = { source, folder, producto: producto.producto, gancho, duracion };
  // Con qué sexo se escribe la versión PRINCIPAL de este nicho. Lo dice el
  // backend y no la clave del personaje, que ya lleva dentro la elección
  // manual: si no, al elegir hombre parecía que el principal era el hombre y
  // no se veía que la versión alternativa era justo esa.
  const sexoDelNicho =
    (cfg?.nichos ?? []).find((n) => n.clave === (producto.nicho || "generico"))
      ?.sexo ?? "mujer";
  // Los guiones que se copian son los de la versión ELEGIDA. Sin esto, al
  // pedir la de hombre se copiaba su personaje pero los prompts seguían siendo
  // los de la mujer: el vídeo saldría con un tío diciendo el guion de ella.
  const usandoAlt =
    Boolean(producto.personaje_sexo) &&
    producto.personaje_sexo !== sexoDelNicho &&
    producto.escenas_alt.length > 0;
  const escenas = usandoAlt ? producto.escenas_alt : producto.escenas;
  // Lo que cabe hablando en ese clip. Sale de la proporción del curso —170
  // caracteres para 10 s— y es lo que decide si una frase se corta.
  const tope = duracion === "8" ? 136 : 170;
  const fichaPersonaje =
    (cfg?.personajes ?? []).find((x) => x.clave === producto.personaje_clave)?.ficha ?? "";

  async function adjuntar(lista: File[]) {
    if (!lista.length) {
      toast.error("El selector no devolvió ningún vídeo.");
      return;
    }
    toast.info(`Subiendo ${lista.length} clip(s)…`);
    // De uno en uno y esperando: cada subida escribe en el mismo documento y
    // lanzarlas a la vez solo se estorban.
    for (const [i, f] of lista.entries()) {
      setSubiendo(`${i + 1}/${lista.length}`);
      try {
        await subirClipUGC(f, clave, (pct) =>
          setSubiendo(`${i + 1}/${lista.length} · ${pct}%`),
        );
      } catch (e) {
        toast.error(e instanceof Error ? e.message : String(e));
        break;
      }
    }
    setSubiendo("");
    // Sin esto la tarjeta no se entera: los clips se guardaban bien pero el
    // contador seguía a cero y "Montar anuncio" apagado, así que parecía que
    // cada subida pisaba a la anterior.
    await qc.invalidateQueries({ queryKey: ["nicho-general", "productos"] });
    toast.success(`${lista.length} clip(s) subidos`);
  }

  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex gap-2">
        {/* La miniatura se pide por producto, no por `file_id`: ese campo no
            siempre está en los textos guardados y la foto se quedaba en
            blanco. Toca para verla grande. */}
        <button
          type="button"
          onClick={() => setVerFoto(true)}
          className="shrink-0"
          title="Ver las fotos del producto"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={buildCleanPhotoDownloadUrl(source, folder, producto.producto, "limpia", 120)}
            alt=""
            className="h-14 w-14 rounded-md border border-border/60 object-cover"
          />
        </button>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-xs font-semibold sm:text-sm">
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">
              {producto.producto}
            </span>
            <span className="min-w-0 break-words leading-tight">
              {producto.titulo || "— sin textos todavía —"}
            </span>
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px]">
            {producto.precio && (
              <span className="font-mono font-semibold">{producto.precio} €</span>
            )}
            <span
              className={`rounded px-1.5 py-0.5 font-semibold ${
                producto.plazos
                  ? "bg-violet-500/15 text-violet-400"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {producto.plazos ? "💳 con plazos" : "sin plazos"}
            </span>
            {escenas.length > 0 && (
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-semibold text-emerald-500">
                {escenas.length} escenas
              </span>
            )}
            {/* El nicho, con su color: en una carpeta de diez mezclados es lo
                que dice de un vistazo qué personaje toca en cada uno. */}
            <span
              className={`rounded border px-1.5 py-0.5 font-semibold ${
                COLOR_NICHO[producto.nicho || "generico"] ?? COLOR_NICHO.generico
              }`}
            >
              {(cfg?.nichos ?? []).find((n) => n.clave === producto.nicho)?.label ??
                "Sin clasificar"}
            </span>
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {/* El caption se copia YA con los emojis y los hashtags pegados: es lo
            que se pega tal cual en TikTok, igual que en el POV BOF. */}
        <CopyChip
          label="✍️ Caption"
          text={
            producto.caption
              ? [producto.caption, producto.emojis, hashtags.join(" ")]
                  .filter(Boolean)
                  .join(" ")
              : ""
          }
          siempre
        />
        <BotonUrl url={producto.product_url} />
        <button
          type="button"
          onClick={() => setVerMas((v) => !v)}
          className="rounded-md border border-border/60 px-2 py-1 text-[11px] text-muted-foreground transition hover:border-foreground/30"
        >
          más {verMas ? "▴" : "▾"}
        </button>
      </div>
      {verMas && (
        <div className="flex flex-wrap gap-1">
          <CopyChip label="🔎 Título TikTok" text={producto.titulo_tiktok_completo} siempre />
          <CopyChip label="🏪 Tienda" text={producto.tienda} siempre />
          <CopyChip label="🗣️ Voz" text={producto.voz} />
        </div>
      )}

      {/* El personaje, en dos botones: se copia el prompt del hombre o el de
          la mujer de ese nicho y se pega en Flow. No hay que elegir nada antes
          — copiar ES elegir.

          El que está marcado es el que cuadra con el guion ya escrito: la
          identidad vocal va DENTRO de los prompts de vídeo, así que copiar el
          otro deja un tío hablando con voz de mujer. Por eso, al copiar el que
          no toca, se avisa de que hay que rehacer. */}
      <div className="space-y-1 rounded-lg border border-border/60 p-2">
        <div className="flex items-center gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            🧍 Personaje
          </p>
          {/* El nicho lo pone la IA; se corrige aquí cuando se equivoca. */}
          <select
            value={producto.nicho || "generico"}
            onChange={(e) =>
              estado.mutate(
                { ...clave, nicho: e.target.value, personaje: "" },
                { onError: (err) => toast.error(String(err)) },
              )
            }
            className="min-w-0 flex-1 rounded-md border border-border/60 bg-background px-2 py-0.5 text-[10px]"
          >
            {(cfg?.nichos ?? []).map((n) => (
              <option key={n.clave} value={n.clave}>
                {n.label}
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-1">
          {(["mujer", "hombre"] as const).map((sx) => {
            const clavePers = `${producto.nicho || "generico"}_${sx}`;
            const ficha =
              (cfg?.personajes ?? []).find((x) => x.clave === clavePers)?.ficha ?? "";
            // El que pega con el nicho ya está escrito; del otro solo hay
            // guiones si se pidieron para este producto.
            const esElPrincipal = sexoDelNicho === sx;
            const hecho = esElPrincipal
              ? escenas.length > 0
              : producto.escenas_alt.length > 0;
            return (
              <button
                key={sx}
                type="button"
                disabled={!ficha || pidiendoAlt}
                onClick={() => {
                  if (hecho) {
                    navigator.clipboard.writeText(ficha);
                    // Copiar es elegir: los seis prompts de abajo pasan a ser
                    // los de esta versión.
                    if ((producto.personaje_sexo || sexoDelNicho) !== sx) {
                      estado.mutate({ ...clave, personaje_sexo: sx });
                    }
                    toast.success(`Prompt de ${sx} copiado`);
                    return;
                  }
                  // Aún no existe esa versión: se pide solo para este producto.
                  setPidiendoAlt(true);
                  rehacer.mutate(
                    {
                      source, folder, gancho, duracion,
                      productos: [producto.producto], sexo: sx,
                    },
                    {
                      onSuccess: () =>
                        toast.success(
                          `Escribiendo la versión de ${sx} de este producto`,
                        ),
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                      onSettled: () => setPidiendoAlt(false),
                    },
                  );
                }}
                className={`flex items-center justify-center gap-1 rounded-md border px-2 py-1.5 text-[11px] transition disabled:opacity-30 ${
                  hecho
                    ? esElPrincipal
                      ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-400"
                      : "border-border/60 text-foreground hover:border-foreground/40"
                    : "border-dashed border-border/60 text-muted-foreground hover:border-foreground/30"
                }`}
              >
                {sx === "mujer" ? "👩 Mujer" : "👨 Hombre"}
                {!ficha ? " (sin crear)" : hecho ? "" : " ✨"}
              </button>
            );
          })}
        </div>
        <p className="text-[10px] text-muted-foreground">
          El marcado es el que se escribió para este producto: cópialo y pégalo
          en Flow. El otro sale con ✨ — al tocarlo se escriben sus guiones (una
          llamada, solo de este producto) y luego ya se copia igual.
        </p>
      </div>

      {/* Los seis textos que se copian, en DOS bloques: primero se hacen las
          tres fotos y luego, sobre cada una, su vídeo. Mezclados en una fila
          es cuestión de tiempo pegar el de vídeo en el generador de imagen. */}
      {escenas.length > 0 ? (
        <>
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              <ImageIcon className="mr-1 inline h-3 w-3" />
              Fotos · en Flow, con el personaje y el producto
            </p>
            <div className="grid grid-cols-3 gap-1">
              {escenas.map((e) => (
                <CopyChip key={`i${e.n}`} label={`📸 Foto ${e.n}`} text={e.prompt_imagen} siempre />
              ))}
            </div>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              <Clapperboard className="mr-1 inline h-3 w-3" />
              Vídeos · sobre la foto de cada escena
            </p>
            <div className="grid grid-cols-3 gap-1">
              {escenas.map((e) => (
                <CopyChip key={`v${e.n}`} label={`🎬 Vídeo ${e.n}`} text={e.prompt_video} siempre />
              ))}
            </div>
            {/* Cuántos caracteres tiene cada guion: es lo que decide si cabe en
                el clip, y el propio curso lo hace contar. */}
            {/* Los caracteres de cada guion y, si alguno no cabe, el botón de
                rehacer SOLO este producto: por una escena larga no se vuelven
                a pagar las diez de la carpeta. */}
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[10px] text-muted-foreground">
                {escenas.map((e) => (
                  <span
                    key={e.n}
                    className={e.caracteres > tope * 1.15 ? "text-amber-500" : ""}
                  >
                    {e.n}: {e.caracteres} car.{" "}
                  </span>
                ))}
              </p>
              <button
                type="button"
                disabled={rehacer.isPending}
                onClick={() =>
                  rehacer.mutate(
                    {
                      source, folder, gancho, duracion,
                      rehacer: true, productos: [producto.producto],
                    },
                    {
                      onSuccess: () => toast.success("A la cola: solo este producto"),
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground transition hover:border-foreground/30"
              >
                ↻ rehacer
              </button>
            </div>
          </div>
        </>
      ) : (
        <p className="rounded-lg border border-dashed border-border/60 px-2.5 py-2 text-[11px] text-muted-foreground">
          Sin escenas todavía — dale al paso 1.
        </p>
      )}

      {/* La foto LIMPIA es la que se adjunta en Flow con el personaje, así que
          se baja desde la propia tarjeta como en los demás nichos. */}
      <a
        href={buildCleanPhotoDownloadUrl(source, folder, producto.producto, "limpia")}
        download={nombreDescarga("ugc", producto.producto) + ".jpg"}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30"
      >
        <Download className="h-3.5 w-3.5" /> Bajar la foto del producto
      </a>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30">
          {subiendo ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> {subiendo}
            </>
          ) : (
            <>
              <Upload className="h-3.5 w-3.5" /> Adjuntar clips
              {producto.clips.length > 0 && ` (${producto.clips.length})`}
            </>
          )}
          <input
            type="file"
            accept="video/*"
            multiple
            className="hidden"
            onChange={(e) => {
              // Los ficheros se copian ANTES de tocar el input: al ponerle
              // `value = ""` el navegador vacía su FileList, y si la subida
              // aún no los ha leído se queda sin nada que enviar — que es lo
              // que pasaba: se elegían los tres clips y no salía ninguna
              // petición.
              const elegidos = Array.from(e.target.files ?? []);
              e.target.value = "";
              void adjuntar(elegidos);
            }}
          />
        </label>
        <button
          type="button"
          disabled={!producto.clips.length || producto.montando || montar.isPending}
          onClick={() =>
            montar.mutate(clave, {
              onSuccess: () => toast.success("Montando: se ordenan solos"),
              onError: (e) =>
                toast.error(e instanceof ApiError ? e.message : String(e)),
            })
          }
          className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-40"
        >
          {producto.montando
            ? "Montando…"
            : producto.clips.length
              ? `Montar (${producto.clips.length})`
              : "Montar anuncio"}
        </button>
      </div>
      {producto.clips.length > 0 && !producto.montando && (
        <button
          type="button"
          onClick={() =>
            limpiar.mutate(clave, { onSuccess: () => toast.success("Clips vaciados") })
          }
          className="w-full rounded-lg border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-foreground/30"
        >
          Quitar los {producto.clips.length} clip(s) y volver a subirlos
        </button>
      )}

      {producto.video_path && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setVerVideo(true)}
              className="rounded-lg border border-emerald-500/60 px-3 py-1.5 text-[11px] text-emerald-500 transition hover:bg-emerald-500/10"
            >
              Ver vídeo
            </button>
            <a
              href={buildVideoUGCUrl(clave, true)}
              download={nombreDescarga("ugc", producto.producto) + ".mp4"}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30"
            >
              <Download className="h-3.5 w-3.5" /> Descargar
            </a>
          </div>
          <MontadoEl ts={producto.video_listo_at} />
        </>
      )}

      <div className="flex gap-1.5 border-t border-border/60 pt-2">
        {(
          [
            ["🏪 Escaparate", enEscaparate, setEnEscaparate, "en_escaparate", "sky"],
            ["📤 Subido", subido, setSubido, "uploaded", "sky"],
            ["💰 Vendió", vendio, setVendio, "sold", "emerald"],
          ] as const
        ).map(([label, valor, set, campo, color]) => (
          <button
            key={campo}
            type="button"
            onClick={() => {
              set(!valor);
              estado.mutate(
                { ...clave, [campo]: !valor },
                {
                  onError: (e) => {
                    set(valor);
                    toast.error(e instanceof ApiError ? e.message : String(e));
                  },
                },
              );
            }}
            className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
              valor
                ? color === "emerald"
                  ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                  : "border-sky-500 bg-sky-500/15 text-sky-500"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={`Producto ${producto.producto}`}
        urlLimpia={buildCleanPhotoDownloadUrl(source, folder, producto.producto, "limpia")}
        urlTitulo={buildCleanPhotoDownloadUrl(source, folder, producto.producto, "ficha")}
        urlDescarga={buildCleanPhotoDownloadUrl(source, folder, producto.producto, "limpia")}
      />

      <VideoModal
        open={verVideo}
        onOpenChange={setVerVideo}
        title={`Producto ${producto.producto}`}
        filename={`ugc_${producto.producto}.mp4`}
        videoUrl={producto.video_path ? buildVideoUGCUrl(clave) : null}
        downloadUrl={producto.video_path ? buildVideoUGCUrl(clave, true) : null}
        localPath={producto.video_path}
      />
    </div>
  );
}

/** Bajarse los anuncios ya montados de la carpeta, de uno en uno.
 *
 *  Con retardo entre descargas porque el navegador del móvil cancela las
 *  simultáneas — el mismo motivo que en el resto de nichos.
 */
function BajarVideos({
  items,
  source,
  folder,
  gancho,
  duracion,
}: {
  items: ProductoUGC[];
  source: string;
  folder: string;
  gancho: string;
  duracion: string;
}) {
  const [bajando, setBajando] = useState("");
  const conVideo = items.filter((p) => p.video_path);

  async function bajarTodos() {
    if (!conVideo.length) return;
    setBajando(`0/${conVideo.length}`);
    for (const [i, p] of conVideo.entries()) {
      setBajando(`${i + 1}/${conVideo.length}`);
      const a = document.createElement("a");
      a.href = buildVideoUGCUrl(
        { source, folder, producto: p.producto, gancho, duracion }, true,
      );
      a.download = nombreDescarga("ugc", p.producto) + ".mp4";
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < conVideo.length - 1) await new Promise((r) => setTimeout(r, 800));
    }
    setBajando("");
    toast.success(`${conVideo.length} vídeo(s) descargados`);
  }

  return (
    <button
      type="button"
      disabled={!conVideo.length || Boolean(bajando)}
      onClick={() => void bajarTodos()}
      className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-sky-500/60 px-3 py-2 text-[11px] text-sky-400 transition hover:bg-sky-500/10 disabled:opacity-40"
    >
      {bajando ? (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Bajando {bajando}
        </>
      ) : (
        <>
          <Download className="h-3.5 w-3.5" /> Vídeos ({conVideo.length})
        </>
      )}
    </button>
  );
}

/** Bajarse las fotos LIMPIAS de toda la carpeta.
 *
 *  Es lo que se adjunta en Flow con el personaje para sacar las tres escenas,
 *  así que se baja la carpeta entera de una vez y se trabaja seguida — igual
 *  que en el POV BOF y en Ropa. De una en una y con retardo: el navegador del
 *  móvil cancela las descargas simultáneas.
 */
function BajarFotos({
  items,
  source,
  folder,
  nichos,
}: {
  items: ProductoUGC[];
  source: string;
  folder: string;
  nichos: OpcionUGC[];
}) {
  const [bajando, setBajando] = useState("");
  // Los que tienen textos leídos: sin ellos el producto ni siquiera sale en la
  // lista, pero puede no tener foto limpia emparejada.
  const conFoto = items.filter((p) => p.clean_photo_id !== null);
  // Cuántas hay de cada nicho. Se baja por nicho porque se trabaja así: se
  // generan seguidas las que llevan el mismo personaje, igual que en el POV
  // BOF Largo se bajan juntas las de dos clips y las de tres.
  const porNicho = conFoto.reduce<Record<string, number>>((acc, p) => {
    const n = p.nicho || "generico";
    acc[n] = (acc[n] ?? 0) + 1;
    return acc;
  }, {});

  async function bajar(lista: ProductoUGC[], etiqueta: string) {
    if (!lista.length) return;
    setBajando(`0/${lista.length}`);
    for (const [i, p] of lista.entries()) {
      setBajando(`${i + 1}/${lista.length}`);
      const a = document.createElement("a");
      a.href = buildCleanPhotoDownloadUrl(source, folder, p.producto, "limpia");
      a.download = nombreDescarga("ugc", p.producto) + ".jpg";
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < lista.length - 1) await new Promise((r) => setTimeout(r, 600));
    }
    setBajando("");
    toast.success(`${lista.length} foto(s) de ${etiqueta}`);
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        disabled={!conFoto.length || Boolean(bajando)}
        onClick={() => void bajar(conFoto, "la carpeta")}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-fuchsia-500/60 px-3 py-2 text-[11px] text-fuchsia-400 transition hover:bg-fuchsia-500/10 disabled:opacity-40"
      >
        {bajando ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Bajando {bajando}
          </>
        ) : (
          <>
            <Download className="h-3.5 w-3.5" /> Todas las fotos ({conFoto.length})
          </>
        )}
      </button>
      {/* Por nicho: se generan seguidas las que comparten personaje, así no
          hay que ir cambiando de referencia en Flow a cada producto. */}
      {Object.keys(porNicho).length > 1 && (
        <div className="grid grid-cols-2 gap-1">
          {Object.entries(porNicho)
            .sort((a, b) => b[1] - a[1])
            .map(([nicho, cuantas]) => (
              <button
                key={nicho}
                type="button"
                disabled={Boolean(bajando)}
                onClick={() =>
                  void bajar(
                    conFoto.filter((p) => (p.nicho || "generico") === nicho),
                    nichos.find((n) => n.clave === nicho)?.label ?? nicho,
                  )
                }
                className={`flex items-center justify-center gap-1 rounded-md border px-2 py-1 text-[10px] transition disabled:opacity-40 ${
                  COLOR_NICHO[nicho] ?? COLOR_NICHO.generico
                }`}
              >
                <Download className="h-3 w-3" />
                {nichos.find((n) => n.clave === nicho)?.label ?? nicho} ({cuantas})
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
