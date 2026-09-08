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
  useExtraerTextos,
  useFolders,
  useHashtags,
  useSources,
} from "@/lib/queries/nichoPovBof";
import { useEsPro } from "@/lib/queries/auth";
import {
  buildVideoUGCUrl,
  subirClipUGC,
  useConfigUGC,
  useEscenasLote,
  useEstadoUGC,
  useLimpiarClipsUGC,
  useMontarUGC,
  useProductosUGC,
  nichoGeneralKeys,
} from "@/lib/queries/nichoGeneral";
import type {
  ConfigUGCResponse,
  OpcionUGC,
  ProductoUGC,
} from "@/lib/types/nichoGeneral";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { AltaMiProducto } from "@/components/tiktok-shop-ai-pro/AltaMiProducto";
import { Caja, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { MontadoEl } from "@/components/tiktok-shop-ai-pro/MontadoEl";
import { TextosDelAdmin } from "@/components/tiktok-shop-ai-pro/TextosDelAdmin";
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

/** El mismo color, para el borde izquierdo de la tarjeta. Van aparte porque
 *  Tailwind necesita la clase entera escrita. */
const BORDE_NICHO: Record<string, string> = {
  belleza: "border-l-pink-500",
  hogar: "border-l-amber-500",
  exterior: "border-l-emerald-500",
  tech: "border-l-sky-500",
  fitness: "border-l-orange-500",
  bebe: "border-l-violet-500",
  viaje: "border-l-cyan-500",
  generico: "border-l-border",
};

/** Corta por la última palabra entera antes del tope. */
function recorta(texto: string, tope: number): string {
  const limpio = (texto || "").replace(/\s+/g, " ").trim();
  if (limpio.length <= tope) return limpio;
  const corte = limpio.slice(0, tope);
  return corte.slice(0, corte.lastIndexOf(" ")) + "…";
}

export function PantallaUGC() {
  const sources = useSources();
  const cfg = useConfigUGC();
  // El defecto es el catálogo VIVO: las dos carpetas del Drive compartido se
  // quedaron desfasadas y ya no salen en el selector.
  const [source, setSource, sourceListo] = useEstadoDeUsuario(
    "ugc:source",
    "inventario_general",
  );
  const [folder, setFolder, folderListo] = useEstadoDeUsuario("ugc:folder", "");
  const [gancho, setGancho] = useEstadoDeUsuario("ugc:gancho", "dolor");
  const [duracion, setDuracion] = useEstadoDeUsuario("ugc:duracion", "10");

  // Nada se pide hasta saber POR DÓNDE IBA. Lo guardado se aplica en un
  // efecto, así que el primer render trae el catálogo por defecto: sin esta
  // espera se veía entrar en uno y saltar al otro medio segundo después.
  const listo = sourceListo && folderListo;
  const folders = useFolders(listo ? source : "");
  const carpetas = folders.data?.items ?? [];
  useEffect(() => {
    // Y la corrección de carpeta, igual: en el primer render la carpeta
    // guardada todavía no está, así que esto la pisaba con la primera de la
    // lista Y la dejaba guardada.
    if (!listo || !carpetas.length) return;
    if (!carpetas.some((c) => c.name === folder)) setFolder(carpetas[0]!.name);
  }, [carpetas, folder, listo, setFolder]);

  const productos = useProductosUGC(listo ? source : "", folder, gancho, duracion);
  const items = productos.data?.items ?? [];
  const conEscenas = items.filter((p) => p.escenas.length > 0).length;
  // Las escenas se escriben leyendo el título y la ficha, así que sin textos
  // no hay nada que escribir. Se sacan aquí mismo y no en el POV BOF: son del
  // producto y valen para todos los nichos, pero mandar al operador a otra
  // pantalla a mitad del paso 1 era perderlo.
  const conTexto = items.filter((p) => p.titulo).length;
  const extraerTextos = useExtraerTextos();
  const qcPantalla = useQueryClient();
  // Los textos son del producto y se comparten: los extrae solo el admin.
  const esPro = useEsPro();
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

        {/* El alta va aquí y no solo en el POV BOF: el producto es el mismo
            —lo guarda el mismo endpoint, en el mismo catálogo— y quien lo da
            de alta es quien lo tiene delante. Como los textos también se
            sacan desde esta pantalla, un producto de "Tareas Productos" se
            puede llevar de la foto al anuncio sin cambiar de menú.

            Al crearlo se salta a la carpeta donde ha caído: se llenan de
            diez en diez, así que el nuevo puede ir a la SIGUIENTE y quedarse
            invisible mientras miras la anterior. */}
        {CATALOGOS_PROPIOS.includes(source) && (
          <AltaMiProducto
            source={source}
            onCreado={(carpeta) => {
              if (carpeta) setFolder(carpeta);
              void folders.refetch();
              void qcPantalla.invalidateQueries({
                queryKey: ["nicho-general", "productos"],
              });
            }}
          />
        )}

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
        hint="Primero los textos (lee la ficha de cada producto) y luego las tres escenas: sus prompts de imagen, sus prompts de vídeo y lo que se dice en cada una."
        extra={`${conEscenas}/${items.length}`}
      >
        {esPro ? (
          <TextosDelAdmin hechos={conTexto} total={items.length} />
        ) : (
          <button
            type="button"
            disabled={extraerTextos.isPending || !folder}
            onClick={() =>
              extraerTextos.mutate(
                { source, folder },
                {
                  onSuccess: () => {
                    // Los textos los guarda el POV BOF: esta lista es otra
                    // consulta y sin recargarla se queda diciendo "sin textos".
                    void qcPantalla.invalidateQueries({
                      queryKey: nichoGeneralKeys.productos(
                        source, folder, gancho, duracion,
                      ),
                    });
                    toast.success("Textos extraídos");
                  },
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : String(e)),
                },
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
          >
            {extraerTextos.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                Extrayendo textos…
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5 shrink-0" />
                {conTexto >= items.length && items.length > 0
                  ? "Textos al día · volver a extraer"
                  : `Obtener textos (${conTexto}/${items.length})`}
              </>
            )}
          </button>
        )}
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
          nichos={cfg.data?.nichos ?? []}
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
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);
  // De qué va cada escena. Plegado: solo hace falta cuando no se distingue
  // qué imagen generada era la 1, la 2 o la 3.
  const [verEscenas, setVerEscenas] = useState(false);
  const [verMas, setVerMas] = useState(false);
  const [pidiendoAlt, setPidiendoAlt] = useState(false);
  // El porcentaje de cada hueco por separado, como en el POV BOF Largo: con
  // uno solo, subir el segundo pisaba el aviso del primero.
  const [pctsClip, setPctsClip] = useState<Record<number, number | null>>({
    1: null, 2: null, 3: null,
  });
  // Los hashtags que exige la tienda por la muestra. Se editan aquí y se
  // guardan al salir del campo, como el resto de lo compartido.
  const [tagsTienda, setTagsTienda] = useState(producto.hashtags_extra ?? "");
  const [enEscaparate, setEnEscaparate] = useState(producto.en_escaparate);
  const [subido, setSubido] = useState(producto.uploaded);
  const [vendio, setVendio] = useState(producto.sold);
  useEffect(() => {
    setTagsTienda(producto.hashtags_extra ?? "");
  }, [producto.hashtags_extra]);
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
  // Cuántos clips hay que generar y subir. Tres es el anuncio del curso; sube
  // cuando la tienda pide un mínimo de segundos por la muestra, porque un clip
  // dura lo que dura y la única forma de llegar es hacer más.
  const huecos = producto.escenas_pedidas || cfg?.escenas || 3;
  const fichaPersonaje =
    (cfg?.personajes ?? []).find((x) => x.clave === producto.personaje_clave)?.ficha ?? "";

  async function subirUno(f: File, hueco: number) {
    setPctsClip((p) => ({ ...p, [hueco]: 0 }));
    try {
      await subirClipUGC(f, clave, (pct) =>
        setPctsClip((p) => ({ ...p, [hueco]: pct })),
      );
      await qc.invalidateQueries({ queryKey: ["nicho-general", "productos"] });
      toast.success(`Clip ${hueco} subido`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setPctsClip((p) => ({ ...p, [hueco]: null }));
    }
  }

  return (
    /* El borde de la izquierda va del color del nicho, como los clips en el
       POV BOF: en una carpeta con diez productos mezclados es lo que dice de
       un vistazo qué personaje toca, sin leer el chip. */
    <div
      className={`space-y-2 rounded-xl border border-l-4 border-border/60 bg-card p-3 ${
        BORDE_NICHO[producto.nicho || "generico"] ?? BORDE_NICHO.generico
      }`}
    >
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
              ? [
                  producto.caption,
                  producto.emojis,
                  hashtags.join(" "),
                  // Los de la tienda VAN LOS ÚLTIMOS y en el mismo copiado:
                  // son obligatorios para cobrar la muestra, y lo que se pega
                  // aparte se olvida justo el día que hay prisa.
                  producto.hashtags_extra,
                ]
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
          {/* La foto va aquí y no suelta abajo: se baja de uvas a peras —lo
              normal es bajarse la carpeta entera en el paso 2— y ahí abajo
              estorbaba entre los botones que sí se usan en cada producto. */}
          <a
            href={buildCleanPhotoDownloadUrl(source, folder, producto.producto, "limpia")}
            download={nombreDescarga("ugc", producto.producto) + ".jpg"}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] transition hover:border-foreground/30"
          >
            <Download className="h-3 w-3" /> Foto del producto
          </a>
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
            <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              <ImageIcon className="h-3 w-3" />
              Fotos · en Flow, con el personaje y el producto
              {/* Las tres imágenes generadas se parecen entre sí y a la hora
                  de subir los clips no se sabe cuál era cuál. Esto dice de qué
                  va cada escena; va plegado para no ocupar. */}
              <button
                type="button"
                onClick={() => setVerEscenas((v) => !v)}
                title="¿Qué se ve en cada foto?"
                className="rounded-full border border-border/60 px-1 leading-none text-[10px] normal-case text-muted-foreground transition hover:border-foreground/40"
              >
                {verEscenas ? "×" : "?"}
              </button>
            </p>
            {verEscenas && (
              <ol className="space-y-1 rounded-lg border border-border/60 bg-muted/30 p-1.5 text-[10px] leading-tight text-muted-foreground">
                {/* SOLO la foto: es la duda —cuál de las tres imágenes es la
                    1— y para eso el guion sobra. Y en una frase: lo que las
                    separa es qué hace la persona, porque el escenario y la luz
                    son iguales en las tres a propósito. */}
                {escenas.map((e) => (
                  <li key={`d${e.n}`}>
                    <strong className="text-foreground">{e.n}. </strong>
                    {e.resumen || recorta(e.prompt_imagen, 110)}
                  </li>
                ))}
              </ol>
            )}
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

      {/* Cuánto tiene que durar el anuncio. Lo normal es el del curso (tres
          clips), y se sube cuando la tienda pide un mínimo por la muestra
          ("dos vídeos de 30 segundos"). NO alarga cada escena —lo que no cabe
          en su clip se corta a media palabra—: añade clips, y con ellos hacen
          falta más capturas del producto para tener de qué hablar. Se cambia
          ANTES de escribir las escenas. */}
      {CATALOGOS_PROPIOS.includes(source) && (
        <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
          <span>Anuncio de</span>
          {(cfg?.segundos_opciones ?? [0, 30, 40, 60]).map((sg) => (
            <button
              key={sg}
              type="button"
              title={
                sg === 0
                  ? "El del curso: tres clips"
                  : `${Math.ceil(sg / (duracion === "8" ? 8 : 10))} clips de ${duracion === "8" ? 8 : 10}s. Necesita capturas del producto para tener qué contar`
              }
              onClick={() =>
                estado.mutate(
                  { ...clave, segundos_guion: sg },
                  {
                    onError: (e) =>
                      toast.error(e instanceof Error ? e.message : String(e)),
                  },
                )
              }
              className={`rounded px-1.5 py-0.5 font-semibold transition ${
                (producto.segundos_guion || 0) === sg
                  ? "bg-amber-500/20 text-amber-500"
                  : "hover:text-foreground"
              }`}
            >
              {sg === 0 ? "normal" : `${sg}s`}
            </button>
          ))}
          <span className="ml-auto">
            {huecos} clip{huecos === 1 ? "" : "s"}
            {escenas.length > 0 && escenas.length !== huecos
              ? " · rehaz las escenas"
              : ""}
          </span>
        </div>
      )}

      {/* Lo que la tienda OBLIGA a poner en el caption a cambio de la muestra
          (`#vevor #vevorttESshop @vevor_es`). No van a la lista general de
          hashtags: esa se pega a los doscientos productos del catálogo y estos
          son de UN trato. Se copian con el caption, al final. */}
      {CATALOGOS_PROPIOS.includes(source) && (
        <label className="block">
          <span className="text-[10px] text-muted-foreground">
            Hashtags y menciones que pide la tienda
          </span>
          <input
            value={tagsTienda}
            onChange={(e) => setTagsTienda(e.target.value)}
            onBlur={() => {
              if ((producto.hashtags_extra ?? "") === tagsTienda.trim()) return;
              estado.mutate(
                { ...clave, hashtags_extra: tagsTienda.trim() },
                {
                  onSuccess: () => toast.success("Guardado"),
                  onError: (e) =>
                    toast.error(e instanceof Error ? e.message : String(e)),
                },
              );
            }}
            placeholder="#vevor #vevorttESshop @vevor_es"
            className="mt-0.5 w-full rounded-md border border-border/60 bg-background px-2 py-1 text-[11px] outline-none transition focus:border-violet-500/60"
          />
        </label>
      )}

      {/* Un hueco por escena, como en el POV BOF Largo: mismo aspecto, mismo
          ✓ al tenerlo y misma ✕ para quitarlo. Aquí el hueco es solo para
          contar —el orden lo pone el montaje escuchándolos—, pero se trabaja
          igual y eso vale más que ahorrarse dos clics.

          Y de uno en uno porque el WebView de la app devuelve la selección
          vacía cuando el input lleva `multiple` (ver learnings.md). */}
      <div className="grid grid-cols-3 gap-1.5">
        {Array.from({ length: huecos }, (_, i) => i + 1).map((hueco) => {
          const puesto = producto.clips.length >= hueco;
          const pct = pctsClip[hueco];
          const subiendoEste = pct !== null && pct !== undefined;
          return (
            <label
              key={hueco}
              className={`flex cursor-pointer items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-[11px] font-medium transition ${
                puesto
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 hover:border-violet-500/60"
              } ${subiendoEste ? "pointer-events-none opacity-60" : ""}`}
            >
              {subiendoEste ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  {pct}%
                </>
              ) : (
                <>
                  <Upload className="h-3.5 w-3.5 shrink-0" />
                  {puesto ? `Clip ${hueco} ✓` : `Clip ${hueco}`}
                </>
              )}
              <input
                type="file"
                accept="video/*"
                disabled={subiendoEste}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) void subirUno(f, hueco);
                }}
              />
            </label>
          );
        })}
      </div>
      {producto.clips.length > 0 && (
        /* Se vacían todos y se vuelven a subir: los clips no llevan número
           dentro, así que quitar "el segundo" no significa nada — el montaje
           los ordena por lo que se dice en cada uno. */
        <button
          type="button"
          onClick={() =>
            limpiar.mutate(clave, { onSuccess: () => toast.success("Clips vaciados") })
          }
          className="w-full rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-destructive/60 hover:text-destructive"
        >
          ✕ Quitar los {producto.clips.length} clip(s)
        </button>
      )}

      <button
        type="button"
        disabled={!producto.clips.length || producto.montando || montar.isPending}
        onClick={() =>
          montar.mutate(clave, {
            onSuccess: () => toast.success("Montando: se ordenan solos"),
            onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
          })
        }
        className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-[11px] font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-40"
      >
        {producto.montando
          ? "Montando…"
          : producto.clips.length
            ? `Montar (${producto.clips.length})`
            : "Montar anuncio"}
      </button>

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
  nichos,
}: {
  items: ProductoUGC[];
  source: string;
  folder: string;
  gancho: string;
  duracion: string;
  nichos: OpcionUGC[];
}) {
  const [bajando, setBajando] = useState("");
  const conVideo = items.filter((p) => p.video_path);
  // Por nicho, igual que las fotos: se suben seguidos los que llevan el mismo
  // personaje, así que también se bajan juntos.
  const porNicho = conVideo.reduce<Record<string, number>>((acc, p) => {
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
      a.href = buildVideoUGCUrl(
        { source, folder, producto: p.producto, gancho, duracion }, true,
      );
      a.download = nombreDescarga("ugc", p.producto) + ".mp4";
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < lista.length - 1) await new Promise((r) => setTimeout(r, 800));
    }
    setBajando("");
    toast.success(`${lista.length} vídeo(s) de ${etiqueta}`);
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        disabled={!conVideo.length || Boolean(bajando)}
        onClick={() => void bajar(conVideo, "la carpeta")}
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
                    conVideo.filter((p) => (p.nicho || "generico") === nicho),
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
  // TODOS los productos de la carpeta. La foto se pide por NÚMERO, no por file
  // id —igual que la miniatura de la tarjeta—, así que no hace falta que el
  // producto traiga `clean_photo_id`: ese campo lo calcula el POV BOF al
  // listar y no se guarda, así que aquí llegaba vacío y el botón decía
  // "Todas las fotos (0)" con la carpeta llena.
  const conFoto = items;
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

// Los catálogos que sube el operador. Solo ahí se pide una duración mínima: es
// el trato por la muestra o la tarea, y los productos del curso no lo tienen.
const CATALOGOS_PROPIOS = ["mis_productos", "tareas_productos"];
