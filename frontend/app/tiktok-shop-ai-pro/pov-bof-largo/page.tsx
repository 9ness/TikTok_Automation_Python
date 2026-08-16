"use client";

import {
  Check,
  Clapperboard,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Download,
  Loader2,
  Mic,
  RefreshCw,
  Search,
  ShoppingBag,
  Sparkles,
  Store,
  Upload,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { horaCorta } from "@/lib/hora";
import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";
import {
  esVentaNueva,
  FUENTE_TOP_VENDIDOS,
  verTopVendidos,
} from "@/lib/topVendidos";
import { BotonDescarga } from "@/components/tiktok-shop-ai-pro/BotonDescarga";
import { SubidaMasiva } from "@/components/tiktok-shop-ai-pro/SubidaMasiva";
import { Caja, OSepara, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { MagnificSpaces } from "@/components/tiktok-shop-ai-pro/MagnificSpaces";
import { PrecioAMano } from "@/components/tiktok-shop-ai-pro/PrecioAMano";
import { useMe } from "@/lib/queries/auth";
import { SincronizarTopVendidos } from "@/components/tiktok-shop-ai-pro/SincronizarTopVendidos";
import { VideoModal } from "@/components/ui/video-modal";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import {
  buildCleanPhotoDownloadUrl,
  useActivarCuentaEchoTik,
  useBorrarCuentaEchoTik,
  useBuscarProductos,
  useBuscarProductoUrl,
  useHashtags,
  useBuscarUrlsCarpeta,
  useCrearMiProducto,
  useEchoTikCuentas,
  useEchoTikEstado,
  useExtraerTextos,
  useGuardarCuentaEchoTik,
  useGuardarEchoTik,
  usePhotos,
  usePrompts,
} from "@/lib/queries/nichoPovBof";
import {
  ANCHO_CHIP,
  ANCHO_VISOR,
  fotoLargoUrl,
  largoKeys,
  useEscribirGuion,
  useFoldersLargo,
  useMarkCompletedLargo,
  useProductosLargo,
  useProductosTodosLargo,
  refrescarDesdeDriveLargo,
  useSetEstadoLargo,
  useQuitarClipLargo,
  useSourcesLargo,
  useSumarUnidadesLargo,
  useVendidosLargo,
  useVocesLargo,
  videoLargoUrl,
} from "@/lib/queries/povBofLargo";
import type {
  ProductoBuscado,
  ProductoItem,
} from "@/lib/types/nichoPovBof";
import type { ProductoLargo } from "@/lib/types/povBofLargo";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

const CAR_POR_SEG = 18.2;

/** Los dos flujos de la carpeta: el guion lleva la frase de plazos o no, según
 *  el precio. Se bajan por separado porque no se generan igual. */
type Filtro = "todas" | "plazos" | "viejo";

function cuadra(p: { modo_plazos: boolean }, filtro: Filtro): boolean {
  if (filtro === "todas") return true;
  return filtro === "plazos" ? p.modo_plazos : !p.modo_plazos;
}

/** EchoTik apagado (ver la misma bandera en el Nicho POV BOF). */
const MOSTRAR_ECHOTIK = false;

export default function PovBofLargoPage() {
  const qc = useQueryClient();
  // Solo el admin ve el space de "foto con IA": Ana y Mauro trabajan con la
  // foto limpia del Drive.
  const esAdmin = useMe().data?.rol === "admin";

  const sources = useSourcesLargo();
  const [source, setSource] = useEstadoRecordado("povbof-largo:fuente", "");
  const activaSource = source || sources.data?.[0]?.slug || "";

  const [showFotos, setShowFotos] = useState(false);
  const [picked, setPicked] = useEstadoRecordado<string | null>("povbof-largo:carpeta", null);
  const [verVendidos, setVerVendidos] = useState(false);
  const [verEscaparate, setVerEscaparate] = useState(false);

  const folders = useFoldersLargo(activaSource);
  const markCompleted = useMarkCompletedLargo(activaSource);
  const voces = useVocesLargo();

  const data = folders.data;
  const folder = picked ?? data?.current ?? null;

  const photos = usePhotos(activaSource, folder);
  const prompts = usePrompts();
  const productosQ = useProductosLargo(activaSource, folder ?? "");
  const items = productosQ.data?.items ?? [];
  const extraerTextos = useExtraerTextos();
  const buscarUrls = useBuscarUrlsCarpeta();
  const guionBatch = useEscribirGuion();
  // Global, igual que el listado (ver el mismo comentario en el POV BOF).
  const vendidos = useVendidosLargo("");
  // Productos, no unidades: el botón habla de productos (ver POV BOF).
  const totalVendidos = (vendidos.data ?? []).length;
  const unidadesVendidas = (vendidos.data ?? []).reduce((n, v) => n + (v.unidades || 1), 0);

  const openQueue = useDrawerStore((s) => s.openQueue);

  const [downloadingPhotos, setDownloadingPhotos] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState("");
  const [downloadingVideos, setDownloadingVideos] = useState(false);
  const [videoProgress, setVideoProgress] = useState("");
  const [generandoGuiones, setGenerandoGuiones] = useState(false);
  const [guionProgress, setGuionProgress] = useState("");

  const esTopVendidos = activaSource === FUENTE_TOP_VENDIDOS;
  const [soloSinSubir, setSoloSinSubir] = useEstadoRecordado(
    "largo:topventas:sinsubir", false,
  );
  // Un solo botón para "tráete lo de verdad": carpetas, productos y las ventas
  // del ranking (que se cruzan al listar, no se guardan en el producto).
  const [refrescando, setRefrescando] = useState(false);
  async function actualizarTodo() {
    setRefrescando(true);
    try {
      // El servidor cachea los listados del Drive: sin esto, invalidar la
      // caché del navegador devolvía exactamente lo mismo.
      await refrescarDesdeDriveLargo(activaSource, folder).catch(() => {});
      await qc.invalidateQueries({ queryKey: largoKeys.all });
    } finally {
      setRefrescando(false);
    }
  }

  // Ver el ranking entero y no solo la carpeta abierta: en Top vendidos cada
  // producto se queda de por vida en la carpeta de diez donde entró, así que
  // ordenar dentro de una no da el ranking.
  // Encendido por DEFECTO: en esta fuente lo que se quiere ver es el ranking,
  // igual que en "Productos que vendieron". Quitarlo devuelve la vista carpeta
  // a carpeta. La clave lleva `ranking` y no `todas` porque la primera versión
  // salió apagada y quedó guardada así en los navegadores que la vieron: con
  // la misma clave, el defecto nuevo no habría llegado a nadie.
  const [verTodas, setVerTodas] = useEstadoRecordado("largo:topventas:ranking", true);
  const todos = useProductosTodosLargo(activaSource, esTopVendidos && verTodas);
  const lista = esTopVendidos && verTodas ? todos.data?.items ?? [] : items;

  // El ranking no se repasa de un tirón: se ve de diez en diez. La página NO es
  // un estado aparte, es la CARPETA abierta — "Top 2" enseña del 11 al 20 del
  // ranking. Separados, cambiar de carpeta dejaba delante los mismos diez.
  const POR_PAGINA = 10;

  const itemsVisibles = useMemo(
    () =>
      verTopVendidos(lista, {
        activo: esTopVendidos,
        soloSinSubir,
        yaSubido: (p) => p.uploaded,
      }),
    [lista, esTopVendidos, soloSinSubir],
  );
  // Los dos flujos de guion de la carpeta, contados sobre los que tienen foto.
  const paginado = esTopVendidos && verTodas;
  const paginas = paginado ? Math.max(1, Math.ceil(itemsVisibles.length / POR_PAGINA)) : 1;
  const carpetas = data?.items ?? [];
  const iCarpeta = Math.max(0, carpetas.findIndex((f) => f.name === folder));
  const pagina = paginado ? Math.min(iCarpeta, paginas - 1) : 0;
  /** Pasar de página = abrir la carpeta correspondiente. */
  const irAPagina = (n: number) => {
    const destino = carpetas[Math.max(0, Math.min(paginas - 1, n))];
    if (destino) setPicked(destino.name);
  };
  // Lo que se ve AHORA: es lo que se baja y lo que cuentan los botones.
  const enPantalla = paginado
    ? itemsVisibles.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA)
    : itemsVisibles;

  // Sobre lo que se ESTÁ VIENDO: con el ranking completo abierto, "Fotos
  // 10/10" mientras hay cuarenta productos en pantalla no decía nada de lo que
  // se iba a bajar. Los de textos y guiones NO, que son acciones de carpeta.
  const totalProductos = enPantalla.length;
  const conVideo = enPantalla.filter((p) => p.video_path).length;
  const conFoto = enPantalla.filter((p) => p.clean_photo_id).length;
  const conPlazos = enPantalla.filter((p) => p.clean_photo_id && p.modo_plazos).length;
  const conViejo = enPantalla.filter((p) => p.clean_photo_id && !p.modo_plazos).length;
  const videosPlazos = enPantalla.filter((p) => p.video_path && p.modo_plazos).length;
  const videosViejo = enPantalla.filter((p) => p.video_path && !p.modo_plazos).length;
  // "Textos + guiones" actúa sobre la CARPETA abierta, así que su total es el
  // de la carpeta y no el de lo que se ve.
  const totalCarpeta = items.length;
  const conTexto = items.filter((p) => p.titulo).length;
  const conGuion = items.filter((p) => p.guion).length;
  const subidos = enPantalla.filter((p) => p.uploaded).length;
  const enEscaparate = enPantalla.filter((p) => p.en_escaparate).length;
  /** Le falta el guion o el que tiene es del otro modo (escrito antes de que
   *  existieran los plazos, o antes de corregir el precio). Los desfasados
   *  cuentan como pendientes: si no, el botón dice "guiones al día" mientras
   *  media carpeta lleva un guion sin la frase de plazos. */
  const pendienteGuion = (p: ProductoLargo) =>
    Boolean(p.titulo) && (!p.guion || p.modo_plazos !== p.guion_plazos);
  const sinGuion = items.filter(pendienteGuion).length;
  const pendientesEscaparate = items.filter((p) => !p.en_escaparate).length;
  const pendientesUrl = items.filter(
    (p) => !p.product_url && p.titulo_tiktok_completo,
  ).length;

  function invalidarProductos() {
    if (folder)
      void qc.invalidateQueries({ queryKey: largoKeys.productos(activaSource, folder) });
  }

  function copyText(label: string, text: string | undefined) {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado`);
  }


  async function downloadVideos(filtro: Filtro = "todas") {
    if (!folder) return;
    // En el ORDEN QUE SE VE: en Top vendidos la lista va por ventas y las
    // descargas salían por número de producto, en otro orden del que se
    // acababa de mirar.
    const conV = enPantalla.filter((p) => p.video_path && cuadra(p, filtro));
    if (!conV.length) {
      toast.error(
        filtro === "todas"
          ? "Ningún producto tiene vídeo montado todavía"
          : `Ningún vídeo ${filtro === "plazos" ? "de plazos" : "de guion normal"} montado`,
      );
      return;
    }
    setDownloadingVideos(true);
    try {
      for (const [i, p] of conV.entries()) {
        setVideoProgress(`${i + 1}/${conV.length}`);
        const a = document.createElement("a");
        // Cada producto es de SU carpeta cuando se ven todas juntas.
        const suya = p.folder || folder;
        a.href = videoLargoUrl(activaSource, suya, p.producto, p.video_listo_at ?? 0, true);
        const sufijo = filtro === "todas" ? "" : `_${filtro}`;
        // El número de delante es lo que hace que la galería los enseñe en el
        // mismo orden que la pantalla.
        a.download = `${String(i + 1).padStart(2, "0")}_${suya}_${p.producto}${sufijo}.mp4`
          .replace(/[^a-zA-Z0-9_.-]+/g, "_");
        document.body.appendChild(a);
        a.click();
        a.remove();
        if (i < conV.length - 1) await new Promise((r) => setTimeout(r, 900));
      }
      toast.success(`${conV.length} vídeo(s) descargados`);
    } finally {
      setDownloadingVideos(false);
      setVideoProgress("");
    }
  }

  /** `filtro` separa los dos flujos: los de plazos llevan un guion con la
   *  frase de financiación y los demás el de siempre, así que conviene
   *  generarlos por tandas y no ir mirando el precio producto a producto. */
  async function downloadCleanPhotos(filtro: Filtro = "todas") {
    if (!folder) return;
    const conF = enPantalla.filter((p) => p.clean_photo_id && cuadra(p, filtro));
    if (!conF.length) {
      toast.error(
        filtro === "todas"
          ? "No hay fotos limpias en esta carpeta"
          : `No hay productos ${filtro === "plazos" ? "de plazos" : "con guion viejo"} con foto`,
      );
      return;
    }
    setDownloadingPhotos(true);
    try {
      for (const [i, p] of conF.entries()) {
        setDownloadProgress(`${i + 1}/${conF.length}`);
        const a = document.createElement("a");
        const suya = p.folder || folder;
        a.href = buildCleanPhotoDownloadUrl(activaSource, suya, p.producto);
        const sufijo = filtro === "todas" ? "" : `_${filtro}`;
        a.download = `${String(i + 1).padStart(2, "0")}_${suya}_${p.producto}${sufijo}`
          .replace(/[^a-zA-Z0-9_.-]+/g, "_");
        document.body.appendChild(a);
        a.click();
        a.remove();
        if (i < conF.length - 1) await new Promise((r) => setTimeout(r, 600));
      }
      toast.success(`${conF.length} foto(s) descargadas`);
    } finally {
      setDownloadingPhotos(false);
      setDownloadProgress("");
    }
  }

  /** Escribe el guion de TODOS los productos de la carpeta que ya tienen
   *  textos y aún no lo tienen. Uno detrás de otro (cada uno gasta una llamada
   *  a Gemini), igual que "Textos" pero por guion. */
  /** `reciEn` es lo que acaba de devolver la extracción de textos, para
   *  encadenar las dos cosas.
   *
   *  Hace falta porque en ese momento `items` es todavía el de ANTES, y ahí no
   *  están ni los títulos ni —esto es lo que se escapó— el PRECIO. Un producto
   *  que estrena precio pasa a ser de plazos justo ahora: mirando la lista
   *  vieja seguía figurando como normal, su guion "cuadraba" y se saltaba, así
   *  que se quedaba con un guion sin la frase de financiación.
   *
   *  De la lista nueva solo se cogen el título y el precio, que son datos del
   *  producto (los extrae el POV BOF). El estado del guion es de este nicho y
   *  se sigue leyendo de `items`. */
  async function generarTodosGuiones(reciEn?: ProductoItem[]) {
    if (!folder) return;
    const frescos = new Map((reciEn ?? []).map((x) => [x.producto, x]));
    const pend = items.filter((p) => {
      const nuevo = frescos.get(p.producto);
      const tieneTexto = Boolean(nuevo?.titulo || p.titulo);
      const esPlazos = nuevo?.modo_plazos ?? p.modo_plazos;
      // Si el TÍTULO ha cambiado, el guion viejo habla de otro producto y hay
      // que rehacerlo. Pasa al corregir una carpeta descuadrada: los textos se
      // arreglan y, sin esto, cada vídeo se locutaba con el guion del producto
      // de al lado (que era justo el error que se venía a arreglar).
      const otroProducto = Boolean(
        nuevo?.titulo && p.titulo && nuevo.titulo !== p.titulo,
      );
      return tieneTexto && (!p.guion || esPlazos !== p.guion_plazos || otroProducto);
    });
    if (!pend.length) {
      // No es un error: es que no había nada que reescribir. Con el toast en
      // rojo parecía que la actualización de textos había fallado.
      toast.info("Textos al día · los guiones ya estaban escritos");
      return;
    }
    setGenerandoGuiones(true);
    try {
      let ok = 0;
      for (const [i, p] of pend.entries()) {
        setGuionProgress(`${i + 1}/${pend.length}`);
        try {
          await guionBatch.mutateAsync({
            source: activaSource, folder, producto: p.producto,
            // Sin esto el endpoint reaprovecharía el guion desfasado y el
            // lote no arreglaría nada.
            rehacer: Boolean(p.guion),
          });
          ok++;
        } catch (e) {
          toast.error(`Producto ${p.producto}: ${err(e)}`);
        }
      }
      toast.success(`${ok}/${pend.length} guiones escritos`);
      invalidarProductos();
    } finally {
      setGenerandoGuiones(false);
      setGuionProgress("");
    }
  }

  /** Extrae los textos de la carpeta y, seguido, escribe los guiones que
   *  falten.
   *
   *  Van juntos porque en este nicho no sirve de nada lo uno sin lo otro: sin
   *  guion no se pueden subir los clips, y el guion se escribe a partir de los
   *  textos. Hacerlo en dos botones significaba pulsar el segundo diez veces,
   *  una por producto.
   *
   *  Si la extracción falla no se escribe ningún guion: saldrían todos
   *  genéricos, y encima gastando una llamada a Gemini por producto.
   */
  function runExtraerTextos() {
    if (!folder) return;
    extraerTextos.mutate(
      { source: activaSource, folder },
      {
        onSuccess: async (nuevos) => {
          toast.success("Textos extraídos · escribiendo guiones…");
          invalidarProductos();
          await generarTodosGuiones(nuevos);
        },
        onError: (e) => toast.error(err(e)),
      },
    );
  }

  function runBuscarUrls() {
    if (!folder) return;
    buscarUrls.mutate(
      { source: activaSource, folder },
      {
        onSuccess: (res) => {
          if (!res.llamadas) toast.success("Todos los productos ya tenían enlace");
          else
            toast.success(
              `${res.encontrados}/${res.llamadas} enlaces encontrados` +
                (res.sin_resultado ? ` · ${res.sin_resultado} sin resultado` : ""),
            );
          if (res.aviso) toast.error(res.aviso);
          invalidarProductos();
        },
        onError: (e) => toast.error(err(e)),
      },
    );
  }

  const idx = useMemo(
    () => (data && folder ? data.items.findIndex((f) => f.name === folder) : -1),
    [data, folder],
  );
  const currentItem = idx >= 0 ? data?.items[idx] : undefined;
  const done = data?.completed_count ?? 0;
  const total = data?.total ?? 0;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  function switchSource(slug: string) {
    setSource(slug);
    setPicked(null);
  }

  function step(delta: number) {
    if (!data || idx < 0) return;
    const next = data.items[idx + delta];
    if (next) setPicked(next.name);
  }

  function toggleCompleted(completed: boolean) {
    if (!folder) return;
    markCompleted.mutate(
      { source: activaSource, folder, completed },
      {
        onSuccess: (res) => {
          if (completed) {
            toast.success(`"${folder}" completada`);
            setPicked(res.next_folder);
          } else {
            toast.success(`"${folder}" reabierta`);
          }
        },
        onError: (e) => toast.error(`No se pudo guardar: ${err(e)}`),
      },
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Mic className="h-5 w-5 shrink-0 text-violet-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">POV BOF Largo</h1>
            <p className="text-[11px] text-muted-foreground">
              Igual que el POV BOF, pero la voz es un guion escrito por IA para
              cada producto · DOS clips de 10s
            </p>
          </div>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Mismo catálogo y carpetas que el POV BOF; el progreso es aparte. El
          vídeo se recorta a lo que dure la voz.
          {voces.data && (
            <>
              {" "}Banco de voces: {voces.data.hombre.length} de hombre y{" "}
              {voces.data.mujer.length} de mujer, se sortea una.
            </>
          )}
        </p>
      </header>

      {/* Dónde trabajas: de qué catálogo salen los productos y en qué carpeta
          estás. Va en una caja con rótulos porque antes eran tres bloques
          sueltos sin título (fuentes, progreso, carpetas) y había que deducir
          qué era cada uno por los botones que tenía dentro. */}
      <Caja
        icono="📁"
        titulo="Dónde trabajas"
        hint="Elige el catálogo y la carpeta. El progreso es de este nicho."
        extra={`${done}/${total} hechas`}
      >
        <Sub>Catálogo</Sub>
        <div className="grid grid-cols-2 gap-2">
          {(sources.data ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => switchSource(s.slug)}
              className={`truncate rounded-lg border px-3 py-2 text-xs transition sm:text-sm ${
                activaSource === s.slug
                  ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {activaSource === "mis_productos" && (
          <AltaMiProducto onCreado={() => void folders.refetch()} />
        )}

        {/* La carpeta de Top vendidos es la misma para todos los nichos, así
            que traerse los que han vendido se puede hacer también desde aquí
            (antes solo estaba en el POV BOF). */}
        {esTopVendidos && <SincronizarTopVendidos folder={folder} />}

        <Sub>Carpetas</Sub>
        <div className="flex items-center justify-between text-xs sm:text-sm">
          <span className="font-medium">
            {done} / {total} completadas
          </span>
          <div className="flex items-center gap-2">
            {/* Antes solo recargaba las CARPETAS, así que pulsarlo no cambiaba
                nada de lo que se estaba mirando (ni los productos, ni las
                ventas del ranking, que es para lo que se pulsaba). Ahora tira
                de todo lo del nicho y lo dice. */}
            <button
              type="button"
              onClick={() => void actualizarTodo()}
              disabled={refrescando}
              className="flex items-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
              title="Recarga carpetas, productos y ventas"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refrescando ? "animate-spin" : ""}`} />
              {refrescando ? "Actualizando…" : "Actualizar productos y ventas"}
            </button>
          </div>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-violet-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        {/* Todas las carpetas a la vista, como en Creativos Pro: se ve de un
            vistazo cuáles están hechas y se salta a cualquiera sin desplegar
            nada. Antes iban escondidas tras "Ver todas" y en una rejilla de
            números, donde no se leía de qué carpeta era cada una. */}
        <div className="mt-2 flex flex-wrap gap-1">
          {(data?.items ?? []).map((f) => (
            <button
              key={f.id || f.name}
              type="button"
              onClick={() => setPicked(f.name)}
              className={`truncate rounded border px-2 py-1 text-[10px] transition ${
                // La carpeta ABIERTA se pinta según esté hecha o no: en verde
                // si ya se completó y en azul si aún no. Antes la abierta y las
                // completadas eran del mismo color y no se sabía si la que
                // tenías delante estaba lista o te faltaba terminarla.
                folder === f.name
                  ? f.completed
                    ? "border-emerald-500 bg-emerald-500/15 font-semibold text-emerald-500"
                    : "border-sky-500 bg-sky-500/15 font-semibold text-sky-400"
                  : f.completed
                    ? "border-emerald-500/40 text-emerald-500"
                    : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {f.completed && "✓ "}
              {/* El curso borró esta carpeta entera: se sigue trabajando
                  desde nuestra copia, con el progreso de siempre. */}
              {f.desde_copia && "🗄️ "}
              {f.name}
            </button>
          ))}
        </div>


      </Caja>

      {/* El ranking de ventas es GLOBAL (mismo índice para todos los nichos),
          así que va fuera de la caja de la carpeta: no es de esta carpeta ni
          de este nicho. */}
      <button
        type="button"
        onClick={() => setVerVendidos(true)}
        className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-xs font-semibold text-amber-500 transition hover:bg-amber-500/20"
      >
        <ShoppingBag className="h-4 w-4" />
        Productos que vendieron
        {totalVendidos > 0 && (
          <span className="rounded-full bg-amber-500 px-1.5 text-[10px] font-bold text-black">
            {totalVendidos}
          </span>
        )}
        {unidadesVendidas > totalVendidos && (
          <span className="text-[10px] font-normal opacity-70">· {unidadesVendidas} uds</span>
        )}
      </button>

      {verVendidos && (
        <VendidosModal onClose={() => setVerVendidos(false)} />
      )}

      {verEscaparate && folder && (
        <EscaparateModalLargo
          source={activaSource}
          folder={folder}
          productos={items}
          onClose={() => {
            setVerEscaparate(false);
            invalidarProductos();
          }}
        />
      )}


      {folders.isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Leyendo el Drive compartido…
        </div>
      )}
      {folders.isError && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
          {(folders.error as Error)?.message ?? "No se pudo leer el Drive."}
        </p>
      )}


      {data && !folder && (
        <p className="rounded-lg border border-violet-500/40 bg-violet-500/10 p-4 text-center text-sm text-violet-500">
          🎉 Todas las carpetas de esta fuente están completadas.
        </p>
      )}

      {/* La carpeta abierta: se navega, se ven sus fotos en crudo y se marca
          hecha. Con su propia caja para que no se confunda con los pasos del
          trabajo, que es lo que viene justo debajo. */}
      {data && folder && (
        <Caja
          icono="📂"
          titulo={folder}
          hint={`Carpeta ${idx + 1} de ${total}${currentItem?.completed ? " · ya completada" : ""}`}
        >
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => step(-1)}
              disabled={idx <= 0}
              className="rounded-md border border-border/60 p-1.5 disabled:opacity-30"
              aria-label="Anterior"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <div className="min-w-0 flex-1 text-center text-[11px] text-muted-foreground">
              {/* El nombre y el "N de M" ya están en la cabecera de la caja:
                  aquí solo las flechas para saltar de carpeta. */}
              cambiar de carpeta
            </div>
            <button
              type="button"
              onClick={() => step(1)}
              disabled={idx < 0 || idx >= total - 1}
              className="rounded-md border border-border/60 p-1.5 disabled:opacity-30"
              aria-label="Siguiente"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          {photos.isLoading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando fotos…
            </div>
          )}

          {photos.data && (
            <button
              type="button"
              onClick={() => setShowFotos((v) => !v)}
              className="flex w-full items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-[11px] text-muted-foreground transition hover:text-foreground sm:text-xs"
            >
              <span>{photos.data.items.length} foto(s) en crudo de la carpeta</span>
              <span>{showFotos ? "ocultar ▲" : "ver ▼"}</span>
            </button>
          )}

          {photos.data && showFotos && (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
              {photos.data.items.map((p) => (
                <a
                  key={p.id}
                  href={fotoLargoUrl(activaSource, folder, p.id, null)}
                  target="_blank"
                  rel="noreferrer"
                  className="group relative aspect-square overflow-hidden rounded-lg border border-border/60 bg-muted"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={fotoLargoUrl(activaSource, folder, p.id)}
                    alt={p.name}
                    loading="lazy"
                    className="h-full w-full object-cover transition group-hover:scale-105"
                  />
                  <span className="absolute inset-x-0 bottom-0 truncate bg-black/60 px-1 py-0.5 text-[10px] text-white">
                    {p.name}
                  </span>
                </a>
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={() => toggleCompleted(!currentItem?.completed)}
            disabled={markCompleted.isPending}
            className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition disabled:opacity-50 ${
              currentItem?.completed
                ? "border border-border/60 text-muted-foreground hover:text-foreground"
                : "bg-violet-500 text-white hover:bg-violet-600"
            }`}
          >
            {markCompleted.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            {currentItem?.completed ? "Desmarcar completada" : "Completada · siguiente"}
          </button>
        </Caja>
      )}

      {/* El trabajo del día en el ORDEN en que se hace, con los mismos cuatro
          pasos y los mismos colores que el POV BOF: quien aprende uno sabe
          usar el otro. Aquí el paso 1 escribe además el guion, que es lo que
          decide la duración del vídeo. */}
      {data && folder && (
        <section className="space-y-2">
          <div className="flex items-center gap-2 px-1">
            <Sparkles className="h-4 w-4 shrink-0 text-violet-500" />
            <p className="text-sm font-semibold">Cómo se hace un vídeo</p>
            <span className="ml-auto text-[10px] text-muted-foreground">{folder}</span>
          </div>

          <Paso
            n={1}
            color="violeta"
            titulo="Preparar textos y guion"
            hint={esTopVendidos ? "Aquí los textos se copian del producto original: no se vuelven a leer con IA, que es lo que descuadraba la carpeta." : "Los textos salen de la ficha; el guion lo escribe la IA para ese producto y es lo que marca cuántos clips harán falta."}
            extra={`${conGuion}/${totalProductos} con guion`}
          >
            <button
              type="button"
              onClick={runExtraerTextos}
              disabled={extraerTextos.isPending}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
            >
              {extraerTextos.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> Extrayendo textos…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 shrink-0" />
                  Obtener textos ({conTexto}/{totalCarpeta})
                </>
              )}
            </button>

            {/* Guion para toda la carpeta a la vez, en vez de tarjeta a
                tarjeta. Necesitan tener textos primero. */}
            <button
              type="button"
              onClick={() => void generarTodosGuiones()}
              disabled={generandoGuiones || !sinGuion}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/60 bg-card px-3 py-2 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/10 disabled:opacity-50"
            >
              {generandoGuiones ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  Escribiendo guiones {guionProgress}…
                </>
              ) : (
                <>
                  <Sparkles className="h-3.5 w-3.5 shrink-0" />
                  {sinGuion
                    ? `Escribir todos los guiones (${sinGuion})`
                    : `Guiones al día (${conGuion}/${totalProductos})`}
                </>
              )}
            </button>

            <div className="grid grid-cols-2 gap-1.5">
              <div
                className={`flex items-center justify-center gap-1.5 truncate rounded-lg border px-2 py-1.5 text-[11px] font-semibold ${
                  subidos === totalProductos && totalProductos > 0
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                    : "border-border/60 text-muted-foreground"
                }`}
              >
                <span className="truncate">📤 Subidos {subidos}/{totalProductos}</span>
              </div>
              <button
                type="button"
                onClick={() => setVerEscaparate(true)}
                className={`flex items-center justify-center gap-1.5 truncate rounded-lg border px-2 py-1.5 text-[11px] font-semibold transition ${
                  enEscaparate === totalProductos && totalProductos > 0
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                    : "border-sky-500/50 bg-sky-500/10 text-sky-500 hover:bg-sky-500/20"
                }`}
              >
                <span className="truncate">🏪 Escaparate {enEscaparate}/{totalProductos}</span>
              </button>
            </div>

            {MOSTRAR_ECHOTIK && (
              <button
                type="button"
                onClick={runBuscarUrls}
                disabled={buscarUrls.isPending || !pendientesUrl}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/60 px-3 py-2 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/10 disabled:opacity-50"
              >
                {buscarUrls.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> Buscando…
                  </>
                ) : (
                  <span className="truncate">
                    {pendientesUrl ? `Enlaces (${pendientesUrl} llamadas)` : "Enlaces al día"}
                  </span>
                )}
              </button>
            )}
          </Paso>

          <Paso
            n={2}
            color="fucsia"
            titulo="Generar los clips fuera"
            hint="Baja las fotos y crea los clips en Magnific. Aquí cada vídeo lleva dos clips (tres si el guion pasa de 25s)."
            extra={`${conFoto} foto(s)`}
          >
            <p className="text-[10px] font-semibold text-muted-foreground">
              Primero, baja las fotos
            </p>
            <div className="grid grid-cols-3 gap-1.5">
              <BotonDescarga
                onClick={() => void downloadCleanPhotos()}
                cargando={downloadingPhotos}
                progreso={downloadProgress}
                disabled={!conFoto}
                etiqueta={`Fotos ${conFoto}/${totalProductos}`}
              />
              <BotonDescarga
                onClick={() => void downloadCleanPhotos("viejo")}
                cargando={false}
                disabled={downloadingPhotos || !conViejo}
                etiqueta={`Normal (${conViejo})`}
              />
              <BotonDescarga
                onClick={() => void downloadCleanPhotos("plazos")}
                cargando={false}
                disabled={downloadingPhotos || !conPlazos}
                etiqueta={`💳 Plazos (${conPlazos})`}
                acento
              />
            </div>

            <p className="pt-1 text-[10px] font-semibold text-muted-foreground">
              Y luego, créalos
            </p>
            {/* Del de foto limpia solo hace falta el de plazos: aquí todos los
                vídeos llevan dos clips. El de "foto con IA" solo el admin. */}
            <MagnificSpaces
              spaces={["foto_limpia_plazos", ...(esAdmin ? (["foto_ia"] as const) : [])]}
            />
            <OSepara />
            <div className="grid grid-cols-2 gap-1.5">
              <button
                type="button"
                onClick={() => copyText("Prompt imagen", prompts.data?.imagen)}
                disabled={!prompts.data?.imagen}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
              >
                <ClipboardCopy className="h-3.5 w-3.5" /> Prompt imagen
              </button>
              <button
                type="button"
                onClick={() => copyText("Prompt vídeo", prompts.data?.video)}
                disabled={!prompts.data?.video}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
              >
                <Clapperboard className="h-3.5 w-3.5" /> Prompt vídeo
              </button>
            </div>
          </Paso>

          {folder && items.length > 0 && (
            <Paso
              n={3}
              color="esmeralda"
              titulo="Traer los clips generados"
              hint="Suéltalos todos de golpe: se reparten a su producto y en su orden (clip 1, 2 y 3)."
            >
              <SubidaMasiva
                source={activaSource}
                folder={folder}
                productos={items}
                root="/api/v1/nicho-pov-bof-largo"
                todosDobles
                sinMarco
              />
            </Paso>
          )}

          <Paso
            n={4}
            color="azul"
            titulo="Descargar lo ya montado"
            hint="Los vídeos con la voz puesta, listos para subir a TikTok."
            extra={`${conVideo}/${totalProductos}`}
          >
            <div className="grid grid-cols-3 gap-1.5">
              <BotonDescarga
                onClick={() => void downloadVideos()}
                cargando={downloadingVideos}
                progreso={videoProgress}
                disabled={!conVideo}
                etiqueta={`Vídeos ${conVideo}/${totalProductos}`}
              />
              <BotonDescarga
                onClick={() => void downloadVideos("viejo")}
                cargando={false}
                disabled={downloadingVideos || !videosViejo}
                etiqueta={`Normal (${videosViejo})`}
              />
              <BotonDescarga
                onClick={() => void downloadVideos("plazos")}
                cargando={false}
                disabled={downloadingVideos || !videosPlazos}
                etiqueta={`💳 Plazos (${videosPlazos})`}
                acento
              />
            </div>
          </Paso>
        </section>
      )}

      {/* Los productos de la carpeta, ya fuera de los pasos. */}
      {data && folder && (
        <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
          {productosQ.isLoading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando productos…
            </div>
          )}
          {productosQ.isError && (
            <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
              {(productosQ.error as Error)?.message ?? "No se pudieron cargar los productos."}
            </p>
          )}

          {/* Solo en Top vendidos: ahí importa el orden (lo que más vende) y
              lo que se busca es lo que aún no has probado. */}
          {esTopVendidos && items.length > 0 && (
            <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
              <input
                type="checkbox"
                className="h-4 w-4 accent-violet-500"
                checked={soloSinSubir}
                onChange={(e) => setSoloSinSubir(e.target.checked)}
              />
              Solo los que no he subido
              <span className="ml-auto text-[10px] text-muted-foreground">
                {itemsVisibles.length}/{lista.length}
              </span>
            </label>
          )}

          {/* El ranking de verdad: junta las carpetas de diez y ordena por
              ventas (el sitio de cada producto es fijo, ver arriba). */}
          {esTopVendidos && (
            <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
              <input
                type="checkbox"
                className="h-4 w-4 accent-violet-500"
                checked={verTodas}
                onChange={(e) => setVerTodas(e.target.checked)}
              />
              Todas las carpetas juntas, por ventas
              {todos.isFetching && <Loader2 className="h-3 w-3 animate-spin" />}
            </label>
          )}

          {/* De diez en diez, sin romper el orden por ventas: la página 2 son
              los diez siguientes del ranking, no la carpeta 2. */}
          {paginado && paginas > 1 && (
            <div className="flex items-center justify-between rounded-lg border border-border/60 p-1.5 text-[11px]">
              <button
                type="button"
                onClick={() => irAPagina(pagina - 1)}
                disabled={pagina === 0}
                className="rounded px-2 py-1 text-muted-foreground transition hover:text-foreground disabled:opacity-30"
              >
                ‹ anteriores
              </button>
              <span className="font-semibold">
                {pagina * POR_PAGINA + 1}-
                {Math.min((pagina + 1) * POR_PAGINA, itemsVisibles.length)} de{" "}
                {itemsVisibles.length} por ventas
              </span>
              <button
                type="button"
                onClick={() => irAPagina(pagina + 1)}
                disabled={pagina >= paginas - 1}
                className="rounded px-2 py-1 text-muted-foreground transition hover:text-foreground disabled:opacity-30"
              >
                siguientes ›
              </button>
            </div>
          )}

          {enPantalla.length > 0 && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {enPantalla.map((p) => (
                <ProductoCard
                  key={`${p.folder || folder}-${p.producto}`}
                  source={activaSource}
                  // En la vista global cada tarjeta es de SU carpeta.
                  folder={p.folder || folder}
                  producto={p}
                  esTopVendidos={esTopVendidos}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

/** Alta de productos PROPIOS (fuente "Mis productos"). Reusa el endpoint del
 *  POV BOF: crea el producto en el Drive compartido, así que sirve a los dos. */
function AltaMiProducto({ onCreado }: { onCreado: () => void }) {
  const crear = useCrearMiProducto();
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const refLimpia = useRef<HTMLInputElement>(null);
  const refFicha = useRef<HTMLInputElement>(null);
  const [abierto, setAbierto] = useState(false);

  function enviar() {
    if (!limpia) {
      toast.error("Falta la foto del producto.");
      return;
    }
    crear.mutate(
      { fotoLimpia: limpia, fotoFicha: ficha },
      {
        onSuccess: (r) => {
          toast.success(`Producto ${r.producto} añadido a «${r.carpeta}»`);
          setLimpia(null);
          setFicha(null);
          if (refLimpia.current) refLimpia.current.value = "";
          if (refFicha.current) refFicha.current.value = "";
          onCreado();
        },
        onError: (e) => toast.error(err(e)),
      },
    );
  }

  const campo = (
    ref: React.RefObject<HTMLInputElement>,
    titulo: string,
    ayuda: string,
    archivo: File | null,
    set: (f: File | null) => void,
  ) => (
    <label className="flex cursor-pointer flex-col gap-1 rounded-lg border border-dashed border-border/60 p-2.5 transition hover:border-violet-500/60">
      <span className="text-[11px] font-semibold">{titulo}</span>
      <span className="text-[10px] text-muted-foreground">{ayuda}</span>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        onChange={(e) => set(e.target.files?.[0] ?? null)}
        className="mt-1 block w-full text-[10px] text-muted-foreground file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-[10px]"
      />
      {archivo && <span className="truncate text-[10px] text-emerald-500">✓ {archivo.name}</span>}
    </label>
  );

  return (
    <section className="space-y-2 rounded-xl border border-violet-500/40 bg-violet-500/5 p-3">
      {/* Plegado por defecto (ver POV BOF): dar de alta un producto es cosa de
          una vez al día y desplegado empujaba la lista media pantalla abajo. */}
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-xs font-semibold sm:text-sm">➕ Añadir un producto mío</span>
        <span className="text-[11px] text-muted-foreground">{abierto ? "▾" : "▸"}</span>
      </button>
      {!abierto ? null : (
      <>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {campo(refLimpia, "Foto limpia", "La del producto, sin texto encima", limpia, setLimpia)}
        {campo(refFicha, "Foto descripción", "La captura de la ficha (opcional)", ficha, setFicha)}
      </div>
      <button
        type="button"
        disabled={crear.isPending || !limpia}
        onClick={enviar}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
      >
        {crear.isPending ? "Subiendo…" : "Añadir producto"}
      </button>
      <p className="text-[10px] leading-relaxed text-muted-foreground">
        Las carpetas se llenan de 10 en 10. Es el mismo catálogo que el POV BOF:
        el producto vale para los dos nichos.
      </p>
      </>
      )}
    </section>
  );
}



function EscaparateModalLargo({
  source,
  folder,
  productos,
  onClose,
}: {
  source: string;
  folder: string;
  productos: ProductoLargo[];
  onClose: () => void;
}) {
  const setEstado = useSetEstadoLargo();
  return (
    <EscaparateModal
      source={source}
      folder={folder}
      productos={productos as unknown as ProductoItem[]}
      onClose={onClose}
      marcarEstado={(vars, opts) => setEstado.mutate(vars, opts)}
    />
  );
}

type ToolKey = "gancho" | "titulo" | "cta" | "flecha";

const TOOLS: { key: ToolKey; label: string }[] = [
  { key: "gancho", label: "🎣 Gancho" },
  { key: "titulo", label: "📝 Texto producto" },
  { key: "cta", label: "👉 CTA" },
  { key: "flecha", label: "⬇️ Flecha" },
];

/** Tarjeta de producto del Largo: como la del POV BOF (textos, enlace, foto,
 *  escaparate/subido/vendió) pero con el paso del GUION y DOS clips. */
function ProductoCard({
  source,
  folder,
  producto: p,
  esTopVendidos = false,
}: {
  source: string;
  folder: string;
  producto: ProductoLargo;
  /** En "Top vendidos" se enseña cuántas veces vendió y si es reciente. */
  esTopVendidos?: boolean;
}) {
  const qc = useQueryClient();
  const guion = useEscribirGuion();

  /** Escribe el guion del producto. La usan el botón grande y el intento de
   *  subir un clip sin guion (que es cuando de verdad se echa en falta). */
  function escribirGuion() {
    guion.mutate(
      { source, folder, producto: p.producto },
      {
        onSuccess: () => toast.success("Guion escrito"),
        onError: (e) => toast.error(err(e)),
      },
    );
  }
  const setEstado = useSetEstadoLargo();
  const quitarClip = useQuitarClipLargo();
  const buscarUrl = useBuscarProductoUrl();
  const hashtags = useHashtags().data ?? [];
  const refs = {
    1: useRef<HTMLInputElement>(null),
    2: useRef<HTMLInputElement>(null),
    3: useRef<HTMLInputElement>(null),
  };

  const [verFoto, setVerFoto] = useState(false);
  const [verTools, setVerTools] = useState(false);
  const [verGuion, setVerGuion] = useState(false);
  // El guion guardado se escribió en el otro modo (con o sin la frase de
  // plazos). No es un error: pasa con todo lo escrito antes de que existieran
  // los plazos y cada vez que se corrige un precio.
  const guionDesfasado = Boolean(p.guion) && p.modo_plazos !== p.guion_plazos;
  // Cuántos clips pide ESTE guion. Lo calcula el backend con los caracteres
  // (la voz aún no existe cuando hay que decidirlo).
  const necesarios = p.clips_necesarios || 2;
  const [verVideo, setVerVideo] = useState(false);
  // Progreso POR SLOT (null = ese clip no se está subiendo). Así se puede subir
  // el clip 2 mientras el 1 va por la mitad, y cada tarjeta es independiente de
  // las demás (subir clips de varios productos a la vez).
  const [pcts, setPcts] = useState<{
    1: number | null;
    2: number | null;
    3: number | null;
  }>({ 1: null, 2: null, 3: null });
  // Auto por defecto: el montaje mira la mano del clip 1 y elige la voz
  // (mujer salvo que vea reloj o vello). Se puede forzar a mano.
  const [sexo, setSexo] = useState<"hombre" | "mujer" | "auto">("auto");
  const [tools, setTools] = useState<Record<ToolKey, boolean>>({
    gancho: true, titulo: true, cta: true, flecha: true,
  });

  const urlNoEncontrada = buscarUrl.isSuccess && !p.product_url;

  const limpia = p.clean_photo_id
    ? fotoLargoUrl(source, folder, p.clean_photo_id, ANCHO_CHIP)
    : null;
  const limpiaVisor = p.clean_photo_id
    ? fotoLargoUrl(source, folder, p.clean_photo_id, ANCHO_VISOR)
    : null;
  const fichaVisor = p.titled_photo_id
    ? fotoLargoUrl(source, folder, p.titled_photo_id, ANCHO_VISOR)
    : null;

  function push(patch: { en_escaparate?: boolean; uploaded?: boolean; sold?: boolean }) {
    setEstado.mutate(
      { source, folder, producto: p.producto, ...patch },
      { onError: (e) => toast.error(err(e)) },
    );
  }

  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";

  // XHR (no fetch) para tener porcentaje real de subida, igual que el POV BOF.
  // Cada slot va por su cuenta: no se bloquea el otro clip ni las demás fichas.
  function subirClip(slot: 1 | 2 | 3, file: File) {
    setPcts((prev) => ({ ...prev, [slot]: 0 }));
    const fd = new FormData();
    fd.append("file", file);
    fd.append("source", source);
    fd.append("folder", folder);
    fd.append("producto", p.producto);
    fd.append("slot", String(slot));
    fd.append("sexo", sexo);
    fd.append("con_gancho", String(tools.gancho));
    fd.append("con_titulo", String(tools.titulo));
    fd.append("con_cta", String(tools.cta));
    fd.append("con_flecha", String(tools.flecha));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBase}/api/v1/nicho-pov-bof-largo/clip/upload`);
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        setPcts((prev) => ({ ...prev, [slot]: Math.round((e.loaded / e.total) * 100) }));
    };
    xhr.onload = () => {
      setPcts((prev) => ({ ...prev, [slot]: null }));
      const ref = refs[slot].current;
      if (ref) ref.value = "";
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const r = JSON.parse(xhr.responseText) as { message?: string };
          toast.success(r.message || "Clip subido");
        } catch {
          toast.success("Clip subido");
        }
        void qc.invalidateQueries({ queryKey: largoKeys.productos(source, folder) });
      } else {
        let msg = "Error subiendo el clip";
        try {
          const r = JSON.parse(xhr.responseText) as { detail?: string; message?: string };
          msg = r.detail || r.message || msg;
        } catch {
          /* respuesta no-JSON */
        }
        toast.error(msg);
      }
    };
    xhr.onerror = () => {
      setPcts((prev) => ({ ...prev, [slot]: null }));
      const ref = refs[slot].current;
      if (ref) ref.value = "";
      toast.error("Error de red al subir");
    };
    xhr.send(fd);
  }

  return (
    /* Borde con el color del nicho (violeta) y según el estado: gris sin
       guion, violeta con guion escrito, verde cuando el vídeo ya está. */
    <div
      className={`space-y-2 rounded-xl border bg-card p-3 transition ${
        p.video_path
          ? "border-emerald-500/50"
          : p.guion
            ? "border-violet-500/40"
            : "border-border/60 hover:border-violet-500/30"
      }`}
    >
      <div className="flex gap-2">
        {limpia ? (
          <button type="button" onClick={() => setVerFoto(true)} title="Ver la foto en grande" className="shrink-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={limpia}
              alt={p.producto}
              loading="lazy"
              className="h-16 w-16 rounded-lg border border-border/60 object-cover transition hover:border-foreground/40"
            />
          </button>
        ) : (
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg border border-dashed border-border/60 text-center text-[9px] text-muted-foreground">
            sin foto
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-1.5 text-xs font-semibold sm:text-sm">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {p.producto}
            </span>
            <span className="truncate">{p.titulo || "sin título"}</span>
          </p>
          {p.titulo_tiktok_completo && (
            <p className="truncate text-[10px] text-muted-foreground">{p.titulo_tiktok_completo}</p>
          )}
          {esTopVendidos && p.ventas > 0 && (
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px]">
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-semibold text-emerald-500">
                🔥 {p.ventas} {p.ventas === 1 ? "venta" : "ventas"}
              </span>
              {esVentaNueva(p.vendido_at) && (
                <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-semibold text-amber-500">
                  nuevo
                </span>
              )}
            </p>
          )}
          {/* El precio decide QUÉ guion escribe la IA: por encima del umbral
              lleva la frase de financiación. Los dos clips van igual. */}
          {p.titulo && (
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px]">
              {p.precio > 0 ? (
                <>
                  {p.precio_lista > p.precio && (
                    <span className="font-mono text-muted-foreground line-through">
                      {p.precio_lista.toFixed(2).replace(".", ",")} €
                    </span>
                  )}
                  <span className="font-mono font-semibold">
                    {p.precio.toFixed(2).replace(".", ",")} €
                  </span>
                </>
              ) : (
                /* El precio lo guarda el POV BOF (es del producto, no del
                   nicho) y aquí se lee: sin él no hay guion de plazos. */
                <PrecioAMano source={source} folder={folder} producto={p.producto} />
              )}
              {p.desde_copia && (
                /* El Drive del curso ya no tiene estas fotos: se están
                   sirviendo de nuestra copia. Se avisa porque significa que el
                   producto puede desaparecer de un momento a otro del origen. */
                <span
                  title="El Drive del curso ya no las tiene: salen de la copia de seguridad"
                  className="rounded bg-amber-500/15 px-1.5 py-0.5 font-semibold text-amber-500"
                >
                  🗄️ desde la copia
                </span>
              )}
              {p.modo_plazos && (
                <span className="rounded bg-violet-500/15 px-1.5 py-0.5 font-semibold text-violet-500">
                  💳 Guion con plazos
                </span>
              )}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {/* Igual que en el POV BOF: el "Título" a secas no se pega en ningún
            sitio (el que va a TikTok es el completo). */}
        <CopyChip label="🔎 Título TikTok" text={p.titulo_tiktok_completo ?? ""} />
        <CopyChip label="🏪 Tienda" text={p.tienda ?? ""} siempre />
        <CopyChip
          label="✍️ Caption"
          text={
            p.caption ? [p.caption, p.emojis, hashtags.join(" ")].filter(Boolean).join(" ") : ""
          }
        />
        {/* Gancho y CTA los quema el montaje. Copiar el guion y el subliminal
            se ha bajado DENTRO del guion plegado: ahí siguen a mano (el
            subliminal no lo pone el vídeo, solo se copia) sin ocupar sitio en
            la ficha. */}
        {p.product_url && <CopyChip label="🔗 Enlace" text={p.product_url} />}
        {p.clean_photo_id && (
          <a
            href={buildCleanPhotoDownloadUrl(source, folder, p.producto)}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40 hover:text-foreground"
          >
            <Download className="h-3 w-3" /> Foto
          </a>
        )}
      </div>

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={`Producto ${p.producto}`}
        urlLimpia={limpiaVisor}
        urlTitulo={fichaVisor}
        urlDescarga={
          p.clean_photo_id ? buildCleanPhotoDownloadUrl(source, folder, p.producto) : null
        }
      />

      {p.foto_aviso && (
        <p className="text-[11px] text-amber-400 break-words">🖼️ {p.foto_aviso}</p>
      )}
      {p.caption_riesgo && (
        <p className="text-[11px] text-amber-400 break-words">⚠️ {p.caption_riesgo}</p>
      )}

      {/* Ficha de TikTok Shop (EchoTik, 1 llamada por búsqueda). */}
      {MOSTRAR_ECHOTIK && (p.product_url ? (
        <a
          href={p.product_url}
          target="_blank"
          rel="noreferrer"
          className="block truncate rounded-md border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-[11px] text-emerald-500"
          title={p.url_match_name}
        >
          🔗 Ver ficha en TikTok Shop
          {p.url_match_score < 0.99 && " · comprueba que es el correcto"}
        </a>
      ) : (
        <button
          type="button"
          disabled={buscarUrl.isPending || !p.titulo_tiktok_completo}
          onClick={() =>
            buscarUrl.mutate(
              { source, folder, producto: p.producto },
              {
                onSuccess: () =>
                  void qc.invalidateQueries({ queryKey: largoKeys.productos(source, folder) }),
                onError: (e) => toast.error(err(e)),
              },
            )
          }
          className="rounded-md border border-border/60 px-2 py-1.5 text-[11px] text-muted-foreground transition disabled:opacity-40"
        >
          {buscarUrl.isPending
            ? "🔎 Buscando…"
            : urlNoEncontrada
              ? "❌ EchoTik no lo encuentra — reintentar (1 llamada)"
              : "🔗 Buscar enlace (gasta 1 llamada EchoTik)"}
        </button>
      ))}

      {/* El guion es lo primero: sin él no se puede subir clip. Va plegado
          porque se lee UNA vez, al escribirlo; después solo estorba entre el
          precio y los clips. La cabecera ya dice lo que se mira de reojo
          (cuánto dura) sin abrirlo. */}
      {p.guion ? (
        <div className="space-y-1 rounded border border-border/60 bg-muted/30 p-2">
          <button
            type="button"
            onClick={() => setVerGuion((v) => !v)}
            className="flex w-full items-center justify-between gap-2 text-[10px] font-medium text-muted-foreground"
          >
            <span className={guionDesfasado ? "text-amber-500" : undefined}>
              {guionDesfasado ? "⚠️ 🎬 Guion" : "🎬 Guion"}
              <span className="ml-1 opacity-70">
                {p.guion_caracteres} car. · ~{Math.round(p.guion_caracteres / CAR_POR_SEG)}s
              </span>
            </span>
            <span>{verGuion ? "▾" : "▸"}</span>
          </button>
          {verGuion && (
          <>
          {/* El guion guardado puede ser del OTRO modo: escrito antes de que
              existieran los plazos, o antes de corregir el precio. El montaje
              lo reescribe solo, pero sin decirlo aquí parecería que el vídeo
              va a llevar este texto. */}
          {guionDesfasado && (
            <p className="rounded bg-amber-500/10 px-1.5 py-1 text-[10px] text-amber-500">
              {p.modo_plazos
                ? "Este guion no lleva la frase de plazos (se escribió antes). Se reescribe solo al montar, o púlsalo ahora."
                : "Este guion lleva la frase de plazos y el producto ya no llega al umbral. Se reescribe solo al montar."}
            </p>
          )}
          <p className="text-[10px] leading-relaxed">{p.guion}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            <CopyChip label="🎬 Guion" text={p.guion ?? ""} />
            <CopyChip label="💬 Subliminal" text={p.subliminal ?? ""} />
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
              {guionDesfasado ? "Reescribir" : "Otro guion"}
            </button>
          </div>
          </>
          )}
        </div>
      ) : (
        <button
          type="button"
          disabled={guion.isPending || !p.titulo}
          onClick={escribirGuion}
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

      {/* Voz */}
      <div className="flex rounded-md border border-border/60 p-0.5 text-[11px]">
        {(["auto", "hombre", "mujer"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSexo(s)}
            title={
              s === "auto"
                ? "Mira la mano del clip 1: mujer salvo que se vea reloj o vello"
                : undefined
            }
            className={`flex-1 rounded px-1.5 py-1 transition ${
              sexo === s ? "bg-violet-500 font-semibold text-white" : "text-muted-foreground"
            }`}
          >
            {s === "auto" ? "🖐️ Auto" : s === "hombre" ? "👨 Hombre" : "👩 Mujer"}
            {s !== "auto" && p.sexo_sugerido === s && " ★"}
          </button>
        ))}
      </div>

      {/* Qué añadir al vídeo */}
      <div className="space-y-1.5 rounded-md border border-border/60 p-2">
        {/* Plegado por defecto, como en el POV BOF: casi siempre van las
            cuatro y desplegado se comía media pantalla en el móvil. */}
        <button
          type="button"
          onClick={() => setVerTools((v) => !v)}
          className="flex w-full items-center justify-between text-[10px] font-medium text-muted-foreground"
        >
          <span>
            Qué añadir al vídeo
            <span className="ml-1 opacity-70">
              ({Object.values(tools).filter(Boolean).length}/{TOOLS.length})
            </span>
          </span>
          <span>{verTools ? "▾" : "▸"}</span>
        </button>
        {verTools && (
        <div className="grid grid-cols-2 gap-1.5">
          {TOOLS.map((t) => (
            <label
              key={t.key}
              className={`flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-1 text-[11px] transition ${
                tools[t.key] ? "bg-violet-500/10" : "text-muted-foreground"
              }`}
            >
              <input
                type="checkbox"
                className="h-4 w-4 shrink-0 accent-violet-500"
                checked={tools[t.key]}
                onChange={(e) => setTools((prev) => ({ ...prev, [t.key]: e.target.checked }))}
              />
              <span className="truncate">{t.label}</span>
            </label>
          ))}
        </div>
        )}
        {!Object.values(tools).some(Boolean) && (
          <p className="text-[10px] text-amber-500">Vídeo limpio: solo la voz, sin nada encima.</p>
        )}
      </div>

      {/* Los clips. No se encola hasta tenerlos todos y el guion. Son DOS,
          salvo que la voz no quepa en veinte segundos: entonces hace falta un
          tercero (si no, el montaje estira los dos y el gesto se deforma). */}
      <div className={`grid gap-1.5 ${necesarios > 2 ? "grid-cols-3" : "grid-cols-2"}`}>
        {(necesarios > 2 ? ([1, 2, 3] as const) : ([1, 2] as const)).map((slot) => {
          const puesto = slot === 1 ? p.clip1 : slot === 2 ? p.clip2 : p.clip3;
          const pctSlot = pcts[slot];
          const subiendoEste = pctSlot !== null;
          return (
            <label
              key={slot}
              // Sin guion NO se puede subir (la voz manda la duración), pero
              // antes el botón quedaba muerto: se pulsaba y no pasaba nada, y
              // parecía roto. Ahora dice por qué y lo escribe de un toque.
              onClick={(e) => {
                if (p.guion || subiendoEste) return;
                e.preventDefault();
                toast.info("Primero escribe el guion: es lo que marca la duración.");
                if (!guion.isPending) escribirGuion();
              }}
              className={`flex cursor-pointer items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-[11px] font-medium transition ${
                puesto
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 hover:border-violet-500/60"
              } ${!p.guion || subiendoEste ? "opacity-60" : ""}`}
            >
              {subiendoEste ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  Subiendo {pctSlot}%
                </>
              ) : (
                <>
                  <Upload className="h-3.5 w-3.5 shrink-0" />
                  {puesto ? `Clip ${slot} ✓` : `Clip ${slot}`}
                  {/* Quitar el clip subido por error. Va DENTRO del botón (que
                      es un <label> con el input dentro), así que hay que
                      cortar el evento o se abriría el selector de ficheros. */}
                  {puesto && !subiendoEste && (
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={`Quitar el clip ${slot}`}
                      title="Quitar este clip"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        quitarClip.mutate(
                          { source, folder, producto: p.producto, slot },
                          {
                            onSuccess: () => toast.success(`Clip ${slot} quitado`),
                            onError: (e2: unknown) => toast.error(err(e2)),
                          },
                        );
                      }}
                      className="ml-0.5 rounded px-1 text-muted-foreground transition hover:bg-destructive/15 hover:text-destructive"
                    >
                      ✕
                    </span>
                  )}
                </>
              )}
              <input
                ref={refs[slot]}
                type="file"
                accept="video/*"
                disabled={subiendoEste || !p.guion}
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
      {!p.guion ? (
        <p className="text-[10px] text-muted-foreground">
          Escribe el guion antes de subir los clips: la voz decide la duración.
        </p>
      ) : necesarios > 2 ? (
        <p className="text-[10px] text-amber-500">
          Este guion pasa de 25s ({p.guion_caracteres} car. · ~
          {Math.round(p.guion_caracteres / 18.2)}s): hacen falta {necesarios} clips.
        </p>
      ) : null}

      {p.montando && (
        <p className="flex items-center gap-1.5 rounded border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-[10px] text-violet-500">
          <Loader2 className="h-3 w-3 animate-spin" /> Locutando y montando…
        </p>
      )}

      {p.video_path && (
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            onClick={() => setVerVideo(true)}
            className="flex items-center justify-center gap-1.5 rounded-md border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-[11px] font-semibold text-emerald-500"
          >
            ▶ Ver vídeo{p.voz_label && ` · ${p.voz_label}`}
          </button>
          <a
            href={videoLargoUrl(source, folder, p.producto, p.video_listo_at ?? 0, true)}
            download={`${folder}_${p.producto}.mp4`.replace(/[^a-zA-Z0-9_.-]+/g, "_")}
            className="flex items-center justify-center gap-1.5 rounded-md border border-emerald-500/50 px-2 py-1.5 text-[11px] text-emerald-500"
          >
            <Download className="h-3.5 w-3.5" /> Descargar
          </a>
        </div>
      )}

      <VideoModal
        open={verVideo}
        onOpenChange={setVerVideo}
        title={`Producto ${p.producto}`}
        filename={(p.video_path ?? "").split("/").pop() ?? ""}
        videoUrl={
          p.video_path ? videoLargoUrl(source, folder, p.producto, p.video_listo_at ?? 0) : null
        }
        downloadUrl={
          p.video_path
            ? videoLargoUrl(source, folder, p.producto, p.video_listo_at ?? 0, true)
            : null
        }
      />

      {/* Estado individual. Separado con una línea: no es trabajo por hacer,
          es marcar en qué punto está el producto (igual que en el POV BOF). */}
      <div className="flex gap-1.5 border-t border-border/60 pt-2">
        <button
          type="button"
          onClick={() => push({ en_escaparate: !p.en_escaparate })}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            p.en_escaparate
              ? "border-sky-500 bg-sky-500/15 text-sky-500"
              : "border-border/60 text-muted-foreground hover:border-foreground/40"
          }`}
        >
          🏪 Escaparate
        </button>
        <button
          type="button"
          onClick={() => push({ uploaded: !p.uploaded })}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            p.uploaded
              ? "border-sky-500 bg-sky-500/15 text-sky-500"
              : "border-border/60 text-muted-foreground hover:border-foreground/40"
          }`}
        >
          📤 Subido
          {p.uploaded && p.uploaded_at ? (
            <span className="ml-1 font-normal opacity-80">{horaCorta(p.uploaded_at)}</span>
          ) : null}
        </button>
        <button
          type="button"
          onClick={() => push({ sold: !p.sold })}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            p.sold
              ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
              : "border-border/60 text-muted-foreground hover:border-foreground/40"
          }`}
        >
          💰 Vendió
        </button>
      </div>
    </div>
  );
}
