"use client";

import {
  Check,
  Clapperboard,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Download,
  Link2 as LinkIcon,
  Loader2,
  Eye,
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
import { fechaCorta, horaCorta } from "@/lib/hora";
import {
  useEstadoDeUsuario,
  useEstadoRecordado,
} from "@/lib/hooks/useEstadoRecordado";
import {
  esVentaNueva,
  FUENTE_TOP_VENDIDOS,
  verTopVendidos,
} from "@/lib/topVendidos";
import {
  useCrearMiProducto,
  nichoPovBofKeys,
  buildCleanPhotoDownloadUrl,
  buildVideoUrl,
  buildPhotoUrl,
  useExtraerTextos,
  useFolders,
  useMarkCompleted,
  usePhotos,
  usePrompts,
  useProductos,
  useProductosTodos,
  refrescarDesdeDrive,
  useBuscarProductoUrl,
  useHashtags,
  useGuardarHashtags,
  useBuscarUrlsCarpeta,
  useEchoTikEstado,
  useGuardarEchoTik,
  useEchoTikCuentas,
  useGuardarCuentaEchoTik,
  useActivarCuentaEchoTik,
  useBorrarCuentaEchoTik,
  useSetEstado,
  useQuitarClip,
  useBorrarMiProducto,
  useSortearGuionPlazos,
  useSources,
  useVendidos,
  useSumarUnidades,
  useBuscarProductos,
  ANCHO_CHIP,
  ANCHO_VISOR,
} from "@/lib/queries/nichoPovBof";
import { BotonDescarga } from "@/components/tiktok-shop-ai-pro/BotonDescarga";
import { SubidaMasiva } from "@/components/tiktok-shop-ai-pro/SubidaMasiva";
import { Caja, OSepara, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { MagnificSpaces } from "@/components/tiktok-shop-ai-pro/MagnificSpaces";
import { PrecioAMano } from "@/components/tiktok-shop-ai-pro/PrecioAMano";
import { SincronizarTopVendidos } from "@/components/tiktok-shop-ai-pro/SincronizarTopVendidos";
import { TextosDelAdmin } from "@/components/tiktok-shop-ai-pro/TextosDelAdmin";
import { useEsPro, useMe } from "@/lib/queries/auth";
import { VideoModal } from "@/components/ui/video-modal";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type {
  ProductoBuscado,
  ProductoItem,
  VideoUploadResponse,
} from "@/lib/types/nichoPovBof";

/** EchoTik apagado a petición del operador: su cuota gratis no da para el
 *  volumen diario y de momento no lo usa. Poniéndolo a `true` vuelven el panel
 *  de credenciales y los botones de buscar la ficha del producto. */
const MOSTRAR_ECHOTIK = false;
// Ritmo medido con las voces reales de Fish, igual que en el POV BOF Largo.
const CAR_POR_SEG = 18.2;

/** Los dos flujos de la carpeta. Un producto lleva guion de plazos o el de
 *  siempre según su precio, y cada uno se genera distinto (dos clips o uno),
 *  así que se bajan por separado. `todas` es la carpeta entera. */
type Filtro = "todas" | "plazos" | "viejo";

function cuadra(p: { modo_plazos: boolean }, filtro: Filtro): boolean {
  if (filtro === "todas") return true;
  return filtro === "plazos" ? p.modo_plazos : !p.modo_plazos;
}

export default function NichoPovBofPage() {
  const [source, setSource] = useEstadoDeUsuario("povbof:fuente", "aleatorios_1");
  // Las fotos en crudo van colapsadas: ocupaban toda la pantalla.
  const [showFotos, setShowFotos] = useState(false);
  // Carpeta elegida a mano. Si es null se usa la "current" del backend
  // (la primera sin completar).
  const [picked, setPicked] = useEstadoDeUsuario<string | null>("povbof:carpeta", null);
  const [verVendidos, setVerVendidos] = useState(false);
  const [verEscaparate, setVerEscaparate] = useState(false);

  // Solo el admin ve el space de "foto con IA": Ana y Mauro trabajan con la
  // foto limpia del Drive.
  const esAdmin = useMe().data?.rol === "admin";

  const sources = useSources();
  const folders = useFolders(source);
  const markCompleted = useMarkCompleted(source);

  const openQueue = useDrawerStore((s) => s.openQueue);

  const data = folders.data;
  const folder = picked ?? data?.current ?? null;
  const photos = usePhotos(source, folder);

  // --- Fase 2: automatización de vídeos ---
  const prompts = usePrompts();
  const qc = useQueryClient();
  const productos = useProductos(source, folder);
  const esTopVendidos = source === FUENTE_TOP_VENDIDOS;
  // Se recuerda: si lo pones para ver lo que te queda por probar, la próxima
  // vez que entres quieres lo mismo.
  const [soloSinSubir, setSoloSinSubir] = useEstadoRecordado(
    "povbof:topventas:sinsubir", false,
  );
  // Un solo botón para "tráete lo de verdad": carpetas, productos y las ventas
  // del ranking (que se cruzan al listar, no se guardan en el producto).
  const [refrescando, setRefrescando] = useState(false);
  async function actualizarTodo() {
    setRefrescando(true);
    try {
      // Primero se le dice al servidor que relea el Drive (tiene su propia
      // caché de listados); invalidar solo la del navegador devolvía lo mismo.
      await refrescarDesdeDrive(source, folder).catch(() => {});
      await qc.invalidateQueries({ queryKey: nichoPovBofKeys.all });
    } finally {
      setRefrescando(false);
    }
  }

  // Ver el ranking entero, no solo la carpeta abierta. Se recuerda igual que
  // el filtro de arriba: quien lo enciende lo quiere siempre.
  // Encendido por DEFECTO: en esta fuente lo que se quiere ver es el ranking,
  // igual que en "Productos que vendieron". Quitarlo devuelve la vista carpeta
  // a carpeta. La clave lleva `ranking` y no `todas` porque la primera versión
  // salió apagada y quedó guardada así en los navegadores que la vieron: con
  // la misma clave, el defecto nuevo no habría llegado a nadie.
  const [verTodas, setVerTodas] = useEstadoRecordado("povbof:topventas:ranking", true);
  const todos = useProductosTodos(source, esTopVendidos && verTodas);
  const listaProductos = useMemo(
    () => (esTopVendidos && verTodas ? todos.data ?? [] : productos.data ?? []),
    [esTopVendidos, productos.data, todos.data, verTodas],
  );

  // El ranking completo son 40 productos y de un tirón no se repasa: se ve de
  // diez en diez. La página NO es un estado aparte: es la CARPETA abierta, así
  // que "Top 2" enseña del 11 al 20 del ranking. Tenerlos separados hacía que
  // cambiar de carpeta dejara delante los mismos diez primeros.
  const POR_PAGINA = 10;

  const productosVisibles = useMemo(
    () =>
      verTopVendidos(listaProductos, {
        activo: esTopVendidos,
        soloSinSubir,
        yaSubido: (p) => p.uploaded,
      }),
    [listaProductos, esTopVendidos, soloSinSubir],
  );
  const paginado = esTopVendidos && verTodas;
  const paginas = paginado ? Math.max(1, Math.ceil(productosVisibles.length / POR_PAGINA)) : 1;
  const carpetas = data?.items ?? [];
  const iCarpeta = Math.max(0, carpetas.findIndex((f) => f.name === folder));
  const pagina = paginado ? Math.min(iCarpeta, paginas - 1) : 0;
  /** Pasar de página = abrir la carpeta correspondiente. */
  const irAPagina = (n: number) => {
    const destino = carpetas[Math.max(0, Math.min(paginas - 1, n))];
    if (destino) setPicked(destino.name);
  };
  // Lo que se ve AHORA: es lo que se baja y lo que cuentan los botones.
  const enPantalla = useMemo(
    () =>
      paginado
        ? productosVisibles.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA)
        : productosVisibles,
    [paginado, productosVisibles, pagina],
  );
  const extraerTextos = useExtraerTextos();
  // Los textos son del producto y se comparten: los extrae solo el admin.
  const esPro = useEsPro();
  const buscarUrls = useBuscarUrlsCarpeta();
  // SIN fuente: el ranking es global y el listado que se abre también, así
  // que el número del botón tiene que contar lo mismo. Con `source` decía 2
  // (solo la fuente abierta) y al abrirlo salían 43.
  const vendidos = useVendidos("");
  // El botón dice "productos", así que enseña PRODUCTOS. Antes sumaba las
  // unidades y salía un número mayor (48 con 30 productos), que no cuadraba
  // con las carpetas de Top vendidos y parecía que faltaban por copiar.
  const totalVendidos = (vendidos.data ?? []).length;
  const unidadesVendidas = (vendidos.data ?? []).reduce(
    (n, v) => n + (v.unidades || 1), 0,
  );
  const [downloadingPhotos, setDownloadingPhotos] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState("");
  const [downloadingVideos, setDownloadingVideos] = useState(false);
  const [videoProgress, setVideoProgress] = useState("");
  // Los recuentos van sobre lo que se ESTÁ VIENDO: con el ranking completo
  // abierto, "Fotos 10/10" mientras hay cuarenta productos en pantalla no
  // decía nada de lo que se iba a bajar.
  const totalProductos = enPantalla.length;
  const conVideo = enPantalla.filter((p) => p.video_path).length;
  const conFoto = enPantalla.filter((p) => p.clean_photo_id).length;
  // Los dos flujos de generación de la carpeta, contados sobre los que tienen
  // foto (que son los que se pueden bajar).
  const conPlazos = enPantalla.filter(
    (p) => p.clean_photo_id && p.modo_plazos,
  ).length;
  const conViejo = enPantalla.filter(
    (p) => p.clean_photo_id && !p.modo_plazos,
  ).length;
  // Lo mismo para los vídeos ya montados: bajar 20 para quedarse con 3 es lo
  // que se quería evitar.
  const videosPlazos = enPantalla.filter(
    (p) => p.video_path && p.modo_plazos,
  ).length;
  const videosViejo = enPantalla.filter(
    (p) => p.video_path && !p.modo_plazos,
  ).length;
  // "Textos" es una acción de CARPETA (extrae la carpeta abierta), así que su
  // contador va sobre la carpeta y no sobre lo que se ve.
  const totalCarpeta = productos.data?.length ?? 0;
  const conTexto = (productos.data ?? []).filter((p) => p.titulo).length;
  const subidos = enPantalla.filter((p) => p.uploaded).length;
  const enEscaparate = enPantalla.filter((p) => p.en_escaparate).length;
  // Meter el producto en el escaparate es el paso más lento del día y no se
  // puede automatizar (ver EscaparateModal), así que el pendiente se enseña
  // arriba, en el botón, sin tener que abrir nada.
  const pendientesEscaparate = enPantalla.filter(
    (p) => !p.en_escaparate,
  ).length;

  function copyText(label: string, text: string | undefined) {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado`);
  }

  /** Descarga los vídeos ya montados de la carpeta, uno a uno.
   *
   *  Igual que las fotos: el navegador móvil cancela las descargas
   *  simultáneas, así que van en fila con un retardo entre medias. */
  async function downloadVideos(filtro: Filtro = "todas") {
    if (!folder || !enPantalla.length) return;
    // En el orden que se ve (ver `downloadCleanPhotos`).
    const items = enPantalla.filter((p) => p.video_path && cuadra(p, filtro));
    if (!items.length) {
      toast.error(
        filtro === "todas"
          ? "Ningún producto tiene vídeo montado todavía"
          : `Ningún vídeo ${filtro === "plazos" ? "de plazos" : "de guion normal"} montado`,
      );
      return;
    }
    setDownloadingVideos(true);
    try {
      for (const [i, p] of items.entries()) {
        setVideoProgress(`${i + 1}/${items.length}`);
        const a = document.createElement("a");
        const suya = p.folder || folder;
        a.href = buildVideoUrl(source, suya, p.producto, p.video_listo_at ?? 0, true);
        const sufijo = filtro === "todas" ? "" : `_${filtro}`;
        const orden = String(i + 1).padStart(2, "0");
        a.download = `${orden}_${suya}_${p.producto}${sufijo}.mp4`.replace(
          /[^a-zA-Z0-9_.-]+/g, "_",
        );
        document.body.appendChild(a);
        a.click();
        a.remove();
        if (i < items.length - 1) await new Promise((r) => setTimeout(r, 900));
      }
      toast.success(`${items.length} vídeo(s) descargados`);
    } finally {
      setDownloadingVideos(false);
      setVideoProgress("");
    }
  }

  /** `filtro` separa los dos flujos, que no se generan igual: los de plazos
   *  necesitan DOS clips y los de siempre uno solo, así que bajar la carpeta
   *  entera obligaba a ir mirando el precio producto a producto. */
  async function downloadCleanPhotos(filtro: Filtro = "todas") {
    if (!folder || !enPantalla.length) return;
    // En el ORDEN QUE SE VE, no en el de la carpeta: en Top vendidos la lista
    // va por ventas y las fotos se bajaban por número de producto, así que en
    // la galería aparecían en otro orden del que se acababa de mirar.
    const items = enPantalla.filter((p) => p.clean_photo_id && cuadra(p, filtro));
    if (!items.length) {
      toast.error(
        filtro === "todas"
          ? "No hay fotos limpias en esta carpeta"
          : `No hay productos ${filtro === "plazos" ? "de plazos" : "con guion viejo"} con foto`,
      );
      return;
    }
    setDownloadingPhotos(true);
    try {
      // El navegador móvil no deja elegir carpeta de descarga: van a
      // Descargas con el nombre prefijado por la carpeta para que queden
      // juntas. Se disparan una a una con un pequeño retardo — varias
      // descargas simultáneas suelen bloquearse o cancelarse.
      for (const [i, p] of items.entries()) {
        setDownloadProgress(`${i + 1}/${items.length}`);
        const a = document.createElement("a");
        // Cada producto es de SU carpeta cuando se ven todas juntas.
        const suya = p.folder || folder;
        a.href = buildCleanPhotoDownloadUrl(source, suya, p.producto);
        // El sufijo evita mezclar los dos flujos en la carpeta de Descargas, y
        // el número de delante es lo que hace que la galería los enseñe en el
        // mismo orden que la pantalla.
        const sufijo = filtro === "todas" ? "" : `_${filtro}`;
        const orden = String(i + 1).padStart(2, "0");
        a.download = `${orden}_${suya}_${p.producto}${sufijo}`.replace(
          /[^a-zA-Z0-9_.-]+/g, "_",
        );
        document.body.appendChild(a);
        a.click();
        a.remove();
        if (i < items.length - 1) await new Promise((r) => setTimeout(r, 600));
      }
      toast.success(`${items.length} foto(s) descargadas`);
    } finally {
      setDownloadingPhotos(false);
      setDownloadProgress("");
    }
  }

  function runExtraerTextos() {
    if (!folder) return;
    extraerTextos.mutate(
      { source, folder },
      {
        onSuccess: () => toast.success("Textos extraídos"),
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  // Cuántos productos costaría el botón de buscar enlaces: los que ya tienen
  // ficha o aún no tienen título no gastan llamada. Se enseña el número
  // porque la cuota de EchoTik es un trial de 100 y se acaba.
  const pendientesUrl = (productos.data ?? []).filter(
    (p) => !p.product_url && p.titulo_tiktok_completo,
  ).length;

  function runBuscarUrls() {
    if (!folder) return;
    buscarUrls.mutate(
      { source, folder },
      {
        onSuccess: (res) => {
          if (!res.llamadas) {
            toast.success("Todos los productos ya tenían enlace");
          } else {
            toast.success(
              `${res.encontrados}/${res.llamadas} enlaces encontrados` +
                (res.sin_resultado ? ` · ${res.sin_resultado} sin resultado` : ""),
            );
          }
          if (res.aviso) toast.error(res.aviso);
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
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
      { source, folder, completed },
      {
        onSuccess: (res) => {
          if (completed) {
            toast.success(`"${folder}" completada`);
            // Avanzar a la siguiente sin hacer: es el flujo que pidió el user.
            setPicked(res.next_folder);
          } else {
            toast.success(`"${folder}" reabierta`);
          }
        },
        onError: (e) => {
          const msg = e instanceof ApiError ? e.message : String(e);
          toast.error(`No se pudo guardar: ${msg}`);
        },
      },
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      {/* Cabecera de texto, como en el Largo y en Creativos Pro: la portada
          del curso ocupaba media pantalla en el móvil y decía menos que dos
          líneas. Lo primero que hay que ver es dónde trabajas. */}
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <ShoppingBag className="h-5 w-5 shrink-0 text-emerald-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Nicho POV BOF</h1>
            <p className="text-[11px] text-muted-foreground">
              Un vídeo por producto: la mano enseña el producto y la voz sale
              del banco de audios · UN clip de 10s
            </p>
          </div>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Los productos salen del Drive del curso (solo lectura) y lo que
          marques aquí —textos, escaparate, subido— es de este nicho. Los que
          pasan de 40 € llevan guion de plazos y van con dos clips.
        </p>
      </header>

      {/* Dónde trabajas: de qué catálogo salen los productos y en qué carpeta
          estás. En una caja con rótulos porque antes eran bloques sueltos sin
          título y había que deducir qué era cada uno por sus botones. */}
      <Caja
        icono="📁"
        titulo="Dónde trabajas"
        hint="Elige el catálogo y la carpeta. El progreso es de este nicho."
        extra={`${done}/${total} hechas`}
      >
        <Sub>Catálogo</Sub>
        {/* Dos por línea en móvil desde que son cuatro: en una sola fila los
            nombres quedaban recortados a tres letras. */}
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => switchSource(s.slug)}
              className={`truncate rounded-lg border px-2 py-2 text-[11px] transition sm:text-xs ${
                source === s.slug
                  ? "border-emerald-500 bg-emerald-500/10 font-semibold text-emerald-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {s.label}
              {/* Vendidos que aún no están copiados en la carpeta. Sin esto no
                  hay forma de enterarse sin entrar a mirar. */}
              {s.pendientes > 0 && (
                <span className="ml-1 rounded bg-amber-500/20 px-1 py-0.5 text-[9px] font-bold text-amber-500">
                  +{s.pendientes}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Solo en la fuente propia: en las del curso no hay nada que subir. */}
        {source === "mis_productos" && (
          /* Al crear se salta a la carpeta donde ha caído: las carpetas se
             llenan de diez en diez, así que el producto nuevo puede ir a la
             SIGUIENTE y quedarse invisible mientras miras la anterior. */
          <AltaMiProducto
            onCreado={(carpeta) => {
              setPicked(carpeta);
              void qc.refetchQueries({
                queryKey: nichoPovBofKeys.productos(source, carpeta),
              });
              void qc.refetchQueries({ queryKey: nichoPovBofKeys.folders(source) });
            }}
          />
        )}
        {source === "top_vendidos" && <SincronizarTopVendidos folder={folder} />}

        <Sub>Carpetas</Sub>
        <div className="flex items-center justify-between text-xs sm:text-sm">
          <span className="font-medium">
            {done} / {total} completadas
          </span>
          <div className="flex items-center gap-2">
            {/* Recargaba SOLO las carpetas: pulsarlo no cambiaba ni los
                productos ni las ventas del ranking, que es justo para lo que
                se pulsa. Ahora refresca todo el nicho. */}
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
            className="h-full rounded-full bg-emerald-500 transition-all"
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

      {/* Lo que ya vendió dice qué buscar, y el índice es GLOBAL (el mismo para
          todos los nichos): por eso va fuera de la caja de la carpeta y a un
          toque, no enterrado al final de la página. */}
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
        <EscaparateModal
          source={source}
          folder={folder}
          productos={productos.data ?? []}
          onClose={() => setVerEscaparate(false)}
        />
      )}

      {/* La configuración (hashtags, copia de seguridad) vive en su propia
          pantalla del menú: aquí solo estorbaba, y es la misma para todos los
          nichos. */}

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


      {/* Carpeta actual */}
      {data && !folder && (
        <p className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 text-center text-sm text-emerald-500">
          🎉 Todas las carpetas de esta fuente están completadas.
        </p>
      )}

      {/* La carpeta abierta: se navega, se ven sus fotos en crudo y se marca
          hecha. Caja propia para que no se confunda con los pasos del trabajo,
          que vienen justo debajo. */}
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
              {/* El nombre y el "N de M" ya están en la cabecera de la caja. */}
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

          {/* Las 20 fotos en crudo ocupaban toda la pantalla y estorbaban:
              el trabajo real se hace en las tarjetas de producto de abajo.
              Se dejan a un clic por si hace falta revisarlas. */}
          {photos.data && (
            <button
              type="button"
              onClick={() => setShowFotos((v) => !v)}
              className="flex w-full items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-[11px] text-muted-foreground transition hover:text-foreground sm:text-xs"
            >
              <span>
                {photos.data.items.length} foto(s) en crudo de la carpeta
              </span>
              <span>{showFotos ? "ocultar ▲" : "ver ▼"}</span>
            </button>
          )}

          {photos.data && showFotos && (
            <>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
                {photos.data.items.map((p) => (
                  <a
                    key={p.id}
                    // La cuadrícula pinta miniaturas, pero el enlace abre la
                    // foto DE VERDAD: es una sola, en su propia pestaña, y el
                    // que la abre quiere verla tal cual está en Drive.
                    href={buildPhotoUrl(source, folder, p.id, null)}
                    target="_blank"
                    rel="noreferrer"
                    className="group relative aspect-square overflow-hidden rounded-lg border border-border/60 bg-muted"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={buildPhotoUrl(source, folder, p.id)}
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
            </>
          )}

          <button
            type="button"
            onClick={() => toggleCompleted(!currentItem?.completed)}
            disabled={markCompleted.isPending}
            className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition disabled:opacity-50 ${
              currentItem?.completed
                ? "border border-border/60 text-muted-foreground hover:text-foreground"
                : "bg-emerald-500 text-white hover:bg-emerald-600"
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


      {/* El trabajo del día, en el ORDEN en que se hace. Cada paso es una caja
          con su número y su color, iguales en los tres nichos: entra gente
          nueva a usar esto y el orden tiene que leerse sin que nadie lo
          explique. Antes era una lista de botones donde "copiar el prompt" y
          "subir todos los vídeos" parecían lo mismo. */}
      {data && folder && (
        <section className="space-y-2">
          <div className="flex items-center gap-2 px-1">
            <Sparkles className="h-4 w-4 shrink-0 text-purple-500" />
            <p className="text-sm font-semibold">Cómo se hace un vídeo</p>
            <span className="ml-auto text-[10px] text-muted-foreground">
              {folder}
            </span>
          </div>

          <Paso
            n={1}
            color="violeta"
            titulo="Preparar los textos"
            hint={esTopVendidos ? "Aquí los textos se copian del producto original: no se vuelven a leer con IA, que es lo que descuadraba la carpeta." : "Lee la ficha de cada producto con IA (título, tienda, caption, precio). Se hace una vez por carpeta."}
            extra={`${conTexto}/${totalCarpeta}`}
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
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                    Extrayendo textos…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 shrink-0" />
                    {conTexto >= totalCarpeta && totalCarpeta > 0
                      ? "Textos al día · volver a extraer"
                      : `Obtener textos (${conTexto}/${totalCarpeta})`}
                  </>
                )}
              </button>
            )}

            {/* Estado de la carpeta, para comparar de un vistazo lo que está
                en el escaparate con lo que ya se publicó. */}
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
                  <>
                    <LinkIcon className="h-3.5 w-3.5 shrink-0" />
                    {pendientesUrl ? `Enlaces (${pendientesUrl} llamadas)` : "Enlaces al día"}
                  </>
                )}
              </button>
            )}
          </Paso>

          <Paso
            n={2}
            color="fucsia"
            titulo="Generar los vídeos fuera"
            hint="Baja las fotos, crea los vídeos en Magnific (o con el prompt en otra herramienta) y vuelve aquí."
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
            {/* Magnific O los prompts: dos caminos para lo mismo. El space de
                "foto con IA" solo lo usa el admin. */}
            <MagnificSpaces
              spaces={[
                "foto_limpia_normal",
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

          {/* Traer los vídeos generados. Es la acción MÁS importante del día y
              antes se perdía entre los botones de copiar prompts. */}
          {folder && productos.data && productos.data.length > 0 && (
            <Paso
              n={3}
              color="esmeralda"
              titulo="Traer los vídeos generados"
              hint="Suéltalos todos de golpe: la IA los reparte a su producto y tú solo repasas."
            >
              <SubidaMasiva
                source={source}
                folder={folder}
                productos={productos.data}
                sinMarco
              />
            </Paso>
          )}

          <Paso
            n={4}
            color="azul"
            titulo="Descargar lo ya montado"
            hint="Los vídeos editados, listos para subir a TikTok. Se bajan en el orden que ves en pantalla."
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

          {/* Solo en Top vendidos: ahí el orden importa (los que más venden
              primero) y lo que se busca es lo que aún no has probado. */}
          {esTopVendidos && productos.data && productos.data.length > 0 && (
            <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
              <input
                type="checkbox"
                className="h-4 w-4 accent-emerald-500"
                checked={soloSinSubir}
                onChange={(e) => setSoloSinSubir(e.target.checked)}
              />
              Solo los que no he subido
              <span className="ml-auto text-[10px] text-muted-foreground">
                {productosVisibles.length}/{listaProductos.length}
              </span>
            </label>
          )}

          {/* El ranking de verdad: los productos entran en carpetas de diez y
              ahí se quedan de por vida (moverlos perdería el progreso), así
              que ordenar dentro de una carpeta NO da el ranking. Con esto se
              juntan todas y se ordenan por ventas. */}
          {esTopVendidos && (
            <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
              <input
                type="checkbox"
                className="h-4 w-4 accent-emerald-500"
                checked={verTodas}
                onChange={(e) => setVerTodas(e.target.checked)}
              />
              Todas las carpetas juntas, por ventas
              {todos.isFetching && <Loader2 className="h-3 w-3 animate-spin" />}
            </label>
          )}

          {/* El ranking se recorre de diez en diez, como las carpetas, pero sin
              romper el orden por ventas: la página 2 son los diez siguientes
              del ranking, no la carpeta 2. */}
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
                {Math.min((pagina + 1) * POR_PAGINA, productosVisibles.length)} de{" "}
                {productosVisibles.length} por ventas
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
                  source={source}
                  // En la vista global cada tarjeta es de SU carpeta.
                  folder={p.folder || folder}
                  producto={p}
                  carpetaHecha={Boolean(listaProductos.some((x) => x.titulo))}
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

/** Ranking de lo que ya ha vendido, en pantalla flotante.
 *
 *  Es el dato más valioso de todo el flujo — dice qué tipo de producto buscar —
 *  y estaba enterrado al final de la página, tardando ocho segundos y sin
 *  fotos. Ahora sale de su propio índice en Redis (dos llamadas) y se abre
 *  desde arriba con un toque.
 *
 *  Lo importante es poder sumar unidades: un producto que REPITE venta vale
 *  mucho más que uno que vendió una vez, y no había forma de anotarlo. */
/** Alta de productos PROPIOS. Solo sale en la fuente "Mis productos".
 *
 *  Las otras dos fuentes son carpetas del Drive del curso, de solo lectura;
 *  esta es la del operador. Sube la foto limpia y la captura de la ficha y el
 *  backend las guarda con el MISMO convenio de nombres del curso, así que a
 *  partir de ahí el producto se comporta igual que cualquier otro: textos,
 *  caption, gancho, CTA, escaparate, vendidos y montaje del vídeo.
 */
/** Trae al "Top vendidos" los productos del ranking que aún no estén.
 *
 *  Va aquí, junto al selector de fuente, porque es lo primero que se hace al
 *  entrar: si acabas de marcar una venta, esto la baja a su carpeta. */
function AltaMiProducto({ onCreado }: { onCreado?: (carpeta: string) => void }) {
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
          onCreado?.(r.carpeta);
          setLimpia(null);
          setFicha(null);
          if (refLimpia.current) refLimpia.current.value = "";
          if (refFicha.current) refFicha.current.value = "";
        },
        onError: (e) =>
          toast.error(e instanceof ApiError ? e.message : String(e)),
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
    <label className="flex cursor-pointer flex-col gap-1 rounded-lg border border-dashed border-border/60 p-2.5 transition hover:border-emerald-500/60">
      <span className="text-[11px] font-semibold">{titulo}</span>
      <span className="text-[10px] text-muted-foreground">{ayuda}</span>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        onChange={(e) => set(e.target.files?.[0] ?? null)}
        className="mt-1 block w-full text-[10px] text-muted-foreground file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-[10px]"
      />
      {archivo && (
        <span className="truncate text-[10px] text-emerald-500">
          ✓ {archivo.name}
        </span>
      )}
    </label>
  );

  return (
    <section className="space-y-2 rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-3">
      {/* Plegado por defecto: dar de alta un producto es cosa de una vez al
          día, y desplegado empujaba la lista de carpetas media pantalla abajo
          cada vez que se abría el nicho. */}
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
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
      >
        {crear.isPending ? "Subiendo…" : "Añadir producto"}
      </button>
      <p className="text-[10px] leading-relaxed text-muted-foreground">
        Las carpetas se llenan de 10 en 10: al llegar al 11 se abre la siguiente
        sola. Después se usa igual que un producto del curso — textos, caption,
        voz y vídeo.
      </p>
      </>
      )}
    </section>
  );
}




/** Botón compacto: copia el texto al portapapeles sin mostrarlo. Mismo
 *  patrón que `CopyChip` de `calendar/page.tsx:1044`. */

type ToolKey = "gancho" | "titulo" | "cta" | "flecha";

/** Herramientas de edición que se pueden pedir por separado. */
const TOOLS: { key: ToolKey; label: string }[] = [
  { key: "gancho", label: "🎣 Gancho" },
  { key: "titulo", label: "📝 Texto producto" },
  { key: "cta", label: "👉 CTA" },
  { key: "flecha", label: "⬇️ Flecha" },
];

/** Tarjeta de producto: textos, sexo, subida de vídeo y toggles
 *  Subido/Vendió. Estado local + servidor para que los toggles se sientan
 *  instantáneos (mismo patrón que `OutcomeBar` del calendario). */
function ProductoCard({
  source,
  folder,
  producto,
  carpetaHecha = false,
  esTopVendidos = false,
}: {
  source: string;
  folder: string;
  producto: ProductoItem;
  /** En "Top vendidos" se enseña cuántas veces vendió y si es reciente. */
  esTopVendidos?: boolean;
  /** La carpeta ya tiene textos en OTROS productos. Sirve para marcar al que
   *  se quedó sin ellos: es un producto que apareció tarde (antes se perdían
   *  los de fotos sin extensión y los fundidos bajo un mismo número), y sin
   *  marca pasa desapercibido entre nueve que están completos. */
  carpetaHecha?: boolean;
}) {
  const setEstado = useSetEstado();
  const quitarClip = useQuitarClip();
  const buscarUrl = useBuscarProductoUrl();
  // La búsqueda puede terminar bien y aun así no traer URL (EchoTik no
  // indexa el producto). Sin distinguirlo, el botón se quedaba igual que
  // antes de pulsarlo y el operador volvía a gastar cuota sin saberlo.
  const urlNoEncontrada = buscarUrl.isSuccess && !producto.product_url;
  const [uploaded, setUploaded] = useState(producto.uploaded);
  const [sold, setSold] = useState(producto.sold);
  const [enEscaparate, setEnEscaparate] = useState(producto.en_escaparate);
  // Arranca en automático: el montaje mira la mano del vídeo y elige la voz
  // (mujer salvo que vea reloj o vello, que es la regla del operador). Se
  // puede forzar a mano si el vídeo es de los dudosos.
  const [sexo, setSexo] = useState<"hombre" | "mujer" | "auto">("auto");
  // Herramientas de edición, elegibles por separado. Todas marcadas por
  // defecto = el montaje completo; desmarcarlas todas deja el vídeo limpio
  // (solo la voz). Así se puede pedir, p. ej., solo el nombre del producto
  // o solo la flecha.
  const [tools, setTools] = useState<Record<ToolKey, boolean>>({
    gancho: true, titulo: true, cta: true, flecha: true,
  });
  const [uploading, setUploading] = useState(false);
  const [pct, setPct] = useState(0);
  // Progreso POR CLIP en los productos de plazos (null = ese no se está
  // subiendo). Cada slot va por su cuenta: se puede subir el clip 2 mientras
  // el 1 va por la mitad, y una ficha no bloquea a las demás.
  const [pctsClip, setPctsClip] = useState<{ 1: number | null; 2: number | null }>({
    1: null, 2: null,
  });
  const clipRefs = { 1: useRef<HTMLInputElement>(null), 2: useRef<HTMLInputElement>(null) };
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);
  const [verTools, setVerTools] = useState(false);
  const [verGuion, setVerGuion] = useState(false);
  const sortear = useSortearGuionPlazos();
  const borrar = useBorrarMiProducto();
  const qc = useQueryClient();
  const hashtags = useHashtags().data ?? [];
  const fileInputRef = useRef<HTMLInputElement>(null);

  // El producto puede llegar actualizado desde otra mutación (p. ej. tras
  // "Obtener textos" refresca la lista entera) — resincroniza el estado local.
  useEffect(() => {
    setUploaded(producto.uploaded);
    setSold(producto.sold);
    setEnEscaparate(producto.en_escaparate);
  }, [producto.uploaded, producto.sold, producto.en_escaparate]);

  const pushEstado = (patch: {
    uploaded?: boolean;
    sold?: boolean;
    en_escaparate?: boolean;
  }) => {
    setEstado.mutate(
      { source, folder, producto: producto.producto, ...patch },
      {
        onError: (e) => {
          // DESHACER lo que se pintó al pulsar. Sin esto el botón se quedaba
          // marcado y se desmarcaba solo un rato después (cuando llegaba el
          // listado del servidor), que es lo que se ve como "no me deja
          // marcar" sin saber por qué.
          if (patch.en_escaparate !== undefined) setEnEscaparate(!patch.en_escaparate);
          if (patch.uploaded !== undefined) setUploaded(!patch.uploaded);
          if (patch.sold !== undefined) setSold(!patch.sold);
          toast.error(e instanceof ApiError ? e.message : String(e));
        },
      },
    );
  };

  const toggleEscaparate = () => {
    const v = !enEscaparate;
    setEnEscaparate(v);
    pushEstado({ en_escaparate: v });
  };

  const toggleUploaded = () => {
    const v = !uploaded;
    setUploaded(v);
    pushEstado({ uploaded: v });
  };

  // Ya no se pregunta con qué nicho vendió: el ranking de vendidos es ÚNICO y
  // global (el mismo producto se graba con varios nichos y la cuenta de TikTok
  // es la misma), así que clasificarlo no aportaba nada y costaba un toque de
  // más en la acción que más se repite.
  const toggleSold = () => {
    const v = !sold;
    setSold(v);
    // Vender implica haberlo subido — evita el estado imposible "vendió pero
    // no subido".
    if (v && !uploaded) setUploaded(true);
    pushEstado(v && !uploaded ? { sold: true, uploaded: true } : { sold: v });
  };

  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";

  function uploadVideo(file: File, slot: 0 | 1 | 2 = 0) {
    if (slot) setPctsClip((prev) => ({ ...prev, [slot]: 0 }));
    else {
      setUploading(true);
      setPct(0);
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("source", source);
    fd.append("folder", folder);
    fd.append("producto", producto.producto);
    fd.append("sexo", sexo);
    fd.append("con_gancho", String(tools.gancho));
    fd.append("con_titulo", String(tools.titulo));
    fd.append("con_cta", String(tools.cta));
    fd.append("con_flecha", String(tools.flecha));
    if (slot) fd.append("slot", String(slot));
    // XHR (no fetch) para tener progreso real de subida — mismo patrón que
    // `uploadVideo()` en calendar/page.tsx:634.
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBase}/api/v1/nicho-pov-bof/video/upload`);
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const v = Math.round((e.loaded / e.total) * 100);
      if (slot) setPctsClip((prev) => ({ ...prev, [slot]: v }));
      else setPct(v);
    };
    const acabar = () => {
      if (slot) setPctsClip((prev) => ({ ...prev, [slot]: null }));
      else setUploading(false);
    };
    xhr.onload = () => {
      acabar();
      try {
        const resData = JSON.parse(xhr.responseText) as VideoUploadResponse;
        if (resData.ok) {
          toast.success(resData.message || "En la cola, editando…");
          // Sin esto la lista no se entera de que hay un montaje en marcha y
          // el sondeo nunca arranca: había que recargar a mano para ver el
          // botón de Ver/Descargar.
          void qc.invalidateQueries({
            queryKey: nichoPovBofKeys.productos(source, folder),
          });
        } else toast.error(resData.message || "Error subiendo el vídeo");
      } catch {
        toast.error("Respuesta inválida del servidor");
      }
    };
    xhr.onerror = () => {
      acabar();
      toast.error("Error de red al subir");
    };
    xhr.send(fd);
  }

  return (
    /* El borde lleva el color del nicho (verde) y cambia con el estado: gris
       mientras no hay nada, verde en cuanto el vídeo está montado. Con todas
       las tarjetas iguales había que leerlas una a una para saber por dónde
       ibas. */
    <div
      className={`space-y-2 rounded-xl border bg-card p-3 transition ${
        producto.video_path
          ? "border-emerald-500/50"
          : "border-border/60 hover:border-emerald-500/30"
      }`}
    >
      <div className="flex gap-2">
        {producto.clean_photo_id ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            title="Ver la foto en grande"
            className="shrink-0"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={buildPhotoUrl(source, folder, producto.clean_photo_id, ANCHO_CHIP)}
              alt={producto.producto}
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
          {/* El número del producto va SIEMPRE delante: es como se llama la
              carpeta y la foto, y al extraer los textos el título lo tapaba,
              así que no se sabía con qué producto se estaba trabajando. */}
          <p className="flex items-baseline gap-1.5 text-xs font-semibold sm:text-sm">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {producto.producto}
            </span>
            <span className="truncate">{producto.titulo || "sin título"}</span>
          </p>
          {/* Se quedó sin textos en una carpeta donde los demás sí los tienen:
              apareció tarde (antes se perdían los productos con fotos sin
              extensión y los fundidos bajo un mismo número). Sin la marca
              pasa desapercibido entre nueve completos. */}
          {carpetaHecha && !producto.titulo && (
            <p className="mt-0.5 inline-flex items-center gap-1 rounded bg-fuchsia-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-fuchsia-500">
              🆕 Recuperado — vuelve a pulsar “Textos”
            </p>
          )}
          {producto.titulo_tiktok_completo && (
            <p className="truncate text-[10px] text-muted-foreground">
              {producto.titulo_tiktok_completo}
            </p>
          )}
          {/* El precio decide el guion (por encima del umbral son dos clips y
              el guion de plazos), así que se ve pegado al producto. Cuando la
              carpeta tiene textos pero no se pudo leer el precio se dice: en
              silencio parecería barato y se iría al guion de siempre. */}
          {esTopVendidos && producto.ventas > 0 && (
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px]">
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-semibold text-emerald-500">
                🔥 {producto.ventas} {producto.ventas === 1 ? "venta" : "ventas"}
              </span>
              {/* "Nuevo" = entró en el ranking esta semana. Es lo que buscas al
                  abrir la pantalla: qué ha empezado a vender. */}
              {esVentaNueva(producto.vendido_at) && (
                <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-semibold text-amber-500">
                  nuevo
                </span>
              )}
            </p>
          )}
          {producto.titulo && (
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px]">
              {producto.precio > 0 ? (
                <>
                  {/* El tachado explica por qué un producto de 34,70 no lleva
                      plazos: con cupones se paga 29,50 y Klarna pide 30. */}
                  {producto.precio_lista > producto.precio && (
                    <span className="font-mono text-muted-foreground line-through">
                      {producto.precio_lista.toFixed(2).replace(".", ",")} €
                    </span>
                  )}
                  <span className="font-mono font-semibold">
                    {producto.precio.toFixed(2).replace(".", ",")} €
                  </span>
                </>
              ) : (
                /* Sin precio el producto NUNCA pasa a plazos, así que una
                   silla de 150 € se montaría con el guion de una de 15. Pasa
                   cuando falta la captura de la ficha o no se deja leer: se
                   escribe a mano y ya decide bien. */
                <PrecioAMano
                  source={source}
                  folder={folder}
                  producto={producto.producto}
                />
              )}
              {producto.desde_copia && (
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
              {producto.modo_plazos && (
                <span className="rounded bg-violet-500/15 px-1.5 py-0.5 font-semibold text-violet-500">
                  💳 Plazos · 2 clips
                </span>
              )}
              {/* Cuándo entró en el Drive del curso. Las carpetas no son
                  cerradas: van añadiendo productos durante el día, y sin la
                  fecha no hay forma de saber cuáles son nuevos. */}
              {producto.subida_at && (
                <span
                  title="Cuándo se subió al Drive del curso"
                  className="text-muted-foreground"
                >
                  📅 {fechaCorta(producto.subida_at)}
                </span>
              )}
            </p>
          )}
        </div>
      </div>

      {/* Copiar textos extraídos — solo se muestran los que tengan valor */}
      <div className="flex flex-wrap gap-1">
        {/* El "Título" a secas no se copiaba nunca (el que se pega en TikTok
            es el completo), así que solo hacía ruido en la ficha. */}
        <CopyChip label="🔎 Título TikTok" text={producto.titulo_tiktok_completo ?? ""} />
        <CopyChip label="🏪 Tienda" text={producto.tienda ?? ""} siempre />
        {/* El caption se copia YA con los hashtags pegados: es lo que se
            pega tal cual en TikTok, no hay que juntarlo a mano. */}
        <CopyChip
          label="✍️ Caption"
          text={
            producto.caption
              ? [producto.caption, producto.emojis, hashtags.join(" ")]
                  .filter(Boolean)
                  .join(" ")
              : ""
          }
        />
        {/* Gancho y CTA ya no se copian: los quema el propio montaje, y a
            mano solo se usaban cuando el vídeo se hacía en CapCut. */}
        <BotonUrl url={producto.product_url} />
        {producto.clean_photo_id && (
          <>
            {/* Sin botón "Ver foto": la miniatura de arriba ya abre el visor
                y el botón repetía la misma acción en cada ficha. */}
            <a
              href={buildCleanPhotoDownloadUrl(source, folder, producto.producto)}
              className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40 hover:text-foreground"
            >
              <Download className="h-3 w-3" /> Foto
            </a>
          </>
        )}
      </div>

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={`Producto ${producto.producto}`}
        urlLimpia={
          producto.clean_photo_id
            ? buildPhotoUrl(source, folder, producto.clean_photo_id, ANCHO_VISOR)
            : null
        }
        urlTitulo={
          producto.titled_photo_id
            ? buildPhotoUrl(source, folder, producto.titled_photo_id, ANCHO_VISOR)
            : null
        }
        urlDescarga={
          producto.clean_photo_id
            ? buildCleanPhotoDownloadUrl(source, folder, producto.producto)
            : null
        }
      />

      {/* Cuando no se puede distinguir la foto del producto de la captura de
          la descripción, se avisa: llegó a colarse una captura de texto como
          si fuera la foto del producto. */}
      {producto.foto_aviso && (
        <p className="text-[11px] text-amber-400 break-words">
          🖼️ {producto.foto_aviso}
        </p>
      )}

      {/* El caption no se quema en el vídeo, lo pega el operador al publicar,
          así que no se puede corregir solo: se avisa para revisarlo a mano. */}
      {producto.caption_riesgo && (
        <p className="text-[11px] text-amber-400 break-words">
          ⚠️ El caption dice «{producto.caption_riesgo}» — promete un resultado
          que la ficha no respalda. Revísalo antes de publicar.
        </p>
      )}


      {/* Ficha de TikTok Shop. Cada búsqueda gasta una llamada del plan de
          EchoTik (trial de 100), por eso es un botón manual por producto y
          no algo que se dispare solo al abrir la carpeta. */}
      {/* Ficha de TikTok Shop: escondida mientras EchoTik esté apagado. */}
      {MOSTRAR_ECHOTIK && (producto.product_url ? (
        <a
          href={producto.product_url}
          target="_blank"
          rel="noreferrer"
          className="block truncate rounded-md border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-[11px] text-emerald-500"
          title={producto.url_match_name}
        >
          🔗 Ver ficha en TikTok Shop
          {producto.url_match_score < 0.99 && " · comprueba que es el correcto"}
        </a>
      ) : (
        <button
          type="button"
          disabled={buscarUrl.isPending || !producto.titulo_tiktok_completo}
          onClick={() =>
            buscarUrl.mutate({ source, folder, producto: producto.producto })
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

      {/* Ya no se elige el generador (Veo3/Kling): Veo3 dejó de poner marca de
          agua en 2026-07 y Kling nunca la puso, así que no hay nada que
          quitar y la elección no cambiaba el resultado. */}
      <div className="flex rounded-md border border-border/60 p-0.5 text-[11px]">
        {(["auto", "hombre", "mujer"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSexo(s)}
            title={
              s === "auto"
                ? "Mira la mano del vídeo y elige la voz: mujer salvo que se vea reloj o vello"
                : undefined
            }
            className={`flex-1 rounded px-1.5 py-1 transition ${
              sexo === s ? "bg-emerald-500 font-semibold text-white" : "text-muted-foreground"
            }`}
          >
            {s === "auto" ? "🖐️ Auto" : s === "hombre" ? "👨 Hombre" : "👩 Mujer"}
          </button>
        ))}
      </div>

      {/* Cada herramienta por separado. Todas marcadas = montaje completo;
          ninguna = vídeo limpio (solo la voz, y sin marca si es Veo3). */}
      <div className="space-y-1.5 rounded-md border border-border/60 p-2">
        {/* Plegado por defecto: casi siempre van las cuatro marcadas, así que
            desplegado solo ocupaba media pantalla en el móvil. El resumen dice
            cuántas van sin abrirlo. */}
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
                tools[t.key] ? "bg-emerald-500/10" : "text-muted-foreground"
              }`}
            >
              <input
                type="checkbox"
                className="h-4 w-4 shrink-0 accent-emerald-500"
                checked={tools[t.key]}
                onChange={(e) =>
                  setTools((prev) => ({ ...prev, [t.key]: e.target.checked }))
                }
              />
              <span className="truncate">{t.label}</span>
            </label>
          ))}
        </div>
        )}
        {!Object.values(tools).some(Boolean) && (
          <p className="text-[10px] text-amber-500">
            Vídeo limpio: solo la voz, sin nada encima.
          </p>
        )}
      </div>

      {/* Vídeo ya montado: verlo y descargarlo sin salir de aquí. Al remontar
          el producto, `video_listo_at` cambia y la URL con él, así que apunta
          a la versión nueva y no a la cacheada. */}
      {/* El reproductor va en un modal, no incrustado en la ficha: con 10
          productos por carpeta, diez vídeos cargando a la vez se comen los
          datos del móvil. El modal solo carga el que se abre. */}
      {producto.video_path && (
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            onClick={() => setVerVideo(true)}
            className="flex items-center justify-center gap-1.5 rounded-md border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-[11px] font-semibold text-emerald-500"
          >
            ▶ Ver vídeo
          </button>
          {/* `download` es lo que diferencia esto del botón de la cola: sin
              él el navegador NAVEGA a la URL (parece que carga una página)
              en vez de descargar directamente. */}
          <a
            href={buildVideoUrl(source, folder, producto.producto, producto.video_listo_at ?? 0, true)}
            download={`${folder}_${producto.producto}.mp4`.replace(/[^a-zA-Z0-9_.-]+/g, "_")}
            className="flex items-center justify-center gap-1.5 rounded-md border border-emerald-500/50 px-2 py-1.5 text-[11px] text-emerald-500"
          >
            <Download className="h-3.5 w-3.5" /> Descargar
          </a>
        </div>
      )}

      <VideoModal
        open={verVideo}
        onOpenChange={setVerVideo}
        title={`Producto ${producto.producto}`}
        filename={(producto.video_path ?? "").split("/").pop() ?? ""}
        videoUrl={
          producto.video_path
            ? buildVideoUrl(source, folder, producto.producto, producto.video_listo_at ?? 0)
            : null
        }
        downloadUrl={
          producto.video_path
            ? buildVideoUrl(source, folder, producto.producto, producto.video_listo_at ?? 0, true)
            : null
        }
      />

      {producto.modo_plazos && (
        /* Lo que va a decir la voz, a la vista antes de montar. Se sortea de
           los cinco textos del curso y no gasta ninguna llamada de API, así
           que pedir otro es gratis. */
        producto.guion ? (
          <div className="space-y-1 rounded border border-border/60 bg-muted/30 p-2">
            {/* Plegado, como en el POV BOF Largo: el guion se lee una vez y
                luego solo estorba entre el precio y los clips. */}
            <button
              type="button"
              onClick={() => setVerGuion((v) => !v)}
              className="flex w-full items-center justify-between gap-2 text-[10px] font-medium text-muted-foreground"
            >
              <span>
                🎬 Guion de plazos
                <span className="ml-1 opacity-70">
                  {producto.guion_caracteres} car. · ~
                  {Math.round(producto.guion_caracteres / CAR_POR_SEG)}s
                </span>
              </span>
              <span>{verGuion ? "▾" : "▸"}</span>
            </button>
            {verGuion && (
            <>
            <p className="text-[10px] leading-relaxed">{producto.guion}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <CopyChip label="🎬 Guion" text={producto.guion ?? ""} />
              <button
                type="button"
                disabled={sortear.isPending}
                onClick={() =>
                  sortear.mutate(
                    { source, folder, producto: producto.producto, rehacer: true },
                    {
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="ml-auto inline-flex items-center gap-1 rounded border border-border/60 px-2 py-0.5 text-[10px] transition hover:border-foreground/40 disabled:opacity-50"
              >
                <RefreshCw className={`h-3 w-3 ${sortear.isPending ? "animate-spin" : ""}`} />
                Otro guion
              </button>
            </div>
            </>
            )}
          </div>
        ) : (
          <button
            type="button"
            disabled={sortear.isPending}
            onClick={() =>
              sortear.mutate(
                { source, folder, producto: producto.producto },
                { onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)) },
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 px-3 py-1.5 text-xs font-medium text-violet-500 transition hover:border-violet-500 disabled:opacity-50"
          >
            {sortear.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
            Ver el guion de plazos
          </button>
        )
      )}

      {producto.modo_plazos ? (
        /* Producto de plazos: el guion dura ~15s, así que hacen falta DOS
           clips y no se monta hasta tener los dos. */
        <div className="grid grid-cols-2 gap-1.5">
          {([1, 2] as const).map((slot) => {
            const puesto = slot === 1 ? producto.clip1 : producto.clip2;
            const pctSlot = pctsClip[slot];
            const subiendoEste = pctSlot !== null;
            return (
              <label
                key={slot}
                className={`flex cursor-pointer items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-[11px] font-medium transition ${
                  puesto
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                    : "border-border/60 hover:border-violet-500/60"
                } ${subiendoEste ? "pointer-events-none opacity-60" : ""}`}
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
                    {/* Quitar un clip subido por error. Corta el evento: el
                        botón es un <label> con el input dentro y si no se
                        abriría el selector de ficheros. */}
                    {puesto && (
                      <span
                        role="button"
                        tabIndex={0}
                        aria-label={`Quitar el clip ${slot}`}
                        title="Quitar este clip"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          quitarClip.mutate(
                            { source, folder, producto: producto.producto, slot },
                            {
                              onSuccess: () => toast.success(`Clip ${slot} quitado`),
                              onError: (e2) =>
                                toast.error(
                                  e2 instanceof ApiError ? e2.message : String(e2),
                                ),
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
                  ref={clipRefs[slot]}
                  type="file"
                  accept="video/*"
                  disabled={subiendoEste}
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadVideo(f, slot);
                    e.target.value = "";
                  }}
                />
              </label>
            );
          })}
        </div>
      ) : null}
      {producto.montando && producto.modo_plazos ? (
        <p className="flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Locutando y montando…
        </p>
      ) : null}

      {!producto.modo_plazos && (
      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) uploadVideo(f);
          e.target.value = "";
        }}
      />
      )}
      {!producto.modo_plazos && (
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={uploading}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-xs font-medium transition hover:border-foreground/30 disabled:opacity-50"
      >
        {uploading ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo {pct}%
          </>
        ) : producto.montando ? (
          // La lista se sondea sola mientras esto sea cierto, así que el
          // botón de Ver/Descargar aparece solo al terminar.
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Montando el vídeo…
          </>
        ) : (
          <>
            <Upload className="h-3.5 w-3.5" /> Subir vídeo
          </>
        )}
      </button>
      )}

      {/* Solo en "Mis productos": son los que sube el operador, así que
          también los puede quitar. Las del curso son de solo lectura. */}
      {source === "mis_productos" && (
        <button
          type="button"
          disabled={borrar.isPending}
          onClick={() => {
            if (
              !window.confirm(
                `¿Quitar el producto ${producto.producto}? Se borran sus dos fotos.`,
              )
            )
              return;
            borrar.mutate(
              { carpeta: folder, producto: producto.producto },
              {
                onSuccess: () => toast.success(`Producto ${producto.producto} borrado`),
                onError: (e) =>
                  toast.error(e instanceof ApiError ? e.message : String(e)),
              },
            );
          }}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-red-500/60 hover:text-red-500 disabled:opacity-50"
        >
          {borrar.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Borrando…
            </>
          ) : (
            <>🗑️ Quitar este producto</>
          )}
        </button>
      )}

      {/* Lo de abajo NO es trabajo: es marcar en qué punto está el producto.
          Separado con una línea para que no se confunda con los botones de
          arriba, que sí hacen cosas. */}
      <div className="flex gap-1.5 border-t border-border/60 pt-2">
        {/* Va PRIMERO porque es lo primero que pasa de verdad: el producto
            entra en el escaparate antes de que se publique nada. */}
        <button
          type="button"
          onClick={toggleEscaparate}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            enEscaparate
              ? "border-sky-500 bg-sky-500/15 text-sky-500"
              : "border-border/60 text-muted-foreground hover:border-foreground/40"
          }`}
        >
          🏪 Escaparate
        </button>
        <button
          type="button"
          onClick={toggleUploaded}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            uploaded
              ? "border-sky-500 bg-sky-500/15 text-sky-500"
              : "border-border/60 text-muted-foreground hover:border-foreground/40"
          }`}
        >
          📤 Subido
          {uploaded && producto.uploaded_at ? (
            <span className="ml-1 font-normal opacity-80">
              {horaCorta(producto.uploaded_at)}
            </span>
          ) : null}
        </button>
        <button
          type="button"
          onClick={toggleSold}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            sold
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
