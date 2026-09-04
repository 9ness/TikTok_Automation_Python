"use client";

import {
  Check,
  PenLine,
  Clapperboard,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Download,
  Link2 as LinkIcon,
  Loader2,
  Trash2,
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

import { nombreDescarga } from "@/lib/descargas";

import { api, ApiError } from "@/lib/api";
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
  useMarcarPendiente,
  usePhotos,
  usePrompts,
  useProductos,
  useProductosTodos,
  refrescarDesdeDrive,
  useBuscarProductoUrl,
  useHashtags,
  useGuardarHashtags,
  useEscribirGuionProducto,
  useGuionesLote,
  useResolverIds,
  useClipSCarpeta,
  useRenumerarMisProductos,
  usePlanRecolocar,
  useBuscarUrlsCarpeta,
  useEchoTikEstado,
  useGuardarEchoTik,
  useEchoTikCuentas,
  useGuardarCuentaEchoTik,
  useActivarCuentaEchoTik,
  useBorrarCuentaEchoTik,
  useMontarConLosClips,
  useSetEstado,
  useQuitarClip,
  useBorrarMiProducto,
  useLimpiarProducto,
  useMoverMiProducto,
  useImportarProductosWeb,
  useImportarProductosWebLote,
  useSources,
  useVendidos,
  useSumarUnidades,
  useBuscarProductos,
  ANCHO_CHIP,
  ANCHO_VISOR,
} from "@/lib/queries/nichoPovBof";
import { BotonDescarga } from "@/components/tiktok-shop-ai-pro/BotonDescarga";
import { MontadoEl } from "@/components/tiktok-shop-ai-pro/MontadoEl";
import { ChipAjuste } from "@/components/tiktok-shop-ai-pro/ChipAjuste";
import { FiltroSoloUrl } from "@/components/tiktok-shop-ai-pro/FiltroSoloUrl";
import { Caja, OSepara, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { MagnificSpaces } from "@/components/tiktok-shop-ai-pro/MagnificSpaces";
import { PrecioAMano } from "@/components/tiktok-shop-ai-pro/PrecioAMano";
import { SincronizarTopVendidos } from "@/components/tiktok-shop-ai-pro/SincronizarTopVendidos";
import { TextosDelAdmin } from "@/components/tiktok-shop-ai-pro/TextosDelAdmin";
import { useEsPro, useMe } from "@/lib/queries/auth";
import { Portal } from "@/components/ui/portal";
import { VideoModal } from "@/components/ui/video-modal";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type {
  ProductoBuscado,
  ProductoItem,
  VideoUploadResponse,
} from "@/lib/types/nichoPovBof";
import {
  alElegirEnLaApp,
  alSubirCadaFichero,
  haySubidaNativa,
  subirConLaApp,
} from "@/lib/subidaNativa";
import { useRefrescarAlVolver } from "@/lib/hooks/useRefrescarAlVolver";
import { useAlTerminarJob } from "@/lib/hooks/useAlTerminarJob";

/** EchoTik apagado a petición del operador: su cuota gratis no da para el
 *  volumen diario y de momento no lo usa. Poniéndolo a `true` vuelven el panel
 *  de credenciales y los botones de buscar la ficha del producto. */
const MOSTRAR_ECHOTIK = false;

/** Los dos flujos de la carpeta: un producto lleva guion de plazos o el de
 *  siempre, según su precio. Ya NO cambia cuántos clips hace falta subir (son
 *  dos en los dos casos), solo de dónde sale la voz. */
/** Cuántos clips pide este producto: DOS, siempre.
 *
 *  Sale de medir el banco: los audios duran entre 9,7s y 13,9s (mediana 12s) y
 *  un clip da 8s, o 9,6s estirado un 20%. Con uno solo faltaba trozo en todos,
 *  y ese hueco se rellenaba repitiendo el final del clip hacia atrás y hacia
 *  delante — en un vídeo de 12s, un tercio era ese rebote. Es además la misma
 *  regla del POV BOF Largo, `techo(segundos / 9,6)`, aplicada a este banco: da
 *  dos hasta para el audio más corto.
 *
 *  Sigue siendo una función y no un `2` suelto porque es el sitio donde mirar
 *  si los clips dejan de durar 8s: lo siguen la tarjeta, los recuentos, los
 *  botones de descarga y cuántos huecos de subida se pintan.
 */
function clipsDe(p: { modo_plazos: boolean; clips_necesarios?: number }): number {
  // Lo calcula el backend: con guion propio manda la voz (223 caracteres caben
  // en UN clip de 10s), y sin guion son dos, porque la frase del banco se
  // sortea al montar y hay que ponerse en la más larga.
  return Math.min(4, Math.max(1, p.clips_necesarios || 2));
}

/** Qué subconjunto se baja. Mismo planteamiento que el POV BOF Largo, para que
 *  las dos pantallas se usen igual: lo que importa es si el producto tiene ya
 *  enlazada su ficha de TikTok Shop —es con los que se trabaja— y cuántos clips
 *  pide, que es lo que hay que generar en Magnific. Los recuentos por clips van
 *  SOBRE los que tienen ficha. */
type Filtro = "todas" | "url" | "clips1" | "clips2";

interface ParaFiltrar {
  modo_plazos: boolean;
  product_url?: string;
  clips_necesarios?: number;
}

function cuadra(p: ParaFiltrar, filtro: Filtro): boolean {
  if (filtro === "todas") return true;
  const conUrl = Boolean(p.product_url);
  if (filtro === "url") return conUrl;
  return conUrl && clipsDe(p) === (filtro === "clips1" ? 1 : 2);
}

/** Cómo se nombra cada subconjunto cuando no hay nada que bajar. */
function textoFiltro(filtro: Filtro): string {
  if (filtro === "url") return "con la ficha enlazada";
  if (filtro === "clips1") return "de 1 clip con la ficha enlazada";
  if (filtro === "clips2") return "de 2 clips con la ficha enlazada";
  return "";
}

// Un color por número de clips, el mismo que en el POV BOF Largo (allí son 3 y
// 4). Ni verde ni violeta: ya significan "ficha enlazada" y "plazos".
const BORDE_CLIPS: Record<number, string> = {
  1: "border-l-4 border-l-sky-500",
  2: "border-l-4 border-l-lime-500",
};

const CHIP_CLIPS: Record<number, string> = {
  1: "bg-sky-500/15 text-sky-500",
  2: "bg-lime-500/15 text-lime-500",
};

/** Subir un ZIP de la web del curso.
 *
 *  El catálogo se actualiza a menudo, así que esto está pensado para
 *  RESUBIRSE: la carpeta se llama como el ZIP y cada producto se compara con
 *  lo que ya había. Después de importar se dice cuáles son nuevos, porque son
 *  justo a los que hay que ponerles la ficha de TikTok.
 */
function ImportarZipWeb({
  source = "productos_web",
  onImportado,
}: {
  /** A qué catálogo van los ZIP: el de la web vieja o el inventario nuevo. */
  source?: string;
  onImportado: (carpeta: string) => void;
}) {
  const qcWeb = useQueryClient();
  const importar = useImportarProductosWeb();
  const lote = useImportarProductosWebLote();
  const abrirCola = useDrawerStore((s) => s.openQueue);
  const entrada = useRef<HTMLInputElement>(null);
  // Cuántos ZIP está subiendo la app y cuántos ha terminado. En el WebView el
  // selector NO le devuelve los ficheros al `<input>` —pasó igual con los
  // vídeos—, así que ahí sube la app y la web solo recoge el resultado.
  const [porLaApp, setPorLaApp] = useState<{ total: number; hechos: number } | null>(
    null,
  );
  // Una línea por carpeta, no solo la última: con 31 ZIP, ver solo el
  // resultado del último no dice nada.
  const [hechas, setHechas] = useState<
    {
      carpeta: string;
      nuevos: string[];
      actualizados: string[];
      iguales: string[];
      incompletos: string[];
    }[]
  >([]);

  function apuntar(r: {
    carpeta: string;
    nuevos: string[];
    actualizados: string[];
    iguales: string[];
    incompletos: string[];
  }) {
    setHechas((antes) => [...antes.filter((x) => x.carpeta !== r.carpeta), r]);
  }

  /** Se lo pasa a la app si sabe subir. `false` = que lo haga la web. */
  function lanzarConLaApp(nombres: string[]): boolean {
    if (!haySubidaNativa() || !nombres.length) return false;
    const base = api.baseUrl;
    const lanzada = subirConLaApp({
      url: `${base}/api/v1/nicho-pov-bof/productos-web/importar`,
      apiKey: process.env.NEXT_PUBLIC_API_KEY ?? "",
      // Uno por ZIP: el servidor importa cada uno en su petición y contesta
      // con lo que ha entrado.
      tareas: nombres.map((nombre) => ({ nombre, campos: {} })),
    });
    if (!lanzada) return false;
    setPorLaApp({ total: nombres.length, hechos: 0 });
    toast.success(`${nombres.length} ZIP(s) subiendo con la app`);
    return true;
  }

  // Lo que va terminando la app, ZIP a ZIP.
  useEffect(() => alSubirCadaFichero((nombre, respuesta) => {
    let r: {
      carpeta?: string;
      nuevos?: string[];
      actualizados?: string[];
      iguales?: string[];
      incompletos?: string[];
    } = {};
    try {
      r = JSON.parse(respuesta || "{}");
    } catch {
      // Respuesta rota: cuenta igual, pero no se puede resumir.
    }
    if (r.carpeta) {
      apuntar({
        carpeta: r.carpeta,
        nuevos: r.nuevos ?? [],
        actualizados: r.actualizados ?? [],
        iguales: r.iguales ?? [],
        incompletos: r.incompletos ?? [],
      });
    } else {
      toast.error(`No se pudo importar ${nombre}`);
    }
    setPorLaApp((v) => (v ? { ...v, hechos: v.hechos + 1 } : v));
    void qcWeb.invalidateQueries({ queryKey: nichoPovBofKeys.all });
  }), [qcWeb]);

  // Si el selector de la app no llegó a devolverlos al `<input>`, la app avisa
  // aparte con los NOMBRES y con eso basta: sube ella.
  useEffect(() => alElegirEnLaApp((nombres) => {
    const zips = nombres.filter((n) => n.toLowerCase().endsWith(".zip"));
    if (zips.length) lanzarConLaApp(zips);
  }), []);

  return (
    <div className="space-y-2 rounded-lg border border-cyan-500/40 bg-cyan-500/5 p-2">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Sube los ZIP de la web —<strong className="text-foreground">puedes
        elegir los 31 de golpe</strong>—. Cada carpeta se llama como su fichero,
        así que puedes volver a subirlos cuando los actualicen: solo se tocan
        los productos que hayan cambiado, y la primera vez es la lenta. Con más
        de uno va a la cola y ahí ves el avance.
      </p>

      <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-cyan-600">
        {lote.isPending || importar.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo…
          </>
        ) : (
          <>
            <Upload className="h-3.5 w-3.5" /> Subir ZIPs de la web
          </>
        )}
        <input
          ref={entrada}
          type="file"
          accept=".zip,application/zip"
          multiple
          disabled={lote.isPending || importar.isPending}
          className="hidden"
          onChange={(e) => {
            const fs = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (!fs.length) return;
            // UNO se importa al momento, que es cuestión de segundos; VARIOS
            // van a la cola: treinta y uno son cientos de MB y aquí se agotaría
            // el tiempo a mitad, sin saber por dónde iba.
            if (lanzarConLaApp(fs.map((f) => f.name))) return;
            const uno = fs[0];
            if (fs.length === 1 && uno) {
              importar.mutate(
                { archivo: uno, source },
                {
                  onSuccess: (r) => {
                    apuntar(r);
                    onImportado(r.carpeta);
                    const n = r.nuevos.length + r.actualizados.length;
                    toast.success(
                      n ? `${r.carpeta}: ${n} producto(s) puestos` : `${r.carpeta}: sin cambios`,
                    );
                  },
                  onError: (err) => toast.error(err.message),
                },
              );
              return;
            }
            lote.mutate(
              { archivos: fs, source },
              {
                onSuccess: (r) => {
                  toast.success(`${r.zips} ZIP(s) en la cola`);
                  abrirCola();
                },
                onError: (err) => toast.error(err.message),
              },
            );
          }}
        />
      </label>

      {porLaApp && porLaApp.hechos < porLaApp.total && (
        <p className="flex items-center gap-1.5 text-[10px] text-cyan-400">
          <Loader2 className="h-3 w-3 animate-spin" />
          Subiendo con la app · {porLaApp.hechos} de {porLaApp.total}
        </p>
      )}

      {hechas.length > 0 && (
        <div className="space-y-1 text-[10px] leading-tight">
          {(() => {
            const nuevos = hechas.reduce((n, x) => n + x.nuevos.length, 0);
            const cambiados = hechas.reduce((n, x) => n + x.actualizados.length, 0);
            const iguales = hechas.reduce((n, x) => n + x.iguales.length, 0);
            return (
              <p className="font-semibold text-foreground">
                {hechas.length} carpeta(s) · {nuevos} nuevo(s), {cambiados} cambiado(s),
                {" "}
                {iguales} sin tocar
              </p>
            );
          })()}
          <div className="max-h-40 space-y-0.5 overflow-y-auto">
            {hechas.map((x) => (
              <p key={x.carpeta} className="text-muted-foreground">
                <strong className="text-foreground">{x.carpeta}</strong>
                {x.nuevos.length ? (
                  <span className="text-emerald-500"> · nuevos: {x.nuevos.join(", ")}</span>
                ) : null}
                {x.actualizados.length ? (
                  <span className="text-amber-500">
                    {" "}
                    · cambiados: {x.actualizados.join(", ")}
                  </span>
                ) : null}
                {!x.nuevos.length && !x.actualizados.length ? " · sin cambios" : null}
                {x.incompletos.length ? ` · sin las dos fotos: ${x.incompletos.length}` : null}
              </p>
            ))}
          </div>
          <p className="text-muted-foreground">
            A los <span className="text-emerald-500">nuevos</span> hay que ponerles la URL.
          </p>
        </div>
      )}

    </div>
  );
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
  const marcarPendiente = useMarcarPendiente(source);

  const openQueue = useDrawerStore((s) => s.openQueue);

  const data = folders.data;
  const folder = picked ?? data?.current ?? null;
  // La carpeta que arma la app, no Drive: no tiene fotos propias que listar ni
  // se marca como completada, y sus tarjetas vienen cada una de SU carpeta.
  const esEsperandoStock = folder === CARPETA_ESPERANDO_STOCK;
  const photos = usePhotos(source, esEsperandoStock ? null : folder);

  // --- Fase 2: automatización de vídeos ---
  const prompts = usePrompts();
  const qc = useQueryClient();
  // Igual que en el POV BOF Largo: en cuanto la cola dice que un montaje
  // terminó, se repregunta, en vez de esperar al sondeo de 5 s.
  useAlTerminarJob((job) => {
    // Apagar el "Montando el vídeo…" AL MOMENTO, sin esperar a la respuesta.
    // Repreguntar la lista relee la carpeta del Drive y son 10-15s: el vídeo
    // ya estaba hecho y la tarjeta seguía diciendo que se estaba montando.
    //
    // El producto sale del TÍTULO del trabajo ("… producto 9 · Carpeta_1"):
    // el evento de la cola no trae los parámetros. Si no casa, no se toca
    // nada y se queda el comportamiento de antes.
    const m = /producto\s+(\S+)\s+·\s+(.+)$/.exec(job.title || "");
    const pid = m?.[1];
    if (pid && m?.[2]?.trim() === folder) {
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(source, folder),
        (prev) => prev?.map((p) => (p.producto === pid ? { ...p, montando: false } : p)),
      );
    }
    void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all });
  });
  // Y al volver a la app. Los trabajos que terminan con la pantalla en segundo
  // plano no los ve el enganche de arriba —los ya acabados al montar no
  // disparan nada, a propósito— y la lista se queda diciendo "0/6" aunque el
  // servidor tenga los guiones escritos.
  useRefrescarAlVolver(() => {
    void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all });
  });
  const productos = useProductos(source, folder);
  const esTopVendidos = source === FUENTE_TOP_VENDIDOS;
  // Los dos catálogos del operador (muestras y tareas). Se comportan igual en
  // toda la pantalla: se sube, se borra, se recoloca y se mueve entre ellos.
  const esCatalogoOperador = CATALOGOS_PROPIOS.includes(source);
  // Se recuerda: si lo pones para ver lo que te queda por probar, la próxima
  // vez que entres quieres lo mismo.
  // Trabajar solo con los que ya tienen la ficha enlazada: son los que se van
  // a subir, y en una carpeta a medias el resto solo estorba. Filtra lo que se
  // VE, y como los botones cuentan sobre lo que se ve, también lo que se baja.
  const [soloConUrl, setSoloConUrl] = useEstadoDeUsuario("povbof:solo-url", false);
  const [soloSinSubir, setSoloSinSubir] = useEstadoRecordado(
    "povbof:topventas:sinsubir", false,
  );
  // Selección múltiple, solo en los catálogos del operador (las carpetas del
  // curso son de solo lectura). Se guardan las claves
  // `carpeta|producto` porque en la vista global conviven varias carpetas.
  const [seleccion, setSeleccion] = useState<string[]>([]);
  const [confirmarBorrado, setConfirmarBorrado] = useState(false);
  const borrarSeleccion = useBorrarMiProducto();
  const [borrandoLote, setBorrandoLote] = useState(false);
  const moverSeleccion = useMoverMiProducto();
  const [moviendoLote, setMoviendoLote] = useState(false);
  const limpiarSeleccion = useLimpiarProducto();
  const [limpiandoLote, setLimpiandoLote] = useState(false);
  async function limpiarLote() {
    setLimpiandoLote(true);
    const fallados: string[] = [];
    let limpiados = 0;
    for (const k of seleccion) {
      const [carpeta = "", ...resto] = k.split("|");
      const producto = resto.join("|");
      try {
        await limpiarSeleccion.mutateAsync({ source, folder: carpeta, producto });
        limpiados += 1;
      } catch {
        fallados.push(producto);
      }
    }
    setLimpiandoLote(false);
    setSeleccion([]);
    if (fallados.length) {
      toast.error(`No se pudieron limpiar: ${fallados.join(", ")}`);
    } else {
      toast.success(`${limpiados} producto(s) limpiados`);
    }
  }
  async function moverLote() {
    const destino = otroCatalogo(source);
    if (!destino) return;
    setMoviendoLote(true);
    const fallados: string[] = [];
    let movidos = 0;
    for (const k of seleccion) {
      const [carpeta = "", ...resto] = k.split("|");
      const producto = resto.join("|");
      try {
        await moverSeleccion.mutateAsync({ carpeta, producto, origen: source, destino });
        movidos += 1;
      } catch {
        fallados.push(producto);
      }
    }
    setMoviendoLote(false);
    setSeleccion([]);
    if (fallados.length) {
      toast.error(`No se pudieron mover: ${fallados.join(", ")}`);
    } else {
      toast.success(`${movidos} a «${NOMBRE_CATALOGO[destino] ?? destino}»`);
    }
  }
  async function borrarLote() {
    // De uno en uno contra el endpoint que ya existe: son diez como mucho, y
    // en serie el error dice EXACTAMENTE cuál falló en vez de morir el lote.
    setBorrandoLote(true);
    const fallados: string[] = [];
    for (const k of seleccion) {
      const [carpeta = "", ...resto] = k.split("|");
      const producto = resto.join("|");
      try {
        await borrarSeleccion.mutateAsync({ carpeta, producto, source });
      } catch {
        fallados.push(producto);
      }
    }
    setBorrandoLote(false);
    setSeleccion([]);
    if (fallados.length) {
      toast.error(`No se pudieron borrar: ${fallados.join(", ")}`);
    } else {
      toast.success(
        seleccion.length === 1
          ? "Producto borrado"
          : `${seleccion.length} productos borrados`,
      );
    }
  }
  // Un solo botón para "tráete lo de verdad": carpetas, productos y las ventas
  // del ranking (que se cruzan al listar, no se guardan en el producto).
  const [refrescando, setRefrescando] = useState(false);
  useEffect(() => {
    setSeleccion([]);
  }, [source, folder]);
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

  const productosVisibles = useMemo(() => {
    const base = verTopVendidos(listaProductos, {
      activo: esTopVendidos,
      soloSinSubir,
      yaSubido: (p) => p.uploaded,
    });
    return soloConUrl ? base.filter((p) => Boolean(p.product_url)) : base;
  }, [listaProductos, esTopVendidos, soloSinSubir, soloConUrl]);
  const conUrlEnCarpeta = listaProductos.filter((p) => Boolean(p.product_url)).length;
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
  const fotoConUrl = enPantalla.filter(
    (p) => p.clean_photo_id && cuadra(p, "url"),
  ).length;
  const foto1 = enPantalla.filter(
    (p) => p.clean_photo_id && cuadra(p, "clips1"),
  ).length;
  const foto2 = enPantalla.filter(
    (p) => p.clean_photo_id && cuadra(p, "clips2"),
  ).length;
  // Si TODOS piden los mismos clips (hoy, dos), separarlos no separa nada:
  // ni los botones ni las marcas de la tarjeta aportan. En cuanto vuelva a
  // haber mezcla, reaparecen solos — por eso se mira el dato y no se comenta
  // el código.
  const hayMezclaDeClips =
    new Set(enPantalla.map((p) => clipsDe(p))).size > 1;
  // Lo mismo para los vídeos ya montados: bajar 20 para quedarse con 3 es lo
  // que se quería evitar.
  const videoConUrl = enPantalla.filter(
    (p) => p.video_path && cuadra(p, "url"),
  ).length;
  const video1 = enPantalla.filter(
    (p) => p.video_path && cuadra(p, "clips1"),
  ).length;
  const video2 = enPantalla.filter(
    (p) => p.video_path && cuadra(p, "clips2"),
  ).length;
  // "Textos" es una acción de CARPETA (extrae la carpeta abierta), así que su
  // contador va sobre la carpeta y no sobre lo que se ve.
  const totalCarpeta = productos.data?.length ?? 0;
  const conTexto = (productos.data ?? []).filter((p) => p.titulo).length;
  // Cuántos tienen ya el guion de 10s escrito, para el botón de la carpeta.
  const conGuion = (productos.data ?? []).filter((p) => p.guion_producto).length;
  const guionesLote = useGuionesLote();
  const resolverIds = useResolverIds();
  const clipSCarpeta = useClipSCarpeta();
  // Cuál está puesto en la carpeta: el de sus productos si coinciden todos.
  // Sin esto, al cambiar de carpeta no se marcaba ninguno y parecía que el
  // ajuste se había perdido.
  const clipSCarpetaActual = (() => {
    const vistos = new Set((productos.data ?? []).map((p) => p.clip_s || 10));
    return vistos.size === 1 ? [...vistos][0] : 0;
  })();
  const renumerar = useRenumerarMisProductos();
  // El plan se consulta solo para poner el número en el botón y para poder
  // apagarlo cuando no hay nada que mover. No toca nada: es de lectura.
  const plan = usePlanRecolocar(esCatalogoOperador, source);
  // Con ID se publica pegándolo en el buscador de TikTok Studio; sin él, a mano.
  const conUrl = (productos.data ?? []).filter((p) => p.product_url).length;
  const conId = (productos.data ?? []).filter((p) => p.product_id).length;
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
          : `Ningún vídeo montado ${textoFiltro(filtro)}`,
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
        a.download = nombreDescarga(orden, suya, `${p.producto}${sufijo}`) + ".mp4";
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
          : `No hay productos con foto ${textoFiltro(filtro)}`,
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
        a.download = nombreDescarga(orden, suya, `${p.producto}${sufijo}`);
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

  function togglePendiente(pendiente: boolean) {
    if (!folder) return;
    marcarPendiente.mutate(
      { source, folder, pendiente },
      {
        onSuccess: () =>
          toast.success(
            pendiente
              ? `"${folder}" con vídeos listos para subir`
              : `"${folder}" ya no está pendiente de subir`,
          ),
        onError: (e) => {
          const msg = e instanceof ApiError ? e.message : String(e);
          toast.error(`No se pudo guardar: ${msg}`);
        },
      },
    );
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
          marques aquí —textos, escaparate, subido— es de este nicho. Todos los
          vídeos llevan dos clips; los que pasan de 40 € cambian la voz por el
          guion de plazos.
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
              className={`break-words leading-tight rounded-lg border px-2 py-2 text-[11px] transition sm:text-xs ${
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

        {CATALOGOS_ZIP.includes(source) && (
          <ImportarZipWeb
            source={source}
            onImportado={(carpeta) => {
              setPicked(carpeta);
              void qc.refetchQueries({ queryKey: nichoPovBofKeys.all });
            }}
          />
        )}

        {/* Solo en la fuente propia: en las del curso no hay nada que subir. */}
        {esCatalogoOperador && (
          /* Al crear se salta a la carpeta donde ha caído: las carpetas se
             llenan de diez en diez, así que el producto nuevo puede ir a la
             SIGUIENTE y quedarse invisible mientras miras la anterior. */
          <AltaMiProducto
            source={source}
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
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs sm:text-sm">
          <span className="flex flex-wrap items-center gap-2 font-medium">
            <span>
              {done} / {total} completadas
            </span>
            {/* Lo que se puede publicar mañana. Solo cuenta lo de las carpetas
                marcadas "pendiente" (📤): son las que se preparan de días
                futuros, y hasta ahora había que abrirlas una a una para saber
                cuántos vídeos había hechos. Los sin stock no entran — están
                montados pero no se pueden subir, y esos van a su chip. */}
            {!!data?.listos_para_subir && (
              <span
                title={
                  `${data.listos_para_subir} vídeo(s) montados y sin subir en ` +
                  `${data.carpetas_pendientes ?? 0} carpeta(s) marcadas pendientes. ` +
                  "Los sin stock no cuentan."
                }
                className="rounded-full border border-orange-500/50 bg-orange-500/10 px-2 py-0.5 text-[11px] font-semibold text-orange-400"
              >
                📤 {data.listos_para_subir} listo
                {data.listos_para_subir === 1 ? "" : "s"} para subir
              </span>
            )}
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
              className={`break-words leading-tight rounded border px-2 py-1 text-[10px] transition ${
                // La carpeta ABIERTA se pinta según esté hecha o no: en verde
                // si ya se completó y en azul si aún no. Antes la abierta y las
                // completadas eran del mismo color y no se sabía si la que
                // tenías delante estaba lista o te faltaba terminarla.
                // Y el NARANJA manda sobre los dos: "tiene los vídeos hechos
                // pero sin subir" es lo que se busca de un vistazo cuando se
                // preparan carpetas de días futuros. Que esté completada se
                // sigue leyendo por el ✓.
                f.virtual
                  ? folder === f.name
                    ? "border-amber-500 bg-amber-500/20 font-semibold text-amber-400"
                    : "border-amber-500/50 bg-amber-500/10 text-amber-400"
                  : f.pendiente_subir
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
              {nombreCarpeta(f.name)}
              {/* Enlazados SOBRE EL TOTAL, no el enlazado a secas: un "9"
                  solo no dice si la carpeta tiene nueve productos o diez con
                  uno sin ficha, que es justo lo que hay que saber para decidir
                  si merece abrirla. Con todo enlazado se enseña un número
                  único ("10"), que es el caso normal y así no chilla. */}
              {!!f.total && !f.virtual && (
                <span
                  title={`${f.con_url ?? 0} de ${f.total} con la ficha enlazada`}
                  className={`ml-1 rounded-full px-1 py-px text-[9px] font-semibold ${
                    (f.con_url ?? 0) >= f.total
                      ? "bg-emerald-500/15 text-emerald-500"
                      : "bg-amber-500/15 text-amber-500"
                  }`}
                >
                  {(f.con_url ?? 0) >= f.total ? f.total : `${f.con_url ?? 0}/${f.total}`}
                </span>
              )}
              {/* Retirados del catálogo. No son trabajo pendiente, así que un
                  "8/10" con dos sin stock está DE HECHO terminado — sin este
                  dato esa carpeta parecía quedarse a medias para siempre. */}
              {!!f.sin_stock && (
                <span
                  title={
                    f.virtual
                      ? `${f.sin_stock} vídeo(s) hechos esperando a que vuelva el producto`
                      : `${f.sin_stock} sin stock (retirados del catálogo)`
                  }
                  className="ml-1 rounded-full bg-red-500/15 px-1 py-px text-[9px] font-semibold text-red-400"
                >
                  ✕{f.sin_stock}
                </span>
              )}
              {/* Productos que entraron DESPUÉS de darla por hecha. El catálogo
                  de la web se actualiza, y sin esto una carpeta ya terminada se
                  queda con productos nuevos que no se ven nunca. Mismo aviso
                  ámbar que el de los vendidos sin copiar. */}
              {!!f.nuevos_desde_completada && (
                <span
                  title={`${f.nuevos_desde_completada} producto(s) nuevos desde que la completaste`}
                  className="ml-1 rounded bg-amber-500/20 px-1 py-px text-[9px] font-bold text-amber-500"
                >
                  +{f.nuevos_desde_completada}
                </span>
              )}
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
          icono={esEsperandoStock ? "⏳" : "📂"}
          titulo={nombreCarpeta(folder)}
          hint={
            esEsperandoStock
              ? "Vídeos hechos que no se pueden subir: el producto está sin stock. Salen de aquí en cuanto los marques subidos."
              : `Carpeta ${idx + 1} de ${total}${currentItem?.completed ? " · ya completada" : ""}`
          }
        >
          {!esEsperandoStock && (
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
          )}

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

          {/* Los dos estados de la carpeta, uno al lado del otro: cerrarla y
              dejarla apartada con los vídeos hechos para subirlos otro día.
              En móvil se apilan — el de completar es el ancho porque es el
              que se pulsa a diario. */}
          {!esEsperandoStock && (
          <div className="flex items-stretch gap-2">
            <button
              type="button"
              onClick={() => toggleCompleted(!currentItem?.completed)}
              disabled={markCompleted.isPending}
              title="Marca la carpeta como hecha y salta a la siguiente"
              className={`flex min-w-0 flex-1 items-center justify-center gap-2 truncate rounded-lg px-3 py-3 text-sm font-semibold transition disabled:opacity-50 ${
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
          )}
        </Caja>
      )}


      {/* El trabajo del día, en el ORDEN en que se hace. Cada paso es una caja
          con su número y su color, iguales en los tres nichos: entra gente
          nueva a usar esto y el orden tiene que leerse sin que nadie lo
          explique. Antes era una lista de botones donde "copiar el prompt" y
          "subir todos los vídeos" parecían lo mismo. */}
      {data && folder && !esEsperandoStock && (
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
            titulo="Preparar la carpeta"
            hint={esTopVendidos ? "Aquí los textos se copian del producto original: no se vuelven a leer con IA, que es lo que descuadraba la carpeta." : "Primero los textos (lee la ficha de cada producto), luego el guion que dice la voz. El tercero es opcional y solo para publicar desde el PC."}
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

            {/* Los guiones de la carpeta entera, debajo de los textos porque
                es el paso siguiente y necesita que estén. Van por la cola: son
                diez llamadas a Gemini y con el operador delante serían diez
                esperas seguidas. */}
            {!esPro && (
              <button
                type="button"
                disabled={guionesLote.isPending || conTexto === 0}
                title={
                  conTexto === 0
                    ? "Extrae antes los textos: sin título el guion sale genérico"
                    : "Escribe el guion de 10s de cada producto que no lo tenga"
                }
                onClick={() =>
                  guionesLote.mutate(
                    { source, folder },
                    {
                      onSuccess: (r: { title: string }) => {
                        toast.success(`${r.title} en la cola`);
                        openQueue();
                      },
                      onError: (e: unknown) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 px-3 py-2 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/10 disabled:opacity-50"
              >
                {guionesLote.isPending ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                ) : (
                  <PenLine className="h-4 w-4 shrink-0" />
                )}
                Guiones de la carpeta ({conGuion}/{totalCarpeta})
              </button>
            )}

            {/* El tercero es OPCIONAL y solo sirve si publicas desde el PC:
                saca el ID que TikTok Studio pide para enlazar el producto sin
                buscarlo entre 139 páginas. No hace falta para montar el vídeo,
                por eso va apagado de color y con la etiqueta. */}
            {!esPro && conUrl > 0 && (
              <button
                type="button"
                disabled={resolverIds.isPending}
                title="Para publicar desde el PC: el ID se pega en el buscador de TikTok Studio"
                onClick={() =>
                  resolverIds.mutate(
                    { source, folder },
                    {
                      onSuccess: (r: { resueltos: number; con_url: number }) =>
                        toast.success(
                          `${r.resueltos} ID(s) sacados de ${r.con_url} enlace(s)`,
                        ),
                      onError: (e: unknown) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs font-medium text-muted-foreground transition hover:border-foreground/30 disabled:opacity-50"
              >
                {resolverIds.isPending ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                ) : (
                  <span>🏷️</span>
                )}
                IDs de producto ({conId}/{conUrl})
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold">
                  opcional · PC
                </span>
              </button>
            )}

            {/* La duración de clip para TODA la carpeta: el operador genera la
                tanda entera con la misma herramienta, así que elegirlo diez
                veces era trabajo tonto. El de cada producto sigue estando para
                la excepción. */}
            {!esPro && (
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
            )}

            {/* De tanto borrar quedan carpetas a medias: esto las rellena de
                diez en diez desde la primera y borra las que sobren. Cubre
                también los huecos DENTRO de cada carpeta, porque reparte todos
                los productos en una secuencia seguida — por eso no hace falta
                un botón aparte por carpeta.

                Enseña el plan antes de ejecutarlo: mueve productos ENTRE
                carpetas, arrastrando sus textos, guion, clips y vídeo. */}
            {esCatalogoOperador && (
              <button
                type="button"
                disabled={renumerar.isPending || !plan.data?.movimientos}
                title={
                  plan.data
                    ? `Se moverían ${plan.data.movimientos} de ${plan.data.total} productos`
                    : ""
                }
                onClick={() =>
                  renumerar.mutate(
                    { carpeta: "", source },
                    {
                      onSuccess: (r: { title: string }) => {
                        toast.success(`${r.title} en la cola`);
                        openQueue();
                      },
                      onError: (e: unknown) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 px-3 py-2 text-xs font-medium text-amber-500 transition hover:bg-amber-500/10 disabled:opacity-50"
              >
                {renumerar.isPending ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                ) : (
                  <span>📦</span>
                )}
                {plan.data?.movimientos
                  ? `Recolocar (${plan.data.movimientos} de ${plan.data.total})`
                  : "Carpetas ya recolocadas"}
              </button>
            )}

            {/* Estado de la carpeta, para comparar de un vistazo lo que está
                en el escaparate con lo que ya se publicó. */}
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
            titulo="Generar los clips fuera"
            hint="Baja las fotos y crea los clips en Magnific (o con el prompt en otra herramienta). Los que piden más de un clip van marcados con una franja de color."
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
            {hayMezclaDeClips && (
              <>
                <p className="pt-0.5 text-[10px] text-muted-foreground">
                  De los que tienen URL, por clips:
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  <BotonDescarga
                    onClick={() => void downloadCleanPhotos("clips1")}
                    cargando={false}
                    disabled={downloadingPhotos || !foto1}
                    etiqueta={`1 clip (${foto1})`}
                    tono="clips1"
                  />
                  <BotonDescarga
                    onClick={() => void downloadCleanPhotos("clips2")}
                    cargando={false}
                    disabled={downloadingPhotos || !foto2}
                    etiqueta={`2 clips (${foto2})`}
                    tono="clips2"
                  />
                </div>
              </>
            )}

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
            {hayMezclaDeClips && (
              <>
                <p className="pt-0.5 text-[10px] text-muted-foreground">
                  De los que tienen URL, por clips:
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  <BotonDescarga
                    onClick={() => void downloadVideos("clips1")}
                    cargando={false}
                    disabled={downloadingVideos || !video1}
                    etiqueta={`1 clip (${video1})`}
                    tono="clips1"
                  />
                  <BotonDescarga
                    onClick={() => void downloadVideos("clips2")}
                    cargando={false}
                    disabled={downloadingVideos || !video2}
                    etiqueta={`2 clips (${video2})`}
                    tono="clips2"
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

          <FiltroSoloUrl
            activo={soloConUrl}
            onChange={setSoloConUrl}
            conUrl={conUrlEnCarpeta}
            total={listaProductos.length}
          />

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

          {/* Borrar de varios en varios: son productos que sube el operador y
              se quitan a puñados (una tanda que salió mal), no de uno en uno. */}
          {esCatalogoOperador && enPantalla.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
              <button
                type="button"
                onClick={() =>
                  setSeleccion(
                    seleccion.length === enPantalla.length
                      ? []
                      : enPantalla.map((p) => claveSel(p.folder || folder, p.producto)),
                  )
                }
                className="rounded-md border border-border/60 px-2 py-1 transition hover:border-foreground/40"
              >
                {seleccion.length === enPantalla.length ? "Ninguno" : "Todos"}
              </button>
              <span className="text-muted-foreground">
                {seleccion.length} seleccionado(s)
              </span>
              <button
                type="button"
                disabled={!seleccion.length || limpiandoLote || moviendoLote || borrandoLote}
                onClick={() => void limpiarLote()}
                title="Quitarles el guion, el vídeo y las marcas; los textos se quedan"
                className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border/60 px-2 py-1 font-medium text-muted-foreground transition hover:border-amber-500/60 hover:text-amber-500 disabled:opacity-40"
              >
                {limpiandoLote ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" /> Limpiando…
                  </>
                ) : (
                  <>🧹 Limpiar</>
                )}
              </button>
              <button
                type="button"
                disabled={!seleccion.length || limpiandoLote || moviendoLote || borrandoLote}
                onClick={() => void moverLote()}
                title={`Pasarlos a «${NOMBRE_CATALOGO[otroCatalogo(source)] ?? ""}»`}
                className="inline-flex items-center gap-1.5 rounded-md border border-border/60 px-2 py-1 font-medium text-muted-foreground transition hover:border-violet-500/60 hover:text-violet-400 disabled:opacity-40"
              >
                {moviendoLote ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" /> Moviendo…
                  </>
                ) : (
                  <>→ {NOMBRE_CATALOGO[otroCatalogo(source)] ?? "mover"}</>
                )}
              </button>
              <button
                type="button"
                disabled={!seleccion.length || limpiandoLote || borrandoLote}
                onClick={() => setConfirmarBorrado(true)}
                className="inline-flex items-center gap-1.5 rounded-md border border-border/60 px-2 py-1 font-medium text-muted-foreground transition hover:border-red-500/60 hover:text-red-500 disabled:opacity-40"
              >
                {borrandoLote ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" /> Borrando…
                  </>
                ) : (
                  <>
                    <Trash2 className="h-3 w-3" /> Borrar {seleccion.length || ""}
                  </>
                )}
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
                  marcarClips={hayMezclaDeClips}
                  seleccionado={
                    esCatalogoOperador &&
                    seleccion.includes(claveSel(p.folder || folder, p.producto))
                  }
                  onSeleccion={
                    esCatalogoOperador
                      ? (marcado) => {
                          const k = claveSel(p.folder || folder, p.producto);
                          setSeleccion((prev) =>
                            marcado ? [...prev, k] : prev.filter((x) => x !== k),
                          );
                        }
                      : undefined
                  }
                />
              ))}
            </div>
          )}

          {/* La confirmación dice QUÉ se va y qué se lleva por delante. El
              `confirm()` del navegador salía con el dominio de la app y un
              texto suelto: ni se leía ni se sabía de dónde venía. */}
          <AlertDialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
            <AlertDialogContent className="w-[calc(100vw-2rem)] max-w-md">
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {seleccion.length === 1
                    ? `Quitar 1 producto de ${NOMBRE_CATALOGO[source] ?? source}`
                    : `Quitar ${seleccion.length} productos de ${
                        NOMBRE_CATALOGO[source] ?? source
                      }`}
                </AlertDialogTitle>
                <AlertDialogDescription asChild>
                  <div className="space-y-2">
                    <p>
                      Se borran del Drive sus fotos (la limpia y la de la ficha).
                      Lo que ya esté montado o subido a TikTok no se toca, y el
                      hueco de numeración lo cierras luego con «reordenar».
                    </p>
                    <p className="max-h-24 overflow-y-auto break-words rounded-md bg-muted/40 p-2 font-mono text-[11px]">
                      {seleccion
                        .map((k) => k.split("|").slice(1).join("|"))
                        .join(" · ")}
                    </p>
                    <p className="font-medium text-foreground">No se puede deshacer.</p>
                  </div>
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Dejarlos</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => void borrarLote()}
                  className="bg-red-500 text-white hover:bg-red-600"
                >
                  Sí, borrar
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
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
/** Alta de productos PROPIOS. Solo sale en los catálogos del operador.
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
function AltaMiProducto({
  source = "mis_productos",
  onCreado,
}: {
  /** En cuál de los dos catálogos del operador cae el producto. */
  source?: string;
  onCreado?: (carpeta: string) => void;
}) {
  const crear = useCrearMiProducto();
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const refLimpia = useRef<HTMLInputElement>(null);
  const refFicha = useRef<HTMLInputElement>(null);
  // Capturas de MÁS: características, medidas, qué trae. Son las que dan de
  // qué hablar cuando la tienda pide un vídeo de 30 o 40 segundos; con el
  // título solo, Gemini estira lo mismo con más adjetivos.
  const refExtras = useRef<HTMLInputElement>(null);
  const [extras, setExtras] = useState<File[]>([]);
  const [abierto, setAbierto] = useState(false);
  // La cola de la sesión: los productos preparados que aún no se han subido.
  // Lo que tarda una subida NO es el servidor (las dos fotos se escriben en
  // Drive en el mismo segundo, medido); son los megas saliendo del móvil. Con
  // veinte productos eso es media hora mirando la pantalla de uno en uno, así
  // que se preparan todos y se sube del tirón.
  const [cola, setCola] = useState<
    { limpia: File; ficha: File | null; extras: File[] }[]
  >([]);
  const [subiendoLote, setSubiendoLote] = useState(0);

  function limpiarCampos() {
    setLimpia(null);
    setFicha(null);
    setExtras([]);
    if (refLimpia.current) refLimpia.current.value = "";
    if (refFicha.current) refFicha.current.value = "";
    if (refExtras.current) refExtras.current.value = "";
  }

  function encolar() {
    if (!limpia) {
      toast.error("Falta la foto del producto.");
      return;
    }
    setCola((prev) => [...prev, { limpia, ficha, extras }]);
    limpiarCampos();
  }

  async function subirCola() {
    // De uno en uno, no a la vez: son megas por la misma línea y en paralelo
    // solo se estorban. Además así el error dice EXACTAMENTE cuál falló y los
    // que ya subieron se quedan subidos.
    const pendientes = [...cola];
    let ultimaCarpeta = "";
    for (const [i, item] of pendientes.entries()) {
      setSubiendoLote(i + 1);
      try {
        const r = await crear.mutateAsync({
          fotoLimpia: item.limpia,
          fotoFicha: item.ficha,
          fotosExtra: item.extras,
          source,
        });
        ultimaCarpeta = r.carpeta;
        setCola((prev) => prev.filter((x) => x !== item));
      } catch (e) {
        setSubiendoLote(0);
        toast.error(
          `Se subieron ${i} de ${pendientes.length}. Falló el ${i + 1}: ` +
            (e instanceof ApiError ? e.message : String(e)),
        );
        return;
      }
    }
    setSubiendoLote(0);
    toast.success(`${pendientes.length} producto(s) añadidos`);
    if (ultimaCarpeta) onCreado?.(ultimaCarpeta);
  }

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
          onCreado?.(r.carpeta);
          limpiarCampos();
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
      {/* Solo hacen falta para los guiones largos, así que no ocupan sitio
          arriba: van debajo y en una sola línea. */}
      <label className="flex cursor-pointer flex-col gap-1 rounded-lg border border-dashed border-border/60 p-2.5 transition hover:border-emerald-500/60">
        <span className="text-[11px] font-semibold">
          Más capturas (opcional)
        </span>
        <span className="text-[10px] text-muted-foreground">
          Características, medidas, qué trae. Con ellas se puede pedir un guion
          de 30 o 40 segundos; con el título solo, no.
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
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        <button
          type="button"
          disabled={crear.isPending || !limpia || !!subiendoLote}
          onClick={enviar}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
        >
          {crear.isPending && !subiendoLote ? "Subiendo…" : "Añadir producto"}
        </button>
        {/* Preparar sin subir: lo que tarda son los megas saliendo del móvil,
            así que con varios productos compensa dejarlos listos y subirlos de
            una tacada en vez de esperar delante de cada uno. */}
        <button
          type="button"
          disabled={!limpia || !!subiendoLote}
          onClick={encolar}
          title="Se queda preparado aquí y se sube al final, con los demás"
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/50 px-3 py-2 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/10 disabled:opacity-50"
        >
          ＋ Preparar y añadir otro
        </button>
      </div>

      {!!cola.length && (
        <div className="space-y-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-2">
          <p className="text-[11px] font-semibold">
            {cola.length} producto(s) preparados
            {subiendoLote ? ` · subiendo el ${subiendoLote} de ${cola.length}…` : ""}
          </p>
          <ul className="space-y-0.5">
            {cola.map((item, i) => (
              <li
                key={`${item.limpia.name}-${i}`}
                className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
              >
                <span className="truncate">
                  {i + 1}. {item.limpia.name}
                  {item.ficha ? " + ficha" : " · sin ficha"}
                  {item.extras.length ? ` + ${item.extras.length} captura(s)` : ""}
                </span>
                {!subiendoLote && (
                  <button
                    type="button"
                    aria-label={`Quitar el producto ${i + 1} de la cola`}
                    onClick={() => setCola((prev) => prev.filter((_, j) => j !== i))}
                    className="ml-auto rounded px-1 transition hover:text-red-500"
                  >
                    ✕
                  </button>
                )}
              </li>
            ))}
          </ul>
          <button
            type="button"
            disabled={!!subiendoLote}
            onClick={() => void subirCola()}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
          >
            {subiendoLote ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo{" "}
                {subiendoLote}/{cola.length}…
              </>
            ) : (
              <>⬆️ Subir los {cola.length}</>
            )}
          </button>
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Van de uno en uno por la misma línea. No cierres la pestaña
            mientras suben; si falla uno, los anteriores se quedan subidos y te
            digo cuál fue.
          </p>
        </div>
      )}

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
/** Los dos catálogos que sube el operador. Un producto se graba porque llegó
 *  una MUESTRA gratuita o porque es una TAREA pagada, y eso no se trabaja
 *  igual; por dentro son idénticos (mismas carpetas de diez, mismo convenio de
 *  nombres) y se puede mover de uno a otro. */
const CATALOGOS_PROPIOS = ["mis_productos", "tareas_productos"];

/** Los que entran por ZIP de la web del curso: el de la web vieja y el
 *  "Inventario General" de la nueva (`ttshopaiproapp.com`). Van separados a
 *  propósito — los números de producto se reutilizan entre catálogos, así que
 *  importar lo nuevo encima de lo viejo pegaría textos y vídeos del producto
 *  anterior al mismo número. */
const CATALOGOS_ZIP = ["productos_web", "inventario_general"];

/** La carpeta que no está en Drive: la arma la app con los productos que
 *  tienen el vídeo hecho, están marcados sin stock y siguen sin subir. Se sale
 *  de ella al marcarlos subidos, porque la pertenencia se calcula. */
const CARPETA_ESPERANDO_STOCK = "__esperando_stock__";
const ETIQUETA_ESPERANDO_STOCK = "⏳ Esperando stock";

function nombreCarpeta(nombre: string): string {
  return nombre === CARPETA_ESPERANDO_STOCK ? ETIQUETA_ESPERANDO_STOCK : nombre;
}
const NOMBRE_CATALOGO: Record<string, string> = {
  mis_productos: "Muestras productos",
  tareas_productos: "Tareas Productos",
};

/** El otro catálogo del operador: a donde se mueve desde este. */
function otroCatalogo(source: string): string {
  return CATALOGOS_PROPIOS.find((c) => c !== source) ?? "";
}

/** Clave de una tarjeta para la selección múltiple. Lleva la carpeta porque
 *  en la vista global conviven varias y el número de producto se repite. */
function claveSel(carpeta: string, producto: string): string {
  return `${carpeta}|${producto}`;
}

function ProductoCard({
  source,
  folder,
  producto,
  carpetaHecha = false,
  esTopVendidos = false,
  marcarClips = false,
  seleccionado = false,
  onSeleccion,
}: {
  source: string;
  folder: string;
  producto: ProductoItem;
  /** Marcado para el borrado en lote. */
  seleccionado?: boolean;
  /** Solo en los catálogos del operador: sin esto no se pinta la casilla. */
  onSeleccion?: (marcado: boolean) => void;
  /** ¿Hay productos de distinto nº de clips en pantalla? Solo entonces vale la
   *  pena marcar cuántos pide cada uno. */
  marcarClips?: boolean;
  /** En "Top vendidos" se enseña cuántas veces vendió y si es reciente. */
  esTopVendidos?: boolean;
  /** La carpeta ya tiene textos en OTROS productos. Sirve para marcar al que
   *  se quedó sin ellos: es un producto que apareció tarde (antes se perdían
   *  los de fotos sin extensión y los fundidos bajo un mismo número), y sin
   *  marca pasa desapercibido entre nueve que están completos. */
  carpetaHecha?: boolean;
}) {
  const setEstado = useSetEstado();
  const montar = useMontarConLosClips();
  // Todos los huecos que pide este producto, cubiertos.
  const clipsPuestos =
    [producto.clip1, producto.clip2].slice(0, clipsDe(producto)).every(Boolean);
  const mover = useMoverMiProducto();
  const limpiar = useLimpiarProducto();
  const [confirmarLimpiar, setConfirmarLimpiar] = useState(false);
  // Lo que la tienda pide a cambio de la muestra. Se edita en la tarjeta
  // porque se consulta justo cuando vas a grabar, no en otra pantalla.
  const [editandoNotas, setEditandoNotas] = useState(false);
  const [notas, setNotas] = useState(producto.notas ?? "");
  useEffect(() => {
    setNotas(producto.notas ?? "");
  }, [producto.notas]);
  const quitarClip = useQuitarClip();
  const buscarUrl = useBuscarProductoUrl();
  // La búsqueda puede terminar bien y aun así no traer URL (EchoTik no
  // indexa el producto). Sin distinguirlo, el botón se quedaba igual que
  // antes de pulsarlo y el operador volvía a gastar cuota sin saberlo.
  const urlNoEncontrada = buscarUrl.isSuccess && !producto.product_url;
  const [uploaded, setUploaded] = useState(producto.uploaded);
  const [sold, setSold] = useState(producto.sold);
  const [enEscaparate, setEnEscaparate] = useState(producto.en_escaparate);
  // De dónde sale el producto: solo se marca en los catálogos que NO son el
  // Drive del curso, porque ahí la pregunta no tiene sentido.
  const esCatalogoPropio = source === "productos_web";
  // El guion propio sustituye a la frase del banco: nombra el producto. Sin
  // él, el montaje sigue tirando del banco de audios como siempre.
  const escribirGuion = useEscribirGuionProducto();
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
  // Hasta cuatro: un guion de 30s no cabe en dos clips y el montaje ya sabe
  // pegar los que hagan falta.
  const [pctsClip, setPctsClip] = useState<Record<number, number | null>>({
    1: null, 2: null, 3: null, 4: null,
  });
  const clipRefs: Record<number, React.RefObject<HTMLInputElement>> = {
    1: useRef<HTMLInputElement>(null),
    2: useRef<HTMLInputElement>(null),
    3: useRef<HTMLInputElement>(null),
    4: useRef<HTMLInputElement>(null),
  };
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);
  // Los dos que se usan a diario (Caption y URL) van fuera; el resto detrás de
  // "más". Siete botones en fila hacían que buscar el de siempre costara mirar.
  const [verMasCopias, setVerMasCopias] = useState(false);
  const [confirmarQuitar, setConfirmarQuitar] = useState(false);
  const [verTools, setVerTools] = useState(false);
  const [verGuion, setVerGuion] = useState(false);
  const [verVoz, setVerVoz] = useState(false);
  // UN solo guion para todos: el escrito para ESTE producto. Los de plazos
  // también — la frase de la financiación va dentro, con la CTA original del
  // curso, en vez de ir por los cinco textos de Klarna (genéricos, no nombran
  // el producto y duran 13-20s donde se piden 10).
  const guionActual = producto.guion_producto || "";
  const pedirGuion = () => {
    const onError = (e: unknown) =>
      toast.error(e instanceof ApiError ? e.message : String(e));
    escribirGuion.mutate(
      { source, folder: producto.folder || folder, producto: producto.producto },
      {
        onSuccess: (r: { caracteres: number }) =>
          toast.success(`Guion escrito · ${r.caracteres} car.`),
        onError,
      },
    );
  };
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

  const apiBase = api.baseUrl;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";

  function uploadVideo(file: File, slot = 0) {
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
      } ${marcarClips ? BORDE_CLIPS[clipsDe(producto)] ?? "" : ""}`}
    >
      <div className="flex gap-2">
        {onSeleccion && (
          <input
            type="checkbox"
            checked={seleccionado}
            onChange={(e) => onSeleccion(e.target.checked)}
            title="Seleccionar para borrar"
            className="mt-1 h-4 w-4 shrink-0 accent-red-500"
          />
        )}
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
          {/* Agotado en su web. Va antes que lo demás porque decide si merece
              la pena grabarlo hoy. */}
          {/* Se puede quitar de un toque: un producto vuelve al catálogo, y
              sin esto había que dejarlo marcado para siempre. */}
          {producto.sin_stock && (
            <button
              type="button"
              title="Quitar la marca de sin stock"
              onClick={() =>
                setEstado.mutate({
                  source,
                  folder: producto.folder || folder,
                  producto: producto.producto,
                  sin_stock: false,
                })
              }
              className="mt-0.5 inline-flex items-center gap-1 rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-500"
            >
              🚫 Sin stock · quitar
            </button>
          )}
          {/* Solo con el título leído: sin texto no hay con qué comparar y
              decir "exclusivo" sería inventárselo. */}
          {esCatalogoPropio && producto.titulo && (
            <p className="mt-0.5 inline-flex items-center gap-1 text-[10px]">
              {producto.tambien_en_drive ? (
                <span
                  title="El mismo producto está también en el Drive del curso"
                  className="rounded bg-sky-500/15 px-1.5 py-0.5 font-semibold text-sky-500"
                >
                  📁 también en Drive
                </span>
              ) : (
                <span
                  title="No aparece en ninguna carpeta del Drive de las que ya tienen los textos leídos"
                  className="rounded bg-violet-500/15 px-1.5 py-0.5 font-semibold text-violet-400"
                >
                  🌐 solo web
                </span>
              )}
            </p>
          )}
          {/* El precio decide el GUION (por encima del umbral, el de plazos),
              así que se ve pegado al producto. Cuando la carpeta tiene textos
              pero no se pudo leer el precio se dice: en silencio parecería
              barato y se iría al guion de siempre. */}
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
                  💳 Plazos
                </span>
              )}
              {/* Cuántos clips pide, SOLO si en la carpeta hay de varios
                  tipos. Con todos iguales (hoy, dos) el distintivo lo llevaría
                  cada tarjeta y no distinguiría nada. */}
              {marcarClips && (
                <span
                  className={`rounded px-1.5 py-0.5 font-semibold ${
                    CHIP_CLIPS[clipsDe(producto)]
                  }`}
                >
                  🎞️ {clipsDe(producto)} clip{clipsDe(producto) > 1 ? "s" : ""}
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

      {/* Copiar textos extraídos — solo se muestran los que tengan valor.
          Fuera van Caption y URL, que son los de cada producto; los demás
          (título, tienda, ID, sin stock, foto) se usan de vez en cuando y
          vivían igual de grandes, tapando a los dos de siempre. */}
      <div className="flex flex-wrap gap-1">
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
        <BotonUrl
          url={producto.product_url}
          source={source}
          folder={producto.folder || folder}
          producto={producto.producto}
        />
        <button
          type="button"
          onClick={() => setVerMasCopias((v) => !v)}
          title="Título, tienda, ID, sin stock y descarga de la foto"
          className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40 hover:text-foreground"
        >
          {verMasCopias ? "menos ▲" : "más ▼"}
        </button>
      </div>

      {verMasCopias && (
      <div className="flex flex-wrap gap-1">
        {/* El "Título" a secas no se copiaba nunca (el que se pega en TikTok
            es el completo), así que solo hacía ruido en la ficha. */}
        <CopyChip label="🔎 Título TikTok" text={producto.titulo_tiktok_completo ?? ""} />
        <CopyChip label="🏪 Tienda" text={producto.tienda ?? ""} siempre />
        {/* Gancho y CTA ya no se copian: los quema el propio montaje, y a
            mano solo se usaban cuando el vídeo se hacía en CapCut. */}
        {/* El ID que busca TikTok Studio al enlazar el producto. Sin él hay
            que ir pasando páginas de la lista hasta dar con el tuyo. */}
        {producto.product_id && (
          <CopyChip label="🏷️ ID" text={producto.product_id} siempre />
        )}
        {/* Se descubre al abrir el enlace: TikTok dice que ya no existe y se
            marca aquí mismo, sin salir de la ficha.
            Comprobarlo automáticamente no se puede —TikTok responde un captcha
            a cualquier petición del servidor y un enlace vivo y uno muerto
            salen idénticos—, así que el toque lo da el operador.
            Va al documento COMPARTIDO: el mismo producto se repite en varias
            carpetas y así el siguiente ya no lo abre. */}
        {producto.product_url && !producto.sin_stock && (
          <button
            type="button"
            title="Marcar que su enlace ya no abre (retirado del catálogo)"
            onClick={() =>
              setEstado.mutate({
                source,
                folder: producto.folder || folder,
                producto: producto.producto,
                sin_stock: true,
              })
            }
            className="inline-flex items-center gap-1 break-words leading-tight rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-rose-500/50 hover:text-rose-500"
          >
            🚫 Sin stock
          </button>
        )}
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
      )}

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
          className="block break-words leading-tight rounded-md border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-[11px] text-emerald-500"
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

      {/* Una sola fila para los ajustes de la tarjeta (ver `ChipAjuste`), igual
          que en el POV BOF Largo: la voz va casi siempre en Auto y las
          herramientas casi siempre las cuatro, así que enseñan su valor y se
          abren solo cuando hay que cambiarlos. */}
      <div className="flex items-stretch gap-1.5">
        {/* El guion, como en el Largo: un chip que dice cuánto ocupa y se
            despliega. Antes era una barra de ancho completo entre el precio y
            los clips, para enseñar un texto que se lee UNA vez. */}
        {guionActual ? (
          <ChipAjuste
            icono="🎬"
            /* Segundos, no caracteres: lo que el operador necesita saber es si
               el vídeo llega al mínimo del reto, y 192 caracteres no dicen
               nada. El rango sale del servidor (la voz se sortea entre las que
               caben, y cada una lee a su ritmo); si no lo manda —audio del
               banco, que dura lo que dure— se cae a los caracteres. */
            valor={
              producto.segundos_min
                ? `${producto.segundos_min}-${producto.segundos_max}s`
                : `${guionActual.length} car.`
            }
            abierto={verGuion}
            onToggle={() => setVerGuion((v) => !v)}
            title={
              producto.segundos_min
                ? `Guion de ${guionActual.length} caracteres · el vídeo durará entre ${producto.segundos_min}s y ${producto.segundos_max}s según la voz que salga`
                : `Guion · ${guionActual.length} caracteres`
            }
          />
        ) : (
          <ChipAjuste
            icono={escribirGuion.isPending ? "⏳" : "✍️"}
            valor="Guion"
            abierto={false}
            onToggle={pedirGuion}
            title="Escribir el guion de este producto"
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

      {/* Ya no se elige el generador (Veo3/Kling): Veo3 dejó de poner marca de
          agua en 2026-07 y Kling nunca la puso, así que no hay nada que
          quitar y la elección no cambiaba el resultado. */}
      {/* El texto del guion, desplegado desde su chip. */}
      {guionActual && verGuion && (
        <div className="space-y-1 rounded border border-border/60 bg-muted/30 p-2">
          <p className="text-[10px] leading-relaxed">{guionActual}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            <CopyChip label="🎬 Guion" text={guionActual} />
            {producto.modo_plazos && (
              <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-violet-400">
                plazos
              </span>
            )}
            <button
              type="button"
              disabled={escribirGuion.isPending}
              onClick={() => {
                escribirGuion.mutate(
                  {
                    source,
                    folder: producto.folder || folder,
                    producto: producto.producto,
                    rehacer: true,
                  },
                  {
                    onError: (e: unknown) =>
                      toast.error(e instanceof ApiError ? e.message : String(e)),
                  },
                );
              }}
              className="ml-auto inline-flex items-center gap-1 rounded border border-border/60 px-2 py-0.5 text-[10px] transition hover:border-foreground/40 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3 w-3 ${escribirGuion.isPending ? "animate-spin" : ""}`}
              />
              Otro guion
            </button>
          </div>
        </div>
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
      )}

      {/* Cada herramienta por separado. Todas marcadas = montaje completo;
          ninguna = vídeo limpio (solo la voz). */}
      {verTools && (
      <div className="space-y-1.5 rounded-md border border-border/60 p-2">
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
      </div>
      )}
      {/* El aviso se ve SIEMPRE, plegado o no: que el vídeo salga sin nada
          encima no puede quedar escondido detrás de un chip. */}
      {!Object.values(tools).some(Boolean) && (
        <p className="text-[10px] text-amber-500">
          Vídeo limpio: solo la voz, sin nada encima.
        </p>
      )}

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
            download={nombreDescarga(folder, producto.producto) + ".mp4"}
            className="flex items-center justify-center gap-1.5 rounded-md border border-emerald-500/50 px-2 py-1.5 text-[11px] text-emerald-500"
          >
            <Download className="h-3.5 w-3.5" /> Descargar
          </a>
        </div>
      )}
      {producto.video_path && <MontadoEl ts={producto.video_listo_at} />}

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

      {/* 8 o 10 segundos. Con guion propio decide cuántos clips hay que subir:
          a 10s el guion entra en uno solo.

          Se enseña SIEMPRE, aunque sin guion no cambie nada: escondido hasta
          tener guion no había manera de encontrarlo, y elegir la duración
          antes de escribirlo es lo natural (ya sabes con qué vas a generar). */}
      {(
        <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <span>Clips de</span>
          {[8, 10].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() =>
                setEstado.mutate({
                  source,
                  folder: producto.folder || folder,
                  producto: producto.producto,
                  clip_s: s,
                })
              }
              className={`rounded px-1.5 py-0.5 font-semibold transition ${
                (producto.clip_s || 10) === s
                  ? "bg-violet-500/20 text-violet-400"
                  : "hover:text-foreground"
              }`}
            >
              {s}s
            </button>
          ))}
          <span className="ml-auto">
            {producto.guion_producto
              ? `${clipsDe(producto)} hueco${clipsDe(producto) === 1 ? "" : "s"}`
              : "2 huecos · sin guion"}
          </span>
        </div>
      )}

      {/* Cuánto tiene que durar el guion. El del curso son ~10s y es lo normal;
          se sube cuando la tienda pide vídeos de 30 o 40 segundos por la
          muestra. Con más segundos hacen falta más clips (el montaje los pega)
          y, sobre todo, más fotos: con el título solo, Gemini estira lo mismo
          con más adjetivos. Se cambia ANTES de pedir el guion. */}
      {CATALOGOS_PROPIOS.includes(source) && (
        <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
          <span>Guion de</span>
          {[0, 20, 30, 40].map((sg) => (
            <button
              key={sg}
              type="button"
              title={
                sg === 0
                  ? "El del curso: ~190 caracteres, unos 10 segundos"
                  : `~${Math.round(sg * 18.2)} caracteres. Necesita capturas del producto para tener qué contar`
              }
              onClick={() =>
                setEstado.mutate(
                  {
                    source,
                    folder: producto.folder || folder,
                    producto: producto.producto,
                    segundos_guion: sg,
                  },
                  {
                    onError: (e) =>
                      toast.error(e instanceof ApiError ? e.message : String(e)),
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
          {!!producto.segundos_guion && (
            <span className="ml-auto text-amber-500/80">
              rehaz el guion para aplicarlo
            </span>
          )}
        </div>
      )}

      {clipsDe(producto) >= 2 ? (
        /* Dos clips o más: el guion manda. No se monta hasta tenerlos todos. */
        <div className="grid grid-cols-2 gap-1.5">
          {Array.from({ length: clipsDe(producto) }, (_, i) => i + 1).map((slot) => {
            const puesto = [
              producto.clip1, producto.clip2, producto.clip3, producto.clip4,
            ][slot - 1];
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
      {producto.montando && clipsDe(producto) >= 2 ? (
        <p className="flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Locutando y montando…
        </p>
      ) : null}

      {/* Los clips están puestos pero no hay vídeo: el montaje falló por algo
          que no son los clips (Gemini sin cuota, la voz sin decidir). Se
          cambia lo que haga falta —normalmente el sexo de la voz, ahí arriba—
          y se relanza sin volver a generar ni subir nada. */}
      {clipsPuestos && !producto.video_path && !producto.montando && (
        <button
          type="button"
          disabled={montar.isPending}
          onClick={() =>
            montar.mutate(
              {
                source,
                folder: producto.folder || folder,
                producto: producto.producto,
                sexo,
              },
              {
                onSuccess: (r) => toast.success(r.message),
                onError: (e) =>
                  toast.error(e instanceof ApiError ? e.message : String(e)),
              },
            )
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/20 disabled:opacity-50"
        >
          {montar.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Encolando…
            </>
          ) : (
            <>🎬 Montar con los clips que ya están</>
          )}
        </button>
      )}

      {clipsDe(producto) === 1 && (
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
      {clipsDe(producto) === 1 && (
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
            <Upload className="h-3.5 w-3.5" /> Subir clip
          </>
        )}
      </button>
      )}

      {/* Solo en los catálogos del operador: son los que sube él, así que
          también los puede quitar y cambiar de sitio. Los del curso son de
          solo lectura. */}
      {CATALOGOS_PROPIOS.includes(source) && (
        <>
        {/* Los cuatro en una fila: son acciones de mantenimiento y una por
            línea se comía media tarjeta. En móvil quedan dos y dos. Las
            etiquetas van cortas — lo que hace cada una lo cuenta el `title` y,
            al pulsarla, el diálogo. */}
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {/* Muestra ⇄ tarea: por qué se graba un producto se sabe a veces
            después de subirlo, y antes había que borrarlo y volver a subir
            las dos fotos. */}
        <button
          type="button"
          disabled={mover.isPending}
          title={`Pasarlo a «${NOMBRE_CATALOGO[otroCatalogo(source)] ?? ""}» con sus fotos y sus datos`}
          onClick={() =>
            mover.mutate(
              {
                carpeta: folder,
                producto: producto.producto,
                origen: source,
                destino: otroCatalogo(source),
              },
              {
                onSuccess: (r) =>
                  toast.success(
                    `Movido a «${NOMBRE_CATALOGO[r.source] ?? r.source}» · ` +
                      `${r.carpeta}, nº ${r.producto}`,
                  ),
                onError: (e) =>
                  toast.error(e instanceof ApiError ? e.message : String(e)),
              },
            )
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-violet-500/60 hover:text-violet-400 disabled:opacity-50"
        >
          {mover.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Moviendo…
            </>
          ) : (
            <>→ {NOMBRE_CATALOGO[otroCatalogo(source)]?.split(" ")[0] ?? "Mover"}</>
          )}
        </button>
        {/* Cuando un producto nace con lo del que ocupaba antes su número:
            se va lo generado y se quedan las fotos y los textos. Borrar y
            volver a subir también valdría, pero obliga a tener las fotos. */}
        <button
          type="button"
          disabled={limpiar.isPending}
          title="Quitarle el guion, el vídeo y las marcas; las fotos y los textos se quedan"
          onClick={() => setConfirmarLimpiar(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-amber-500/60 hover:text-amber-500 disabled:opacity-50"
        >
          {limpiar.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Limpiando…
            </>
          ) : (
            <>🧹 Limpiar</>
          )}
        </button>
        <button
          type="button"
          disabled={borrar.isPending}
          title="Borrar el producto y sus fotos del Drive"
          onClick={() => setConfirmarQuitar(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-red-500/60 hover:text-red-500 disabled:opacity-50"
        >
          {borrar.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Borrando…
            </>
          ) : (
            <>🗑️ Quitar</>
          )}
        </button>
        {/* El cuarto hueco: solo cuando no hay requisitos escritos. Cuando los
            hay, se leen en su caja de abajo y tocarla los edita. */}
        {!producto.notas && (
          <button
            type="button"
            title="Lo que pide la tienda a cambio de la muestra: vídeos, duración, hashtags"
            onClick={() => setEditandoNotas(true)}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-amber-500/60 hover:text-amber-500"
          >
            📋 Requisitos
          </button>
        )}
        </div>
        <AlertDialog open={confirmarLimpiar} onOpenChange={setConfirmarLimpiar}>
          <AlertDialogContent className="w-[calc(100vw-2rem)] max-w-md">
            <AlertDialogHeader>
              <AlertDialogTitle>
                Limpiar lo generado del producto {producto.producto}
              </AlertDialogTitle>
              <AlertDialogDescription asChild>
                <div className="space-y-2">
                  <p className="break-words">
                    {producto.titulo || "Sin título extraído"}
                  </p>
                  <p>
                    Se van el guion, el subliminal, la voz, los clips, el vídeo
                    montado y las marcas de subido y vendido.
                  </p>
                  <p>
                    Se quedan las fotos y los textos (título, tienda, caption,
                    hashtags y el enlace).
                  </p>
                  <p className="font-medium text-foreground">
                    Es para cuando el producto salió con el guion o el vídeo de
                    otro: después vuelve a pedirle el guion y a montarlo.
                  </p>
                </div>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Dejarlo</AlertDialogCancel>
              <AlertDialogAction
                onClick={() =>
                  limpiar.mutate(
                    {
                      source,
                      folder: producto.folder || folder,
                      producto: producto.producto,
                    },
                    {
                      onSuccess: (r) =>
                        toast.success(
                          r.borrados.length
                            ? `Limpiado (${r.borrados.length} campos)`
                            : "No había nada que limpiar",
                        ),
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="bg-amber-500 text-white hover:bg-amber-600"
              >
                Sí, limpiar
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <AlertDialog open={confirmarQuitar} onOpenChange={setConfirmarQuitar}>
          <AlertDialogContent className="w-[calc(100vw-2rem)] max-w-md">
            <AlertDialogHeader>
              <AlertDialogTitle>
                Quitar el producto {producto.producto}
              </AlertDialogTitle>
              <AlertDialogDescription asChild>
                <div className="space-y-2">
                  <p className="break-words">
                    {producto.titulo || "Sin título extraído"} · carpeta «{folder}»
                  </p>
                  <p>
                    Se borran del Drive sus fotos (la limpia y la de la ficha).
                    Lo que ya esté montado o subido a TikTok no se toca, y el
                    hueco de numeración lo cierras luego con «reordenar».
                  </p>
                  <p className="font-medium text-foreground">No se puede deshacer.</p>
                </div>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Dejarlo</AlertDialogCancel>
              <AlertDialogAction
                onClick={() =>
                  borrar.mutate(
                    { carpeta: folder, producto: producto.producto, source },
                    {
                      onSuccess: () =>
                        toast.success(`Producto ${producto.producto} borrado`),
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="bg-red-500 text-white hover:bg-red-600"
              >
                Sí, quitarlo
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        </>
      )}

      {/* Los requisitos del vendedor. Un producto caro no se regala: piden
          tres vídeos, una duración o unos hashtags concretos, y eso no cabe en
          ningún campo de los que ya hay — cada tienda pide lo suyo. Va en la
          tarjeta y no en otra pantalla porque se consulta justo al grabar. */}
      {editandoNotas ? (
        <div className="space-y-1.5 rounded-md border border-amber-500/40 bg-amber-500/5 p-2">
          <textarea
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            rows={4}
            autoFocus
            placeholder={"Qué pide la tienda. Por ejemplo:\n· 3 vídeos, mínimo 30s\n· hashtags #marca #producto\n· enlace del producto en el pie"}
            className="w-full rounded border border-border/60 bg-background p-1.5 text-[11px] leading-relaxed"
          />
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={setEstado.isPending}
              onClick={() => {
                setEstado.mutate(
                  {
                    source,
                    folder: producto.folder || folder,
                    producto: producto.producto,
                    notas,
                  },
                  {
                    onSuccess: () => setEditandoNotas(false),
                    onError: (e) =>
                      toast.error(e instanceof ApiError ? e.message : String(e)),
                  },
                );
              }}
              className="rounded border border-amber-500/50 px-2 py-1 text-[10px] font-semibold text-amber-500 transition hover:bg-amber-500/10 disabled:opacity-50"
            >
              {setEstado.isPending ? "Guardando…" : "Guardar"}
            </button>
            <button
              type="button"
              onClick={() => {
                setNotas(producto.notas ?? "");
                setEditandoNotas(false);
              }}
              className="rounded border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : producto.notas ? (
        <button
          type="button"
          onClick={() => setEditandoNotas(true)}
          title="Editar los requisitos"
          className="w-full space-y-1 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-left transition hover:border-amber-500/70"
        >
          <p className="text-[10px] font-semibold text-amber-500">
            📋 Lo que pide la tienda
          </p>
          <p className="whitespace-pre-wrap text-[10px] leading-relaxed text-muted-foreground">
            {producto.notas}
          </p>
        </button>
      ) : null}

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
