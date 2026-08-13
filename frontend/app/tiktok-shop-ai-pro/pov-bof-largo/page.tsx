"use client";

import {
  Check,
  Clapperboard,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Download,
  HardDrive,
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
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { BotonDescarga } from "@/components/tiktok-shop-ai-pro/BotonDescarga";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { VideoModal } from "@/components/ui/video-modal";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import {
  buildCleanPhotoDownloadUrl,
  useActivarCuentaEchoTik,
  useBackupCheck,
  useBackupSync,
  useBorrarCuentaEchoTik,
  useBuscarProductos,
  useBuscarProductoUrl,
  useBuscarUrlsCarpeta,
  useCrearMiProducto,
  useEchoTikCuentas,
  useEchoTikEstado,
  useExtraerTextos,
  useGuardarCuentaEchoTik,
  useGuardarEchoTik,
  useGuardarHashtags,
  useHashtags,
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
  useSetEstadoLargo,
  useSourcesLargo,
  useSumarUnidadesLargo,
  useVendidosLargo,
  useVocesLargo,
  videoLargoUrl,
} from "@/lib/queries/povBofLargo";
import type {
  BackupCheckResponse,
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

  const [backup, setBackup] = useState<BackupCheckResponse | null>(null);
  const backupCheck = useBackupCheck();
  const backupSync = useBackupSync();
  const openQueue = useDrawerStore((s) => s.openQueue);

  const [downloadingPhotos, setDownloadingPhotos] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState("");
  const [downloadingVideos, setDownloadingVideos] = useState(false);
  const [videoProgress, setVideoProgress] = useState("");
  const [generandoGuiones, setGenerandoGuiones] = useState(false);
  const [guionProgress, setGuionProgress] = useState("");

  const totalProductos = items.length;
  const conVideo = items.filter((p) => p.video_path).length;
  const conFoto = items.filter((p) => p.clean_photo_id).length;
  const esTopVendidos = activaSource === FUENTE_TOP_VENDIDOS;
  const [soloSinSubir, setSoloSinSubir] = useEstadoRecordado(
    "largo:topventas:sinsubir", false,
  );
  const itemsVisibles = useMemo(
    () =>
      verTopVendidos(items, {
        activo: esTopVendidos,
        soloSinSubir,
        yaSubido: (p) => p.uploaded,
      }),
    [items, esTopVendidos, soloSinSubir],
  );
  // Los dos flujos de guion de la carpeta, contados sobre los que tienen foto.
  const conPlazos = items.filter((p) => p.clean_photo_id && p.modo_plazos).length;
  const conViejo = items.filter((p) => p.clean_photo_id && !p.modo_plazos).length;
  const videosPlazos = items.filter((p) => p.video_path && p.modo_plazos).length;
  const videosViejo = items.filter((p) => p.video_path && !p.modo_plazos).length;
  const conTexto = items.filter((p) => p.titulo).length;
  const conGuion = items.filter((p) => p.guion).length;
  const subidos = items.filter((p) => p.uploaded).length;
  const enEscaparate = items.filter((p) => p.en_escaparate).length;
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

  function checkBackup() {
    backupCheck.mutate(undefined, {
      onSuccess: (res) => {
        setBackup(res);
        toast.success(
          res.has_changes
            ? `${res.n_added} nuevos · ${res.n_modified} modificados · ${res.n_deleted} borrados en origen`
            : "Sin cambios desde la última copia",
        );
      },
      onError: (e) => toast.error(err(e)),
    });
  }

  function syncBackup(forceFull: boolean) {
    backupSync.mutate(
      { force_full: forceFull },
      {
        onSuccess: () => {
          toast.success("Backup encolado");
          openQueue();
        },
        onError: (e) => toast.error(err(e)),
      },
    );
  }

  async function downloadVideos(filtro: Filtro = "todas") {
    if (!folder) return;
    const conV = items.filter((p) => p.video_path && cuadra(p, filtro));
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
        a.href = videoLargoUrl(activaSource, folder, p.producto, p.video_listo_at ?? 0, true);
        const sufijo = filtro === "todas" ? "" : `_${filtro}`;
        a.download = `${folder}_${p.producto}${sufijo}.mp4`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
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
    const conF = items.filter((p) => p.clean_photo_id && cuadra(p, filtro));
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
        a.href = buildCleanPhotoDownloadUrl(activaSource, folder, p.producto);
        const sufijo = filtro === "todas" ? "" : `_${filtro}`;
        a.download = `${folder}_${p.producto}${sufijo}`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
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
      return tieneTexto && (!p.guion || esPlazos !== p.guion_plazos);
    });
    if (!pend.length) {
      toast.error("Todos los productos con textos ya tienen guion");
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

      {/* Fuente + progreso */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
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

        <div className="mb-2 flex items-center justify-between text-xs sm:text-sm">
          <span className="font-medium">
            {done} / {total} completadas
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void folders.refetch()}
              className="rounded-md border border-border/60 p-1.5 text-muted-foreground transition hover:text-foreground"
              title="Recargar desde Drive"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${folders.isFetching ? "animate-spin" : ""}`} />
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
              {f.name}
            </button>
          ))}
        </div>


        <button
          type="button"
          onClick={() => setVerVendidos(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-500 transition hover:bg-amber-500/20"
        >
          <ShoppingBag className="h-3.5 w-3.5" />
          Productos que vendieron
          {totalVendidos > 0 && (
            <span className="rounded-full bg-amber-500 px-1.5 text-[10px] font-bold text-black">
              {totalVendidos}
            </span>
          )}
          {unidadesVendidas > totalVendidos && (
            <span className="text-[10px] font-normal opacity-70">
              · {unidadesVendidas} uds
            </span>
          )}
        </button>
      </section>

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

      <CollapsibleCard
        title="⚙️ Configuración"
        subtitle="EchoTik · hashtags · copia de seguridad — el Drive de origen es de solo lectura"
      >
        <div className="space-y-3">
          <EchoTikPanel />
          <HashtagsPanel />

          <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
            <div className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 shrink-0 text-sky-500" />
              <p className="text-sm font-semibold">Copia de seguridad</p>
            </div>
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              El Drive de origen es de un tercero y se borra sin aviso. Comprueba si
              han añadido o cambiado algo y guarda solo la diferencia.
            </p>

            {backup && (
              <div className="space-y-1 rounded-lg border border-border/60 bg-muted/40 p-2 text-[11px]">
                <p className="text-muted-foreground">
                  Última copia:{" "}
                  <span className="font-medium text-foreground">
                    {backup.last_snapshot ?? "ninguna"}
                  </span>
                </p>
                {backup.has_changes ? (
                  <>
                    <p>
                      <span className="font-semibold text-emerald-500">+{backup.n_added}</span> nuevos ·{" "}
                      <span className="font-semibold text-amber-500">~{backup.n_modified}</span> modificados ·{" "}
                      <span className="font-semibold text-red-500">-{backup.n_deleted}</span> borrados
                    </p>
                    <p className="text-muted-foreground">
                      {Math.round(backup.change_ratio * 100)}% del archivo ({backup.n_total_source} ficheros).{" "}
                      {backup.would_be_full ? "Se hará copia COMPLETA nueva." : "Se copiará solo la diferencia."}
                    </p>
                  </>
                ) : (
                  <p className="text-emerald-500">Sin cambios — no hay nada que copiar.</p>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={checkBackup}
                disabled={backupCheck.isPending}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
              >
                {backupCheck.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Comprobar cambios
              </button>
              <button
                type="button"
                onClick={() => syncBackup(false)}
                disabled={backupSync.isPending}
                className="flex items-center justify-center gap-1.5 rounded-lg bg-sky-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-600 disabled:opacity-50"
              >
                {backupSync.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <HardDrive className="h-3.5 w-3.5" />
                )}
                Sincronizar
              </button>
            </div>
            <button
              type="button"
              onClick={() => syncBackup(true)}
              disabled={backupSync.isPending}
              className="w-full rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
            >
              Forzar copia completa nueva
            </button>
            <p className="text-[10px] text-muted-foreground">
              También corre solo cada día a las 06:00.
            </p>
          </section>
        </div>
      </CollapsibleCard>

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

      {data && folder && (
        <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
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
            <div className="min-w-0 flex-1 text-center">
              <p className="truncate text-sm font-semibold sm:text-base">{folder}</p>
              <p className="text-[11px] text-muted-foreground">
                {idx + 1} de {total}
                {currentItem?.completed && " · ✅ completada"}
              </p>
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
        </section>
      )}

      {/* Automatización de vídeos por producto */}
      {data && folder && (
        <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 shrink-0 text-violet-500" />
            <p className="text-sm font-semibold">Automatización de vídeos</p>
            <span className="ml-auto text-[11px] text-muted-foreground">
              {conGuion}/{totalProductos} con guion
            </span>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline gap-1.5">
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
                1
              </span>
              <p className="text-[11px] font-semibold">Preparar</p>
              <p className="truncate text-[10px] text-muted-foreground">textos y ficha del producto</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={runExtraerTextos}
                disabled={extraerTextos.isPending}
                className="flex items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
              >
                {extraerTextos.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                    <span className="truncate">Extrayendo textos…</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">
                      Textos + guiones ({conTexto}/{totalProductos})
                    </span>
                  </>
                )}
              </button>
            </div>

            {/* Subidos y escaparate en la misma línea (ver POV BOF). */}
            <div className="grid grid-cols-2 gap-1.5">
            <div
              className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold ${
                subidos === totalProductos && totalProductos > 0
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 text-muted-foreground"
              }`}
            >
              📤 Subidos {subidos}/{totalProductos}
            </div>

              {/* Junto a "Subidos" para comparar de un vistazo. */}
              <button
                type="button"
                onClick={() => setVerEscaparate(true)}
                className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${
                  enEscaparate === totalProductos && totalProductos > 0
                    ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                    : "border-sky-500/50 bg-sky-500/10 text-sky-500 hover:bg-sky-500/20"
                }`}
              >
                🏪 Escaparate {enEscaparate}/{totalProductos}
              </button>

              {MOSTRAR_ECHOTIK && (
              <button
                type="button"
                onClick={runBuscarUrls}
                disabled={buscarUrls.isPending || !pendientesUrl}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-emerald-500/60 px-3 py-2 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/10 disabled:opacity-50"
              >
                {buscarUrls.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                    <span className="truncate">Buscando…</span>
                  </>
                ) : (
                  <span className="truncate">
                    {pendientesUrl ? `Enlaces (${pendientesUrl} llamadas)` : "Enlaces al día"}
                  </span>
                )}
              </button>
              )}
            </div>
            {/* Guion para todos los productos de la carpeta a la vez, en vez de
                pulsarlo en cada tarjeta. Necesitan tener textos primero. */}
            <button
              type="button"
              onClick={() => void generarTodosGuiones()}
              disabled={generandoGuiones || !sinGuion}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/60 px-3 py-2 text-xs font-semibold text-violet-500 transition hover:bg-violet-500/10 disabled:opacity-50"
            >
              {generandoGuiones ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  <span className="truncate">Escribiendo guiones {guionProgress}…</span>
                </>
              ) : (
                <>
                  <Sparkles className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">
                    {sinGuion
                      ? `Escribir todos los guiones (${sinGuion})`
                      : `Guiones al día (${conGuion}/${totalProductos})`}
                  </span>
                </>
              )}
            </button>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline gap-1.5">
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
                2
              </span>
              <p className="text-[11px] font-semibold">Generar fuera</p>
              <p className="truncate text-[10px] text-muted-foreground">copia el prompt y las fotos</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => copyText("Prompt imagen", prompts.data?.imagen)}
                disabled={!prompts.data?.imagen}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
              >
                <ClipboardCopy className="h-3.5 w-3.5" /> Prompt imagen
              </button>
              <button
                type="button"
                onClick={() => copyText("Prompt vídeo", prompts.data?.video)}
                disabled={!prompts.data?.video}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
              >
                <Clapperboard className="h-3.5 w-3.5" /> Prompt vídeo
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline gap-1.5">
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
                3
              </span>
              <p className="text-[11px] font-semibold">Descargar</p>
              <p className="truncate text-[10px] text-muted-foreground">fotos para generar · vídeos ya montados</p>
            </div>
            {/* Una fila por cosa: el total y los dos flujos al lado (ver
                POV BOF), para bajar solo lo que toca. */}
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
          </div>

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
                {itemsVisibles.length}/{items.length}
              </span>
            </label>
          )}

          {itemsVisibles.length > 0 && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {itemsVisibles.map((p) => (
                <ProductoCard
                  key={p.producto}
                  source={activaSource}
                  folder={folder}
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
      <p className="text-xs font-semibold sm:text-sm">➕ Añadir un producto mío</p>
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
    </section>
  );
}



function HashtagsPanel() {
  const tagsQuery = useHashtags();
  const guardar = useGuardarHashtags();
  const [nuevo, setNuevo] = useState("");
  const tags = tagsQuery.data ?? [];

  function aplicar(siguientes: string[]) {
    guardar.mutate(siguientes, { onError: (e) => toast.error(err(e)) });
  }

  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <p className="text-xs font-semibold">🏷️ Hashtags del caption</p>
      <p className="text-[11px] text-muted-foreground">
        Se pegan al final de TODOS los captions al copiarlos. Cámbialos según la campaña.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px]"
          >
            {t}
            <button
              type="button"
              aria-label={`Quitar ${t}`}
              onClick={() => aplicar(tags.filter((x) => x !== t))}
              className="text-muted-foreground transition hover:text-destructive"
            >
              ×
            </button>
          </span>
        ))}
        {tags.length === 0 && !tagsQuery.isLoading && (
          <span className="text-[11px] text-muted-foreground">Ninguno.</span>
        )}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const t = nuevo.trim();
          if (!t) return;
          aplicar([...tags, t]);
          setNuevo("");
        }}
        className="flex gap-1.5"
      >
        <input
          value={nuevo}
          onChange={(e) => setNuevo(e.target.value)}
          placeholder="#rebajasdeverano"
          className="min-w-0 flex-1 rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs"
        />
        <button
          type="submit"
          disabled={guardar.isPending || !nuevo.trim()}
          className="rounded-md border border-border/60 px-3 py-1.5 text-xs font-medium transition hover:border-foreground/30 disabled:opacity-50"
        >
          Añadir
        </button>
      </form>
    </section>
  );
}

function diaCorto(ts: number | null | undefined): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}

function EchoTikPanel() {
  const estado = useEchoTikEstado();
  const guardar = useGuardarEchoTik();
  const cuentas = useEchoTikCuentas();
  const guardarCuenta = useGuardarCuentaEchoTik();
  const activarCuenta = useActivarCuentaEchoTik();
  const borrarCuenta = useBorrarCuentaEchoTik();
  const [abierto, setAbierto] = useState(false);
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");

  const puedeGuardar = usuario.trim().length >= 4 && password.trim().length >= 8;
  const listaCuentas = cuentas.data ?? [];
  const libres = listaCuentas.filter((c) => c.disponible).length;
  const d = estado.data;

  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="text-sm font-semibold">🔑 API de EchoTik (enlaces)</span>
        <span className="text-[11px] text-muted-foreground">
          {d
            ? d.configurado
              ? `${d.usuario_mascara} · ${d.origen === "guardadas" ? "guardadas aquí" : "del .env"}`
              : "sin configurar"
            : "…"}
        </span>
      </button>

      {d?.mensaje && !guardar.isPending && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-500">
          {d.mensaje}
        </p>
      )}

      {abierto && (
        <div className="space-y-2">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Se aplican al instante, sin desplegar nada. Al guardar se gasta UNA llamada
            comprobando que funcionan; si no funcionan, no se guardan.
          </p>
          <input
            type="text"
            inputMode="numeric"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            placeholder="usuario (el número largo)"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="contraseña"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
          />
          <button
            type="button"
            disabled={guardar.isPending || !puedeGuardar}
            onClick={() =>
              guardar.mutate(
                { usuario: usuario.trim(), password: password.trim(), probar: true },
                {
                  onSuccess: (r) => {
                    if (r.ok) {
                      toast.success(r.mensaje);
                      setUsuario("");
                      setPassword("");
                      setAbierto(false);
                    } else {
                      toast.error(r.mensaje);
                    }
                  },
                  onError: (e) => toast.error(err(e)),
                },
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
          >
            {guardar.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Comprobando…
              </>
            ) : (
              "Usar ahora (gasta 1 llamada)"
            )}
          </button>
          <button
            type="button"
            disabled={guardarCuenta.isPending || !puedeGuardar}
            onClick={() =>
              guardarCuenta.mutate(
                { usuario: usuario.trim(), password: password.trim(), nota: "" },
                {
                  onSuccess: (r) => {
                    toast.success(r.mensaje || "Cuenta guardada");
                    setUsuario("");
                    setPassword("");
                  },
                  onError: (e) => toast.error(err(e)),
                },
              )
            }
            className="w-full rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
          >
            Guardar de respaldo (sin usarla, 0 llamadas)
          </button>
        </div>
      )}

      {listaCuentas.length > 0 && (
        <div className="space-y-1.5 border-t border-border/60 pt-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-muted-foreground">
              Cuentas guardadas · {libres} con llamadas libres
            </p>
            {!abierto && (
              <button
                type="button"
                onClick={() => setAbierto(true)}
                className="shrink-0 rounded-md border border-border/60 px-2 py-1 text-[11px] transition hover:border-emerald-500 hover:text-emerald-500"
              >
                + Añadir cuenta
              </button>
            )}
          </div>
          {listaCuentas.map((c) => {
            const renueva = diaCorto(c.renueva_at);
            return (
              <div
                key={c.usuario}
                className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 ${
                  c.activa ? "border-emerald-500/60 bg-emerald-500/10" : "border-border/60"
                }`}
              >
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    c.disponible ? "bg-emerald-500" : "bg-amber-500"
                  }`}
                  title={c.disponible ? "Con llamadas" : "Agotada este ciclo"}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">
                    {c.usuario_mascara}
                    {c.activa && (
                      <span className="ml-1 text-[10px] font-normal text-emerald-500">en uso</span>
                    )}
                  </p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {c.primer_uso_at
                      ? `${c.llamadas}/100 · ${
                          c.disponible ? `renueva ~${renueva}` : `libre ~${renueva}`
                        }`
                      : "sin estrenar"}
                  </p>
                </div>
                {!c.activa && (
                  <button
                    type="button"
                    disabled={activarCuenta.isPending}
                    onClick={() =>
                      activarCuenta.mutate(c.usuario, {
                        onSuccess: (r) => toast.success(r.mensaje || "Activada"),
                        onError: (e) => toast.error(err(e)),
                      })
                    }
                    className="shrink-0 rounded-md border border-border/60 px-2 py-1 text-[11px] transition hover:border-emerald-500 hover:text-emerald-500 disabled:opacity-50"
                  >
                    Usar
                  </button>
                )}
                <button
                  type="button"
                  disabled={borrarCuenta.isPending}
                  onClick={() =>
                    borrarCuenta.mutate(c.usuario, {
                      onSuccess: () => toast.success("Cuenta borrada"),
                      onError: (e) => toast.error(err(e)),
                    })
                  }
                  className="shrink-0 rounded-md p-1 text-muted-foreground transition hover:text-destructive disabled:opacity-50"
                  aria-label={`Borrar ${c.usuario_mascara}`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

/** El escaparate del Largo escribe en SU progreso (endpoint propio). */
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
  const setEstado = useSetEstadoLargo();
  const buscarUrl = useBuscarProductoUrl();
  const hashtags = useHashtags().data ?? [];
  const refs = { 1: useRef<HTMLInputElement>(null), 2: useRef<HTMLInputElement>(null) };

  const [verFoto, setVerFoto] = useState(false);
  const [verTools, setVerTools] = useState(false);
  const [verGuion, setVerGuion] = useState(false);
  // El guion guardado se escribió en el otro modo (con o sin la frase de
  // plazos). No es un error: pasa con todo lo escrito antes de que existieran
  // los plazos y cada vez que se corrige un precio.
  const guionDesfasado = Boolean(p.guion) && p.modo_plazos !== p.guion_plazos;
  const [verVideo, setVerVideo] = useState(false);
  // Progreso POR SLOT (null = ese clip no se está subiendo). Así se puede subir
  // el clip 2 mientras el 1 va por la mitad, y cada tarjeta es independiente de
  // las demás (subir clips de varios productos a la vez).
  const [pcts, setPcts] = useState<{ 1: number | null; 2: number | null }>({
    1: null,
    2: null,
  });
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
  function subirClip(slot: 1 | 2, file: File) {
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
    <div className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
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
                <span className="text-muted-foreground">precio sin detectar</span>
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

      {/* Los DOS clips. No se encola hasta tener los dos y el guion. */}
      <div className="grid grid-cols-2 gap-1.5">
        {([1, 2] as const).map((slot) => {
          const puesto = slot === 1 ? p.clip1 : p.clip2;
          const pctSlot = pcts[slot];
          const subiendoEste = pctSlot !== null;
          return (
            <label
              key={slot}
              className={`flex cursor-pointer items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-[11px] font-medium transition ${
                puesto
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 hover:border-violet-500/60"
              } ${!p.guion || subiendoEste ? "pointer-events-none opacity-60" : ""}`}
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

      {/* Estado individual */}
      <div className="flex gap-1.5">
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
