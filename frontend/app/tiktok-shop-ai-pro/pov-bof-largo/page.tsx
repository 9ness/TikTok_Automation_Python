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

import { nombreDescarga } from "@/lib/descargas";

import { ApiError } from "@/lib/api";
import { horaCorta, fechaCorta } from "@/lib/hora";
import {
  useEstadoDeUsuario,
  useEstadoRecordado,
} from "@/lib/hooks/useEstadoRecordado";
import {
  esVentaNueva,
  FUENTE_TOP_VENDIDOS,
  verTopVendidos,
} from "@/lib/topVendidos";
import { BotonDescarga } from "@/components/tiktok-shop-ai-pro/BotonDescarga";
import {
  alProgresoDeFichero,
  alSubirCadaFichero,
  haySubidaNativa,
  subirConLaApp,
} from "@/lib/subidaNativa";
import { MontadoEl } from "@/components/tiktok-shop-ai-pro/MontadoEl";
import { ChipAjuste } from "@/components/tiktok-shop-ai-pro/ChipAjuste";
import { FiltroSoloUrl } from "@/components/tiktok-shop-ai-pro/FiltroSoloUrl";
import { Caja, OSepara, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { MagnificSpaces } from "@/components/tiktok-shop-ai-pro/MagnificSpaces";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { PrecioAMano } from "@/components/tiktok-shop-ai-pro/PrecioAMano";
import { TextosDelAdmin } from "@/components/tiktok-shop-ai-pro/TextosDelAdmin";
import { useEsPro, useMe } from "@/lib/queries/auth";
import { SincronizarTopVendidos } from "@/components/tiktok-shop-ai-pro/SincronizarTopVendidos";
import { VideoModal } from "@/components/ui/video-modal";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import {
  buildCleanPhotoDownloadUrl,
  useActivarCuentaEchoTik,
  useBorrarCuentaEchoTik,
  useBorrarMiProducto,
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
  useGuionesLote,
  useClipSCarpetaLargo,
  useModoGuion,
  useSetModoGuion,
  useFoldersLargo,
  useMarkCompletedLargo,
  useMarcarPendienteLargo,
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
import { useRefrescarAlVolver } from "@/lib/hooks/useRefrescarAlVolver";
import { useAlTerminarJob } from "@/lib/hooks/useAlTerminarJob";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}


/** Los dos flujos de la carpeta: el guion lleva la frase de plazos o no, según
 *  el precio. Se bajan por separado porque no se generan igual. */
/** Qué subconjunto se baja.
 *
 *  Aquí NO se reparte por normal/plazos como en el POV BOF: en este nicho todos
 *  los vídeos llevan varios clips y el flujo de plazos no cambia lo que hay que
 *  bajar, así que esos dos botones no servían para nada.
 *
 *  Lo que sí importa es (1) si el producto tiene ya enlazada su ficha de TikTok
 *  Shop —es con los que se trabaja— y (2) cuántos clips pide su guion, porque
 *  eso decide cuántos hay que generar en Magnific. Los de 3 y 4 se cuentan
 *  SOBRE los que tienen URL, que es el conjunto de trabajo.
 */
type Filtro = "todas" | "url" | "clips2" | "clips3" | "clips4";

interface ParaFiltrar {
  product_url?: string;
  clips_necesarios?: number;
}

// Cuántos clips pide un guion es lo que más trabajo cambia (hay que generar uno
// más en Magnific por cada uno), así que se ve de un vistazo: una franja en el
// lado de la tarjeta y un distintivo junto al precio, del MISMO color que su
// botón de descarga.
//
// Los de DOS también van marcados. Antes no: eran "lo normal" y se dejaban sin
// color. Pero en una carpeta mezclada eso convierte al más común en el único
// que no se distingue —y en el único que no se podía bajar por separado—, así
// que había que ir producto a producto. Los colores son los MISMOS del POV BOF
// corto para que las dos pantallas se lean igual.
const BORDE_CLIPS: Record<number, string> = {
  2: "border-l-4 border-l-lime-500",
  3: "border-l-4 border-l-amber-500",
  4: "border-l-4 border-l-rose-500",
};

const CHIP_CLIPS: Record<number, string> = {
  2: "bg-lime-500/15 text-lime-500",
  3: "bg-amber-500/15 text-amber-500",
  4: "bg-rose-500/15 text-rose-500",
};

/** Cómo se nombra cada subconjunto cuando no hay nada que bajar. */
function textoFiltro(filtro: Filtro): string {
  if (filtro === "url") return "con la ficha enlazada";
  if (filtro === "clips2") return "de 2 clips con la ficha enlazada";
  if (filtro === "clips3") return "de 3 clips con la ficha enlazada";
  if (filtro === "clips4") return "de 4 clips con la ficha enlazada";
  return "";
}

/** Clips que pide el guion de este producto (2 si aún no hay guion). */
function clipsDe(p: ParaFiltrar): number {
  return Math.min(4, p.clips_necesarios || 2);
}

function cuadra(p: ParaFiltrar, filtro: Filtro): boolean {
  if (filtro === "todas") return true;
  const conUrl = Boolean(p.product_url);
  if (filtro === "url") return conUrl;
  const pide = filtro === "clips2" ? 2 : filtro === "clips3" ? 3 : 4;
  return conUrl && clipsDe(p) === pide;
}

/** EchoTik apagado (ver la misma bandera en el Nicho POV BOF). */
const MOSTRAR_ECHOTIK = false;

export default function PovBofLargoPage() {
  const qc = useQueryClient();
  // En cuanto la cola dice que un montaje terminó, se repregunta la lista. El
  // sondeo de 5 s ya lo hacía, pero tarde —y se pausa si la pestaña no está
  // delante—, así que el vídeo terminado tardaba en salir en su tarjeta.
  useAlTerminarJob(() => {
    void qc.invalidateQueries({ queryKey: largoKeys.all });
  });
  // Y al volver a la app: los trabajos que terminan con la pantalla en segundo
  // plano no los ve el enganche de arriba, y la lista se queda desfasada.
  useRefrescarAlVolver(() => {
    void qc.invalidateQueries({ queryKey: largoKeys.all });
  });
  // Solo el admin ve el space de "foto con IA": Ana y Mauro trabajan con la
  // foto limpia del Drive.
  const esAdmin = useMe().data?.rol === "admin";

  const sources = useSourcesLargo();
  const [source, setSource] = useEstadoDeUsuario("povbof-largo:fuente", "");
  const activaSource = source || sources.data?.[0]?.slug || "";

  const [showFotos, setShowFotos] = useState(false);
  const [picked, setPicked] = useEstadoDeUsuario<string | null>("povbof-largo:carpeta", null);
  const [verVendidos, setVerVendidos] = useState(false);
  const [verEscaparate, setVerEscaparate] = useState(false);

  // La app avisa de cada fichero que termina de subir. Sin esto el hueco se
  // quedaría sin marcar hasta recargar a mano.
  useEffect(() => alSubirCadaFichero(() => {
    void qc.invalidateQueries({ queryKey: largoKeys.all });
  }), [qc]);

  const folders = useFoldersLargo(activaSource);
  const markCompleted = useMarkCompletedLargo(activaSource);
  const marcarPendiente = useMarcarPendienteLargo(activaSource);
  const voces = useVocesLargo();

  const data = folders.data;
  const folder = picked ?? data?.current ?? null;

  const photos = usePhotos(activaSource, folder);
  const prompts = usePrompts();
  const productosQ = useProductosLargo(activaSource, folder ?? "");
  const items = productosQ.data?.items ?? [];
  const extraerTextos = useExtraerTextos();
  // Los textos son del producto y se comparten: los extrae solo el admin.
  // El GUION no: es de cada uno, así que ese botón se queda.
  const esPro = useEsPro();
  const buscarUrls = useBuscarUrlsCarpeta();
  const guionesLote = useGuionesLote();
  const clipSCarpeta = useClipSCarpetaLargo();
  const modoGuion = useModoGuion(source);
  const setModo = useSetModoGuion();
  // Cuál está puesto en la carpeta (0 = mezclados), para marcarlo.
  const clipSCarpetaActual = (() => {
    const vistos = new Set(items.map((p) => p.clip_s || 10));
    return vistos.size === 1 ? [...vistos][0] : 0;
  })();
  // Igual para el estilo de guion: "" = mezclados en esta carpeta.
  //
  // `recienElegido` manda mientras llega la respuesta: repreguntar la lista
  // relee la carpeta del Drive y son 10-15s, así que al pulsar seguía marcado
  // el anterior y parecían los dos a la vez (el que tocas se queda además con
  // el borde de foco).
  // El modo es del CATÁLOGO. `recienElegido` manda mientras llega la
  // respuesta, para que el botón se marque al tocarlo.
  const [recienElegido, setRecienElegido] = useState("");
  useEffect(() => setRecienElegido(""), [source]);
  const estiloActual = recienElegido || modoGuion.data?.estilo || "precio";
  // Verde = precio, ámbar = dolor. El color dice de un vistazo con qué gancho
  // se está trabajando esta carpeta, sin leer.
  const COLOR_ESTILO: Record<string, string> = {
    precio: "border-emerald-500 bg-emerald-500/15 text-emerald-400",
    dolor: "border-amber-500 bg-amber-500/15 text-amber-400",
  };
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

  const esTopVendidos = activaSource === FUENTE_TOP_VENDIDOS;
  // Trabajar solo con los que ya tienen la ficha enlazada: son los que se van
  // a subir, y en una carpeta a medias el resto solo estorba. Filtra lo que se
  // VE, y como los botones cuentan sobre lo que se ve, también lo que se baja.
  const [soloConUrl, setSoloConUrl] = useEstadoDeUsuario("largo:solo-url", false);
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

  const itemsVisibles = useMemo(() => {
    const base = verTopVendidos(lista, {
      activo: esTopVendidos,
      soloSinSubir,
      yaSubido: (p) => p.uploaded,
    });
    return soloConUrl ? base.filter((p) => Boolean(p.product_url)) : base;
  }, [lista, esTopVendidos, soloSinSubir, soloConUrl]);
  const conUrlEnCarpeta = lista.filter((p) => Boolean(p.product_url)).length;
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
  // Los conjuntos que de verdad se bajan aquí: los que tienen la ficha
  // enlazada, y dentro de esos, los que piden 3 y 4 clips.
  const fotoConUrl = enPantalla.filter((p) => p.clean_photo_id && cuadra(p, "url")).length;
  const foto2 = enPantalla.filter((p) => p.clean_photo_id && cuadra(p, "clips2")).length;
  const foto3 = enPantalla.filter((p) => p.clean_photo_id && cuadra(p, "clips3")).length;
  const foto4 = enPantalla.filter((p) => p.clean_photo_id && cuadra(p, "clips4")).length;
  const videoConUrl = enPantalla.filter((p) => p.video_path && cuadra(p, "url")).length;
  const video2 = enPantalla.filter((p) => p.video_path && cuadra(p, "clips2")).length;
  const video3 = enPantalla.filter((p) => p.video_path && cuadra(p, "clips3")).length;
  const video4 = enPantalla.filter((p) => p.video_path && cuadra(p, "clips4")).length;
  // "Textos + guiones" actúa sobre la CARPETA abierta, así que su total es el
  // de la carpeta y no el de lo que se ve.
  const totalCarpeta = items.length;
  const conTexto = items.filter((p) => p.titulo).length;
  // Un guion escrito en el OTRO modo no cuenta como hecho: al pasar la
  // carpeta a "punto de dolor", los diez de precio dejan de valer y el
  // contador tiene que decir 0/10, no 10/10.
  const guionSirve = (p: ProductoLargo) =>
    Boolean(p.guion) &&
    (p.guion_estilo || "precio") === (p.estilo_guion || "precio");
  const conGuion = items.filter(guionSirve).length;
  const subidos = enPantalla.filter((p) => p.uploaded).length;
  const enEscaparate = enPantalla.filter((p) => p.en_escaparate).length;
  /** Le falta el guion o el que tiene es del otro modo (escrito antes de que
   *  existieran los plazos, o antes de corregir el precio). Los desfasados
   *  cuentan como pendientes: si no, el botón dice "guiones al día" mientras
   *  media carpeta lleva un guion sin la frase de plazos. */
  const pendienteGuion = (p: ProductoLargo) =>
    Boolean(p.titulo) &&
    (!guionSirve(p) || p.modo_plazos !== p.guion_plazos);
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
          : `Ningún vídeo montado ${textoFiltro(filtro)}`,
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
        a.download =
          nombreDescarga(String(i + 1).padStart(2, "0"), suya, `${p.producto}${sufijo}`) + ".mp4";
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
          : `No hay productos con foto ${textoFiltro(filtro)}`,
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
        a.download = nombreDescarga(
          String(i + 1).padStart(2, "0"), suya, `${p.producto}${sufijo}`,
        );
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
    // Por la COLA, no en el navegador: son diez llamadas a Gemini seguidas y
    // antes había que quedarse en la pantalla esperando a que acabaran.
    // Los que YA tienen guion van en la lista de forzados: el trabajo sabe
    // solo cuáles no lo tienen, pero no que a estos les cambió el título.
    guionesLote.mutate(
      {
        source: activaSource,
        folder,
        productos: pend.filter((p) => p.guion).map((p) => p.producto),
      },
      {
        onSuccess: () => {
          toast.success(`${pend.length} guion(es) en la cola`);
          openQueue();
        },
        onError: (e: unknown) => toast.error(err(e)),
      },
    );
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
          toast.success("Textos extraídos · los guiones van a la cola");
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

  function togglePendiente(pendiente: boolean) {
    if (!folder) return;
    marcarPendiente.mutate(
      { source: activaSource, folder, pendiente },
      {
        onSuccess: () =>
          toast.success(
            pendiente
              ? `"${folder}" con vídeos listos para subir`
              : `"${folder}" ya no está pendiente de subir`,
          ),
        onError: (e) =>
          toast.error(
            `No se pudo guardar: ${e instanceof ApiError ? e.message : String(e)}`,
          ),
      },
    );
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
              className={`break-words leading-tight rounded-lg border px-3 py-2 text-xs transition sm:text-sm ${
                activaSource === s.slug
                  ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {CATALOGOS_PROPIOS.includes(activaSource) && (
          <AltaMiProducto
            source={activaSource}
            onCreado={() => void folders.refetch()}
          />
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
              className={`break-words leading-tight rounded border px-2 py-1 text-[10px] transition ${
                // La carpeta ABIERTA se pinta según esté hecha o no: en verde
                // si ya se completó y en azul si aún no. Antes la abierta y las
                // completadas eran del mismo color y no se sabía si la que
                // tenías delante estaba lista o te faltaba terminarla.
                // Y el NARANJA manda sobre los dos: "tiene los vídeos hechos
                // pero sin subir" es lo que se busca de un vistazo cuando se
                // preparan carpetas de días futuros. Que esté completada se
                // sigue leyendo por el ✓.
                f.pendiente_subir
                  ? folder === f.name
                    ? "border-orange-500 bg-orange-500/20 font-semibold text-orange-400"
                    : "border-orange-500/50 bg-orange-500/10 text-orange-400"
                  : folder === f.name
                    ? f.completed
                      ? "border-emerald-500 bg-emerald-500/15 font-semibold text-emerald-500"
                      : "border-sky-500 bg-sky-500/15 font-semibold text-sky-400"
                    : f.completed
                      ? "border-emerald-500/40 text-emerald-500"
                      : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {f.pendiente_subir && "📤 "}
              {f.completed && "✓ "}
              {/* El curso borró esta carpeta entera: se sigue trabajando
                  desde nuestra copia, con el progreso de siempre. */}
              {f.desde_copia && "🗄️ "}
              {f.name}
              {/* Cuántos productos de esta carpeta tienen ya la ficha
                  enlazada: es el trabajo que hay dentro. Sin esto había que
                  entrar carpeta por carpeta para descubrir que estaba a cero.
                  No sale cuando es 0 — un cero en cada chip es ruido. */}
              {!!f.con_url && (
                <span className="ml-1 rounded-full bg-emerald-500/15 px-1 py-px text-[9px] font-semibold text-emerald-500">
                  {f.con_url}
                </span>
              )}
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

          {/* Los dos estados de la carpeta, uno al lado del otro: cerrarla y
              dejarla apartada con los vídeos hechos para subirlos otro día.
              Igual que en el POV BOF. */}
          <div className="flex items-stretch gap-2">
            <button
              type="button"
              onClick={() => toggleCompleted(!currentItem?.completed)}
              disabled={markCompleted.isPending}
              title="Marca la carpeta como hecha y salta a la siguiente"
              className={`flex min-w-0 flex-1 items-center justify-center gap-2 truncate rounded-lg px-3 py-3 text-sm font-semibold transition disabled:opacity-50 ${
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
              {currentItem?.completed ? "Desmarcar" : "Completada"}
            </button>
            <button
              type="button"
              onClick={() => togglePendiente(!currentItem?.pendiente_subir)}
              disabled={marcarPendiente.isPending}
              className={`flex items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold shrink-0 transition disabled:opacity-50 ${
                currentItem?.pendiente_subir
                  ? "border-orange-500 bg-orange-500/20 text-orange-400"
                  : "border-border/60 text-muted-foreground hover:border-orange-500 hover:text-orange-400"
              }`}
              title="Los vídeos están hechos pero faltan por subir: la carpeta se marca en naranja en el listado"
            >
              {marcarPendiente.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              {currentItem?.pendiente_subir ? "Pendiente ✓" : "Pendiente"}
            </button>
          </div>
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

          {/* EL MODO, antes que los pasos: decide qué escribe la IA y por
              tanto cómo suena el vídeo entero, así que es lo primero que hay
              que elegir al abrir una carpeta — no un ajuste enterrado en el
              paso 1. El color acompaña (violeta precio, ámbar dolor). */}
          <div
            className={`flex flex-wrap items-center gap-2 rounded-xl border p-3 transition ${
              estiloActual === "dolor"
                ? "border-amber-500/40 bg-amber-500/[0.06]"
                : "border-violet-500/40 bg-violet-500/[0.06]"
            }`}
          >
            <span className="text-sm font-semibold">
              Modo del guion{" "}
              <span className="text-[11px] font-normal text-muted-foreground">
                · todo el catálogo
              </span>
            </span>
            <div className="ml-auto flex gap-1.5">
              {[
                { k: "precio", txt: "Precio" },
                { k: "dolor", txt: "Punto de dolor" },
              ].map((e) => (
                <button
                  key={e.k}
                  type="button"
                  disabled={setModo.isPending}
                  onClick={() => {
                    setRecienElegido(e.k);
                    setModo.mutate(
                      { source, estilo: e.k },
                      {
                        onSuccess: () => toast.success(`Modo: ${e.txt}`),
                        onError: (err: unknown) =>
                          toast.error(err instanceof ApiError ? err.message : String(err)),
                      },
                    );
                  }}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold outline-none transition disabled:opacity-50 ${
                    estiloActual === e.k
                      ? COLOR_ESTILO[e.k]
                      : "border-border/60 text-muted-foreground"
                  }`}
                >
                  {e.txt}
                </button>
              ))}
            </div>
            <p className="w-full text-[11px] leading-relaxed text-muted-foreground">
              {estiloActual === "dolor"
                ? "El vídeo empieza con tres a cinco problemas dirigidos al espectador y el precio va al final."
                : "El vídeo empieza por el precio (“Han ajustado el precio de…”) y el punto de dolor va en medio."}{" "}
              Cada modo lleva su propio progreso, guiones, clips y vídeos:
              cambiar aquí no pisa lo del otro. El escaparate, los vendidos y
              los textos sí son comunes.
            </p>
          </div>

          <Paso
            // Verde/violeta = precio, ámbar = punto de dolor. El paso entero
            // se tiñe: es lo que pediste para saber en qué gancho estás sin
            // leer.
            color={estiloActual === "dolor" ? "ambar" : "violeta"}
            n={1}
            titulo="Preparar textos y guion"
            hint={esTopVendidos ? "Aquí los textos se copian del producto original: no se vuelven a leer con IA, que es lo que descuadraba la carpeta." : "Los textos salen de la ficha; el guion lo escribe la IA para ese producto y es lo que marca cuántos clips harán falta."}
            extra={`${conGuion}/${totalProductos} con guion`}
          >
            {esPro ? (
              <TextosDelAdmin hechos={conTexto} total={totalCarpeta} />
            ) : (
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
            )}

            {/* Guion para toda LA CARPETA, en vez de tarjeta a tarjeta.
                Necesitan tener textos primero. Lo de todo el catálogo vive en
                Configuración, igual que la extracción de textos: aquí solo
                está lo de la carpeta que tienes abierta. */}
            <button
              type="button"
              onClick={() => void generarTodosGuiones()}
              disabled={guionesLote.isPending || !sinGuion}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/60 bg-card px-3 py-2 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/10 disabled:opacity-50"
            >
              {guionesLote.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  Encolando…
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
            {/* La duración de clip para TODA la carpeta. Cambia cuántos
                huecos pide cada producto, así que se elige una vez por tanda y
                no tarjeta a tarjeta. */}
            <div className="flex items-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-[11px] text-muted-foreground">
              <span>Clips de toda la carpeta:</span>
              {[8, 10].map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={clipSCarpeta.isPending}
                  onClick={() =>
                    clipSCarpeta.mutate(
                      { source, folder, clip_s: s },
                      {
                        onSuccess: (r: { productos: number }) =>
                          toast.success(`${s}s en ${r.productos} producto(s)`),
                        onError: (e: unknown) =>
                          toast.error(e instanceof ApiError ? e.message : String(e)),
                      },
                    )
                  }
                  className={`rounded border px-2 py-1 font-semibold transition disabled:opacity-50 ${
                    clipSCarpetaActual === s
                      ? "border-violet-500 bg-violet-500/15 text-violet-400"
                      : "border-border/60 hover:border-violet-500 hover:text-violet-400"
                  }`}
                >
                  {s}s
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              <div
                className={`flex items-center justify-center gap-1.5 break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-semibold ${
                  subidos === totalProductos && totalProductos > 0
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                    : "border-border/60 text-muted-foreground"
                }`}
              >
                <span className="break-words leading-tight">📤 Subidos {subidos}/{totalProductos}</span>
              </div>
              <button
                type="button"
                onClick={() => setVerEscaparate(true)}
                className={`flex items-center justify-center gap-1.5 break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-semibold transition ${
                  enEscaparate === totalProductos && totalProductos > 0
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                    : "border-sky-500/50 bg-sky-500/10 text-sky-500 hover:bg-sky-500/20"
                }`}
              >
                <span className="break-words leading-tight">🏪 Escaparate {enEscaparate}/{totalProductos}</span>
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
                  <span className="break-words leading-tight">
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
            hint="Baja las fotos y crea los clips en Magnific. Cada vídeo lleva dos clips, o tres o cuatro si el guion es largo: cada tarjeta lleva una franja de color según cuántos pida, y hay un botón por cada número."
            extra={`${conFoto} foto(s)`}
          >
            <p className="text-[10px] font-semibold text-muted-foreground">
              Primero, baja las fotos
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              <BotonDescarga
                onClick={() => void downloadCleanPhotos()}
                cargando={downloadingPhotos}
                progreso={downloadProgress}
                disabled={!conFoto}
                etiqueta={`Fotos ${conFoto}/${totalProductos}`}
              />
              <BotonDescarga
                onClick={() => void downloadCleanPhotos("url")}
                cargando={false}
                disabled={downloadingPhotos || !fotoConUrl}
                etiqueta={`🔗 Con URL (${fotoConUrl})`}
                tono="url"
              />
            </div>
            {/* Los que piden 3 y 4 clips, por separado: es lo que decide
                cuántos hay que generar en Magnific, así que se hace por tandas.
                Solo salen si hay alguno — en una carpeta donde todos van con
                dos clips, estos botones serían dos huecos apagados. */}
            {(foto2 > 0 || foto3 > 0 || foto4 > 0) && (
              <>
                <p className="pt-0.5 text-[10px] text-muted-foreground">
                  De los que tienen URL, por clips:
                </p>
                {/* Tres columnas: los de dos clips son los más numerosos y
                    antes no tenían botón, así que había que bajarlos de uno en
                    uno o llevarse la carpeta entera. */}
                <div className="grid grid-cols-3 gap-1.5">
                  <BotonDescarga
                    onClick={() => void downloadCleanPhotos("clips2")}
                    cargando={false}
                    disabled={downloadingPhotos || !foto2}
                    etiqueta={`2 clips (${foto2})`}
                    tono="clips2"
                  />
                  <BotonDescarga
                    onClick={() => void downloadCleanPhotos("clips3")}
                    cargando={false}
                    disabled={downloadingPhotos || !foto3}
                    etiqueta={`3 clips (${foto3})`}
                    tono="clips3"
                  />
                  <BotonDescarga
                    onClick={() => void downloadCleanPhotos("clips4")}
                    cargando={false}
                    disabled={downloadingPhotos || !foto4}
                    etiqueta={`4 clips (${foto4})`}
                    tono="clips4"
                  />
                </div>
              </>
            )}

            <p className="pt-1 text-[10px] font-semibold text-muted-foreground">
              Y luego, créalos
            </p>
            {/* Del de foto limpia solo hace falta el de plazos: aquí todos los
                vídeos llevan dos clips. El de "foto con IA" solo el admin. */}
            <MagnificSpaces
              spaces={[
                "foto_limpia_plazos",
                ...(esAdmin ? (["foto_ia", "foto_ia_2"] as const) : []),
              ]}
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

          <Paso
            n={3}
            color="azul"
            titulo="Descargar lo ya montado"
            hint="Los vídeos con la voz puesta, listos para subir a TikTok. Se bajan en el orden que ves en pantalla."
            extra={`${conVideo}/${totalProductos}`}
          >
            <div className="grid grid-cols-2 gap-1.5">
              <BotonDescarga
                onClick={() => void downloadVideos()}
                cargando={downloadingVideos}
                progreso={videoProgress}
                disabled={!conVideo}
                etiqueta={`Vídeos ${conVideo}/${totalProductos}`}
              />
              <BotonDescarga
                onClick={() => void downloadVideos("url")}
                cargando={false}
                disabled={downloadingVideos || !videoConUrl}
                etiqueta={`🔗 Con URL (${videoConUrl})`}
                tono="url"
              />
            </div>
            {(video2 > 0 || video3 > 0 || video4 > 0) && (
              <>
                <p className="pt-0.5 text-[10px] text-muted-foreground">
                  De los que tienen URL, por clips:
                </p>
                {/* Tres columnas: los de dos clips son los más numerosos y
                    antes no tenían botón, así que había que bajarlos de uno en
                    uno o llevarse la carpeta entera. */}
                <div className="grid grid-cols-3 gap-1.5">
                  <BotonDescarga
                    onClick={() => void downloadVideos("clips2")}
                    cargando={false}
                    disabled={downloadingVideos || !video2}
                    etiqueta={`2 clips (${video2})`}
                    tono="clips2"
                  />
                  <BotonDescarga
                    onClick={() => void downloadVideos("clips3")}
                    cargando={false}
                    disabled={downloadingVideos || !video3}
                    etiqueta={`3 clips (${video3})`}
                    tono="clips3"
                  />
                  <BotonDescarga
                    onClick={() => void downloadVideos("clips4")}
                    cargando={false}
                    disabled={downloadingVideos || !video4}
                    etiqueta={`4 clips (${video4})`}
                    tono="clips4"
                  />
                </div>
              </>
            )}
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

          <FiltroSoloUrl
            activo={soloConUrl}
            onChange={setSoloConUrl}
            conUrl={conUrlEnCarpeta}
            total={lista.length}
          />

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
/** Los dos catálogos del operador: muestras gratuitas y tareas pagadas. */
const CATALOGOS_PROPIOS = ["mis_productos", "tareas_productos"];

function AltaMiProducto({
  source = "mis_productos",
  onCreado,
}: {
  source?: string;
  onCreado: () => void;
}) {
  const crear = useCrearMiProducto();
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const refLimpia = useRef<HTMLInputElement>(null);
  const refFicha = useRef<HTMLInputElement>(null);
  // Capturas de MÁS (características, medidas, qué trae). Son las que dan de
  // qué hablar cuando la tienda pide 30 segundos; con el título solo, Gemini
  // estira lo mismo con más adjetivos. El catálogo es el mismo que el del POV
  // BOF, así que subirlas aquí vale para las dos pantallas.
  const refExtras = useRef<HTMLInputElement>(null);
  const [extras, setExtras] = useState<File[]>([]);
  const [abierto, setAbierto] = useState(false);

  function enviar() {
    if (!limpia) {
      toast.error("Falta la foto del producto.");
      return;
    }
    crear.mutate(
      { fotoLimpia: limpia, fotoFicha: ficha, fotosExtra: extras, source },
      {
        onSuccess: (r) => {
          toast.success(
            `Producto ${r.producto} añadido a «${r.carpeta}»` +
              (extras.length ? ` · ${extras.length} captura(s) más` : ""),
          );
          setLimpia(null);
          setFicha(null);
          setExtras([]);
          if (refLimpia.current) refLimpia.current.value = "";
          if (refFicha.current) refFicha.current.value = "";
          if (refExtras.current) refExtras.current.value = "";
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
      <label className="flex cursor-pointer flex-col gap-1 rounded-lg border border-dashed border-border/60 p-2.5 transition hover:border-emerald-500/60">
        <span className="text-[11px] font-semibold">Más capturas (opcional)</span>
        <span className="text-[10px] text-muted-foreground">
          Características, medidas, qué trae. Con ellas se puede pedir un guion
          de 30 segundos o más; con el título solo, no.
        </span>
        <input
          ref={refExtras}
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => setExtras(Array.from(e.target.files ?? []))}
          className="mt-1 block w-full text-[10px] text-muted-foreground file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-[10px]"
        />
        {!!extras.length && (
          <span className="truncate text-[10px] text-emerald-500">
            ✓ {extras.length} captura(s)
          </span>
        )}
      </label>
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
  const borrarMio = useBorrarMiProducto();
  const quitarClip = useQuitarClipLargo();
  const buscarUrl = useBuscarProductoUrl();
  const hashtags = useHashtags().data ?? [];
  const refs = {
    1: useRef<HTMLInputElement>(null),
    2: useRef<HTMLInputElement>(null),
    3: useRef<HTMLInputElement>(null),
    4: useRef<HTMLInputElement>(null),
  };

  const [verFoto, setVerFoto] = useState(false);
  const [verTools, setVerTools] = useState(false);
  const [verGuion, setVerGuion] = useState(false);
  const [verVoz, setVerVoz] = useState(false);
  // El guion guardado se escribió en el otro modo (con o sin la frase de
  // plazos). No es un error: pasa con todo lo escrito antes de que existieran
  // los plazos y cada vez que se corrige un precio.
  // Desfasado por dos motivos: escrito con el otro modo de plazos, o con el
  // otro MODO de guion (precio/dolor). En los dos casos no sirve.
  const guionDesfasado =
    Boolean(p.guion) &&
    (p.modo_plazos !== p.guion_plazos ||
      (p.guion_estilo || "precio") !== (p.estilo_guion || "precio"));
  // Cuántos clips pide ESTE guion. Lo calcula el backend con los caracteres
  // (la voz aún no existe cuando hay que decidirlo).
  const necesarios = Math.min(4, p.clips_necesarios || 2);
  // Duración de los clips que genera el operador. No es cosmética: el mismo
  // guion son 3 clips de 8s o 2 de 10s, así que cambiarla cambia los huecos.
  const clipS = p.clip_s || 10;
  const [verVideo, setVerVideo] = useState(false);
  // Progreso POR SLOT (null = ese clip no se está subiendo). Así se puede subir
  // el clip 2 mientras el 1 va por la mitad, y cada tarjeta es independiente de
  // las demás (subir clips de varios productos a la vez).
  const [pcts, setPcts] = useState<{
    1: number | null;
    2: number | null;
    3: number | null;
    4: number | null;
  }>({ 1: null, 2: null, 3: null, 4: null });
  // Qué fichero está subiendo la app en cada hueco. Los dos lados se casan por
  // NOMBRE porque es lo único que viaja por el puente: los bytes se quedan en
  // la app (un vídeo en base64 serían 30 MB de cadena).
  const [ficheroApp, setFicheroApp] = useState<Record<number, string>>({});
  /** El porcentaje que manda la app, al hueco que le toca. */
  useEffect(() => {
    const huecos = Object.entries(ficheroApp);
    if (!huecos.length) return;
    const quitarProgreso = alProgresoDeFichero((nombre, pct) => {
      const hueco = huecos.find(([, n]) => n === nombre);
      if (hueco) setPcts((prev) => ({ ...prev, [Number(hueco[0])]: pct }));
    });
    const quitarFin = alSubirCadaFichero((nombre) => {
      const hueco = huecos.find(([, n]) => n === nombre);
      if (!hueco) return;
      const slot = Number(hueco[0]);
      setPcts((prev) => ({ ...prev, [slot]: null }));
      setFicheroApp((prev) => {
        const copia = { ...prev };
        delete copia[slot];
        return copia;
      });
    });
    return () => {
      quitarProgreso();
      quitarFin();
    };
  }, [ficheroApp]);

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
  function subirClip(slot: 1 | 2 | 3 | 4, file: File) {
    const campos = {
      source,
      folder,
      producto: p.producto,
      slot: String(slot),
      sexo,
      con_gancho: String(tools.gancho),
      con_titulo: String(tools.titulo),
      con_cta: String(tools.cta),
      con_flecha: String(tools.flecha),
    };
    // Si la app sabe subir por su cuenta, se le deja: con ocho productos a
    // tres clips son veinticuatro esperas con la pantalla encendida. Su
    // servicio aguanta el móvil bloqueado; en el navegador esto no existe y
    // se sigue por el XHR de siempre.
    if (haySubidaNativa()) {
      const lanzada = subirConLaApp({
        url: `${apiBase}/api/v1/nicho-pov-bof-largo/clip/upload`,
        apiKey,
        tareas: [{ nombre: file.name, campos }],
      });
      if (lanzada) {
        const ref = refs[slot].current;
        if (ref) ref.value = "";
        // El botón se pone a 0% aquí: el primer aviso de la app tarda lo que
        // tarde el primer trozo, y hasta entonces no se vería que va.
        setPcts((prev) => ({ ...prev, [slot]: 0 }));
        setFicheroApp((prev) => ({ ...prev, [slot]: file.name }));
        toast.success("Subiendo con la app: puedes bloquear el móvil");
        return;
      }
    }

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
      } ${BORDE_CLIPS[necesarios] ?? ""}`}
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
              {/* Cuántos clips pide. Va arriba, junto al precio, y no solo en
                  el aviso del final de la tarjeta: es lo que hay que saber
                  ANTES de ponerse a generarlos, y desplazándose se ve por la
                  franja del lado sin tener que abrir nada.
                  También en los de dos: dejarlos sin marcar hacía del caso más
                  común el único que no se reconocía de un vistazo. */}
              {necesarios >= 2 && (
                <span className={`rounded px-1.5 py-0.5 font-semibold ${CHIP_CLIPS[necesarios]}`}>
                  🎞️ {necesarios} clips
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
        <BotonUrl
          url={p.product_url}
          source={source}
          folder={p.folder || folder}
          producto={p.producto}
        />
        {p.clean_photo_id && (
          <a
            href={buildCleanPhotoDownloadUrl(source, folder, p.producto)}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40 hover:text-foreground"
          >
            <Download className="h-3 w-3" /> Foto
          </a>
        )}
        {/* La fecha va al final: los botones que se PULSAN mandan, y esto
            solo se mira (para saber qué productos añadió hoy el curso). */}
        {p.subida_at ? (
          <span
            title="Cuándo se subió al Drive del curso"
            className="self-center text-[10px] text-muted-foreground"
          >
            📅 {fechaCorta(p.subida_at)}
          </span>
        ) : null}
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
          className="block break-words leading-tight rounded-md border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-[11px] text-emerald-500"
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

      {/* Una sola fila para los tres ajustes de la tarjeta (ver `ChipAjuste`):
          el guion se lee una vez al escribirlo, las herramientas van casi
          siempre las cuatro y la voz casi siempre en Auto. Cada uno ocupaba
          una fila entera para enseñar algo que no se toca. La de voz y
          herramientas sale aunque no haya guion todavía: son ajustes del
          producto, no del guion. */}
      <div className="flex items-stretch gap-1.5">
        {p.guion && (
          <ChipAjuste
            icono={guionDesfasado ? "⚠️" : "🎬"}
            // Los SEGUNDOS delante: es lo que decide si el vídeo sirve para
            // el reto, y los caracteres solo interesan si algo va mal.
            valor={
              p.segundos_min && p.segundos_max
                ? `${p.segundos_min}-${p.segundos_max}s`
                : `${p.guion_caracteres} car.`
            }
            abierto={verGuion}
            onToggle={() => setVerGuion((v) => !v)}
            aviso={guionDesfasado}
            title={
              p.segundos_min
                ? `Guion de ${p.guion_caracteres} caracteres · el vídeo durará entre ${p.segundos_min}s y ${p.segundos_max}s según la voz que salga`
                : `Guion · ${p.guion_caracteres} caracteres`
            }
          />
        )}
          <ChipAjuste
            icono={sexo === "auto" ? "🖐️" : sexo === "hombre" ? "👨" : "👩"}
            valor={sexo === "auto" ? "Auto" : sexo === "hombre" ? "Hombre" : "Mujer"}
            abierto={verVoz}
            onToggle={() => setVerVoz((v) => !v)}
            title="Quién pone la voz"
          />
          <ChipAjuste
            icono="✨"
            valor={`${Object.values(tools).filter(Boolean).length}/${TOOLS.length}`}
            abierto={verTools}
            onToggle={() => setVerTools((v) => !v)}
            title="Qué se añade al vídeo"
          />
      </div>

      {p.guion && verGuion && (
        <div className="space-y-1 rounded border border-border/60 bg-muted/30 p-2">
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
        </div>
      )}
      {!p.guion && (
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

      {verVoz && (
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
      )}

      {verTools && (
      <div className="space-y-1.5 rounded-md border border-border/60 p-2">
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
      </div>
      )}
      {/* El aviso se ve SIEMPRE, plegado o no: que el vídeo salga sin nada
          encima no puede quedar escondido detrás de un chip. */}
      {!Object.values(tools).some(Boolean) && (
        <p className="text-[10px] text-amber-500">Vídeo limpio: solo la voz, sin nada encima.</p>
      )}

      {/* Los clips. No se encola hasta tenerlos todos y el guion. Son DOS,
          salvo que la voz no quepa en veinte segundos: entonces hace falta un
          tercero (si no, el montaje estira los dos y el gesto se deforma). */}
      {/* SIEMPRE dos columnas. Con tres clips se ponían tres en fila, y en un
          móvil estrecho salen tres botones apretados; encima con cuatro ya eran
          dos filas de dos, así que la pantalla cambiaba de forma según el
          producto. Dos columnas es igual en todos los casos (2, 2+1, 2+2). */}
      {/* 8 o 10 segundos, pegado a los huecos porque es lo que cambia: con
          clips de 10s el mismo guion pide uno menos. */}
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
        <span>Clips de</span>
        {[8, 10].map((s) => (
          <button
            key={s}
            type="button"
            onClick={() =>
              setEstado.mutate({
                source,
                folder: p.folder || folder,
                producto: p.producto,
                clip_s: s,
              })
            }
            className={`rounded px-1.5 py-0.5 font-semibold transition ${
              clipS === s
                ? "bg-violet-500/20 text-violet-400"
                : "hover:text-foreground"
            }`}
          >
            {s}s
          </button>
        ))}
        <span className="ml-auto">
          {necesarios} hueco{necesarios === 1 ? "" : "s"}
        </span>
      </div>

      {/* Cuánto tiene que durar el guion. Lo normal es lo del curso (~20s);
          se sube cuando la tienda pide vídeos de 30 segundos por la muestra.
          Vale para los DOS estilos: el prompt que se manda es el del modo en
          el que estés (precio o dolor) con el tope reescrito, así que el vídeo
          largo sigue empezando por donde toca. Sale del mismo sitio que en el
          POV BOF —los textos del producto—, así que ponerlo aquí lo pone allí. */}
      <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
        <span>Guion de</span>
        {[0, 30, 40, 60].map((sg) => (
          <button
            key={sg}
            type="button"
            title={
              sg === 0
                ? "El del curso: ~356 caracteres, unos 20 segundos"
                : `~${Math.round(sg * 17.8)} caracteres. Necesita capturas del producto para tener qué contar`
            }
            onClick={() =>
              setEstado.mutate({
                source,
                folder: p.folder || folder,
                producto: p.producto,
                segundos_guion: sg,
              })
            }
            className={`rounded px-1.5 py-0.5 font-semibold transition ${
              (p.segundos_guion || 0) === sg
                ? "bg-amber-500/20 text-amber-500"
                : "hover:text-foreground"
            }`}
          >
            {sg === 0 ? "normal" : `${sg}s`}
          </button>
        ))}
        {!!p.segundos_guion && (
          <span className="ml-auto text-amber-500/80">
            rehaz el guion para aplicarlo
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {(
          [1, 2, 3, 4].slice(0, necesarios) as (1 | 2 | 3 | 4)[]
        ).map((slot) => {
          const puesto = [p.clip1, p.clip2, p.clip3, p.clip4][slot - 1];
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
      {/* Cuántos clips pide ya no se explica con una frase: lo dicen la franja
          del lado de la tarjeta y el distintivo de junto al precio, que se ven
          sin leer. Lo que sí hay que decir es cuándo NO se puede subir nada
          todavía. */}
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
            download={nombreDescarga(folder, p.producto) + ".mp4"}
            className="flex items-center justify-center gap-1.5 rounded-md border border-emerald-500/50 px-2 py-1.5 text-[11px] text-emerald-500"
          >
            <Download className="h-3.5 w-3.5" /> Descargar
          </a>
        </div>
      )}
      {p.video_path && <MontadoEl ts={p.video_listo_at} />}

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

      {/* Solo en "Mis productos": son los que sube el operador, así que también
          los puede quitar (los del curso son de solo lectura). Al borrar se
          cierra el hueco de la numeración, así que la carpeta no se queda en
          5, 7, 8. */}
      {CATALOGOS_PROPIOS.includes(source) && (
        <button
          type="button"
          disabled={borrarMio.isPending}
          onClick={() => {
            if (
              !window.confirm(
                `¿Quitar el producto ${p.producto}? Se borran sus dos fotos. ` +
                  "El hueco de numeración lo cierras luego con «reordenar».",
              )
            )
              return;
            borrarMio.mutate(
              { carpeta: folder, producto: p.producto, source },
              {
                onSuccess: () => {
                  toast.success(`Producto ${p.producto} borrado`);
                  void qc.invalidateQueries({ queryKey: largoKeys.all });
                },
                onError: (e) => toast.error(err(e)),
              },
            );
          }}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-red-500/60 hover:text-red-500 disabled:opacity-50"
        >
          {borrarMio.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Borrando…
            </>
          ) : (
            <>🗑️ Quitar este producto</>
          )}
        </button>
      )}
    </div>
  );
}
