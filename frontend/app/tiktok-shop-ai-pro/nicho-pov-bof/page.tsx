"use client";

import {
  Check,
  Clapperboard,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Download,
  HardDrive,
  LayoutGrid,
  Link2 as LinkIcon,
  Loader2,
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
  useCrearMiProducto,
  nichoPovBofKeys,
  buildCleanPhotoDownloadUrl,
  buildVideoUrl,
  buildPhotoUrl,
  useBackupCheck,
  useBackupSync,
  useExtraerTextos,
  useFolders,
  useMarkCompleted,
  usePhotos,
  usePrompts,
  useProductos,
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
  useSources,
  useVendidos,
  useSumarUnidades,
  useBuscarProductos,
  ANCHO_CHIP,
  ANCHO_VISOR,
} from "@/lib/queries/nichoPovBof";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { VideoModal } from "@/components/ui/video-modal";
import { portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type {
  BackupCheckResponse,
  ProductoBuscado,
  ProductoItem,
  VideoUploadResponse,
} from "@/lib/types/nichoPovBof";

/** EchoTik apagado a petición del operador: su cuota gratis no da para el
 *  volumen diario y de momento no lo usa. Poniéndolo a `true` vuelven el panel
 *  de credenciales y los botones de buscar la ficha del producto. */
const MOSTRAR_ECHOTIK = false;

export default function NichoPovBofPage() {
  const [source, setSource] = useEstadoRecordado("povbof:fuente", "aleatorios_1");
  const [showAll, setShowAll] = useState(false);
  // Las fotos en crudo van colapsadas: ocupaban toda la pantalla.
  const [showFotos, setShowFotos] = useState(false);
  // Carpeta elegida a mano. Si es null se usa la "current" del backend
  // (la primera sin completar).
  const [picked, setPicked] = useEstadoRecordado<string | null>("povbof:carpeta", null);
  const [verVendidos, setVerVendidos] = useState(false);
  const [verEscaparate, setVerEscaparate] = useState(false);

  const sources = useSources();
  const folders = useFolders(source);
  const markCompleted = useMarkCompleted(source);

  const [backup, setBackup] = useState<BackupCheckResponse | null>(null);
  const backupCheck = useBackupCheck();
  const backupSync = useBackupSync();
  const openQueue = useDrawerStore((s) => s.openQueue);

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
      onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
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
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  const data = folders.data;
  const folder = picked ?? data?.current ?? null;
  const photos = usePhotos(source, folder);

  // --- Fase 2: automatización de vídeos ---
  const prompts = usePrompts();
  const productos = useProductos(source, folder);
  const extraerTextos = useExtraerTextos();
  const buscarUrls = useBuscarUrlsCarpeta();
  // SIN fuente: el ranking es global y el listado que se abre también, así
  // que el número del botón tiene que contar lo mismo. Con `source` decía 2
  // (solo la fuente abierta) y al abrirlo salían 43.
  const vendidos = useVendidos("");
  const totalVendidos = (vendidos.data ?? []).reduce(
    (n, v) => n + (v.unidades || 1), 0,
  );
  const [downloadingPhotos, setDownloadingPhotos] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState("");
  const [downloadingVideos, setDownloadingVideos] = useState(false);
  const [videoProgress, setVideoProgress] = useState("");
  const totalProductos = productos.data?.length ?? 0;
  const conVideo = (productos.data ?? []).filter((p) => p.video_path).length;
  const conFoto = (productos.data ?? []).filter((p) => p.clean_photo_id).length;
  const conTexto = (productos.data ?? []).filter((p) => p.titulo).length;
  const subidos = (productos.data ?? []).filter((p) => p.uploaded).length;
  const enEscaparate = (productos.data ?? []).filter((p) => p.en_escaparate).length;
  // Meter el producto en el escaparate es el paso más lento del día y no se
  // puede automatizar (ver EscaparateModal), así que el pendiente se enseña
  // arriba, en el botón, sin tener que abrir nada.
  const pendientesEscaparate = (productos.data ?? []).filter(
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
  async function downloadVideos() {
    if (!folder || !productos.data?.length) return;
    const items = productos.data.filter((p) => p.video_path);
    if (!items.length) {
      toast.error("Ningún producto tiene vídeo montado todavía");
      return;
    }
    setDownloadingVideos(true);
    try {
      for (const [i, p] of items.entries()) {
        setVideoProgress(`${i + 1}/${items.length}`);
        const a = document.createElement("a");
        a.href = buildVideoUrl(source, folder, p.producto, p.video_listo_at ?? 0, true);
        a.download = `${folder}_${p.producto}.mp4`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
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

  async function downloadCleanPhotos() {
    if (!folder || !productos.data?.length) return;
    const items = productos.data.filter((p) => p.clean_photo_id);
    if (!items.length) {
      toast.error("No hay fotos limpias en esta carpeta");
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
        a.href = buildCleanPhotoDownloadUrl(source, folder, p.producto);
        a.download = `${folder}_${p.producto}`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
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
    <div className="container mx-auto space-y-3 p-3 sm:space-y-4 sm:p-6 md:p-10">
      {/* Portada del módulo 6 del curso — la misma que abre los demás nichos,
          para que todos los submenús se reconozcan de un vistazo. Hace también
          de título: por eso no hay un <h1> debajo comiéndose otra fila. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={portadaDe("nicho-pov-bof")}
        alt="Creación de Nicho POV BOF"
        className="h-auto w-full rounded-xl border border-border/60"
      />

      {/* Fuente + progreso en UNA tarjeta. Iban en dos y el borde, el padding
          y el hueco entre ambas costaban ~60px de scroll en móvil para dos
          líneas de contenido. */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        {/* Las tres fuentes en una sola fila: son tres y caben, y así no se
            come una línea entera de pantalla en el móvil. */}
        <div className="grid grid-cols-3 gap-1.5">
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
            </button>
          ))}
        </div>

        {/* Solo en la fuente propia: en las del curso no hay nada que subir. */}
        {source === "mis_productos" && <AltaMiProducto />}


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
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className={`flex items-center gap-1 rounded-md border px-2 py-1.5 text-[11px] transition sm:text-xs ${
                showAll
                  ? "border-emerald-500 text-emerald-500"
                  : "border-border/60 text-muted-foreground hover:text-foreground"
              }`}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Ver todas
            </button>
          </div>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>

        {/* Lo que ya vendió es lo que dice qué buscar, así que va ARRIBA y a
            un toque. Antes vivía al final de la página, detrás de todo. */}
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
        </button>
        {/* El escaparate es el cuello de botella real del día: no se puede
            automatizar (EchoTik da con la ficha 1 de cada 4 veces y su cuota
            gratis no llega), así que al menos se abre de un toque desde
            arriba, igual que los vendidos. */}
      </section>

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

      {/* Todo esto se toca de uvas a peras (la clave de EchoTik cuando caduca,
          los hashtags al cambiar de campaña, la copia si sospechas que han
          borrado algo). El trabajo de todos los días es la carpeta de abajo,
          así que va plegado: si no, son ~700px de scroll antes de empezar. */}
      <CollapsibleCard
        title="⚙️ Configuración"
        subtitle="EchoTik · hashtags · copia de seguridad — el Drive de origen es de solo lectura"
      >
        <div className="space-y-3">
          {MOSTRAR_ECHOTIK && <EchoTikPanel />}
          <HashtagsPanel />

          {/* Backup del Drive de origen */}
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
                      <span className="font-semibold text-red-500">-{backup.n_deleted}</span> borrados en origen
                    </p>
                    <p className="text-muted-foreground">
                      {Math.round(backup.change_ratio * 100)}% del archivo ({backup.n_total_source} ficheros).{" "}
                      {backup.would_be_full
                        ? "Se hará copia COMPLETA nueva."
                        : "Se copiará solo la diferencia."}
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

      {/* Rejilla compacta de todas las carpetas (estilo calendario) */}
      {showAll && data && (
        <section className="rounded-xl border border-border/60 bg-card p-3">
          <div className="grid grid-cols-4 gap-1 sm:grid-cols-6 md:grid-cols-8">
            {data.items.map((f, i) => {
              const isSel = f.name === folder;
              return (
                <button
                  key={f.id || f.name}
                  type="button"
                  onClick={() => setPicked(f.name)}
                  title={f.name}
                  className={`flex aspect-square flex-col items-center justify-center rounded-lg border p-0.5 text-xs transition ${
                    f.completed
                      ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-500"
                      : "border-border/60 text-muted-foreground hover:border-foreground/30"
                  } ${isSel ? "ring-2 ring-emerald-500" : ""}`}
                >
                  <span className="font-semibold">{i + 1}</span>
                  {f.completed && <Check className="h-3 w-3" />}
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* Carpeta actual */}
      {data && !folder && (
        <p className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 text-center text-sm text-emerald-500">
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
        </section>
      )}


      {/* Fase 2 — automatización de vídeos por producto */}
      {data && folder && (
        <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 shrink-0 text-purple-500" />
            <p className="text-sm font-semibold">Automatización de vídeos</p>
          </div>

          {/* En el orden en que se usan: primero se sacan los textos,
              luego se copian los prompts para generar fuera, y al final
              se descarga. Antes estaban mezclados y no se sabía por dónde
              empezar en una carpeta nueva. */}
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
              className="flex items-center justify-center gap-1.5 rounded-lg bg-purple-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-purple-600 disabled:opacity-50"
            >
              {extraerTextos.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  <span className="truncate">Extrayendo…</span>
                </>
              ) : (
                <>
                  <Sparkles className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">Textos ({conTexto}/{totalProductos})</span>
                </>
              )}
            </button>

            {/* Cuántos productos de ESTA carpeta has publicado ya. Que la
                carpeta esté "completada" no significa que estén todos subidos:
                puede haber productos sin stock o descartados. */}
            <div
              className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold ${
                subidos === totalProductos && totalProductos > 0
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 text-muted-foreground"
              }`}
            >
              📤 Subidos {subidos}/{totalProductos}
            </div>

            {/* Junto a "Subidos" para poder comparar de un vistazo: cuántos
                están en el escaparate y cuántos ya publicados. */}
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

            {MOSTRAR_ECHOTIK && (<button
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
                <>
                  <LinkIcon className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">
                    {pendientesUrl
                      ? `Enlaces (${pendientesUrl} llamadas)`
                      : "Enlaces al día"}
                  </span>
                </>
              )}
            </button>)}
            </div>
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
            <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => void downloadCleanPhotos()}
              disabled={downloadingPhotos || !productos.data?.length}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
            >
              {downloadingPhotos ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Descargando {downloadProgress}
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">Fotos ({conFoto}/{totalProductos})</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => void downloadVideos()}
              disabled={downloadingVideos || !conVideo}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
            >
              {downloadingVideos ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Descargando {videoProgress}
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">
                    Vídeos ({conVideo}/{totalProductos})
                  </span>
                </>
              )}
            </button>
            </div>
          </div>

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

          {productos.data && productos.data.length > 0 && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {productos.data.map((p) => (
                <ProductoCard
                  key={p.producto}
                  source={source}
                  folder={folder}
                  producto={p}
                  carpetaHecha={Boolean(productos.data?.some((x) => x.titulo))}
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
function AltaMiProducto() {
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
      <p className="text-xs font-semibold sm:text-sm">➕ Añadir un producto mío</p>
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
    </section>
  );
}




/** Botón compacto: copia el texto al portapapeles sin mostrarlo. Mismo
 *  patrón que `CopyChip` de `calendar/page.tsx:1044`. */
function HashtagsPanel() {
  const tagsQuery = useHashtags();
  const guardar = useGuardarHashtags();
  const [nuevo, setNuevo] = useState("");
  const tags = tagsQuery.data ?? [];

  function aplicar(siguientes: string[]) {
    guardar.mutate(siguientes, {
      onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
    });
  }

  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <p className="text-xs font-semibold">🏷️ Hashtags del caption</p>
      <p className="text-[11px] text-muted-foreground">
        Se pegan al final de TODOS los captions al copiarlos. Cámbialos según
        la campaña.
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

/** Ver la foto de un producto en grande y descargarla suelta.
 *
 *  Muestra TAMBIÉN la captura con título cuando existe: es la forma rápida de
 *  cazar un emparejado raro (pasó con una carpeta donde la foto limpia de un
 *  producto estaba guardada con el número de otro). */


/** Fecha corta ("28 ago"), o "" si no hay. Las horas no importan aquí: lo que
 *  se mira es si ya pasó el mes. */
function diaCorto(ts: number | null | undefined): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
  });
}

/** Credenciales de EchoTik, cambiables sin redespliegue. */
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
  // Cuenta también la que está en uso: si le quedan llamadas, es una cuenta
  // con llamadas libres. Excluirla decía "0 con llamadas libres" con la única
  // cuenta en verde justo debajo.
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
            Se aplican al instante, sin desplegar nada. Al guardar se gasta UNA
            llamada comprobando que funcionan; si no funcionan, no se guardan.
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
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : String(e)),
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

          {/* Guardar SIN activar: para ir apuntando cuentas de respaldo según
              se van creando, sin tocar la que está funcionando ni gastarle
              una llamada a la nueva. */}
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
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : String(e)),
                },
              )
            }
            className="w-full rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
          >
            Guardar de respaldo (sin usarla, 0 llamadas)
          </button>
        </div>
      )}

      {/* Banco de cuentas. El plan gratis da 100 llamadas AL MES: una cuenta
          seca no se tira, se aparta y se vuelve a ella cuando le renueva. */}
      {listaCuentas.length > 0 && (
        <div className="space-y-1.5 border-t border-border/60 pt-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-muted-foreground">
              Cuentas guardadas · {libres} con llamadas libres
            </p>
            {/* Añadir estaba escondido detrás del título del panel y no se
                encontraba. Aquí, pegado a la lista, es donde se busca. */}
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
                  c.activa
                    ? "border-emerald-500/60 bg-emerald-500/10"
                    : "border-border/60"
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
                      <span className="ml-1 text-[10px] font-normal text-emerald-500">
                        en uso
                      </span>
                    )}
                  </p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {c.primer_uso_at
                      ? `${c.llamadas}/100 · ${
                          c.disponible
                            ? `renueva ~${renueva}`
                            : `libre ~${renueva}`
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
                        onError: (e) =>
                          toast.error(e instanceof ApiError ? e.message : String(e)),
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
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
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
}: {
  source: string;
  folder: string;
  producto: ProductoItem;
  /** La carpeta ya tiene textos en OTROS productos. Sirve para marcar al que
   *  se quedó sin ellos: es un producto que apareció tarde (antes se perdían
   *  los de fotos sin extensión y los fundidos bajo un mismo número), y sin
   *  marca pasa desapercibido entre nueve que están completos. */
  carpetaHecha?: boolean;
}) {
  const setEstado = useSetEstado();
  const buscarUrl = useBuscarProductoUrl();
  // La búsqueda puede terminar bien y aun así no traer URL (EchoTik no
  // indexa el producto). Sin distinguirlo, el botón se quedaba igual que
  // antes de pulsarlo y el operador volvía a gastar cuota sin saberlo.
  const urlNoEncontrada = buscarUrl.isSuccess && !producto.product_url;
  const [uploaded, setUploaded] = useState(producto.uploaded);
  const [sold, setSold] = useState(producto.sold);
  const [enEscaparate, setEnEscaparate] = useState(producto.en_escaparate);
  // Arranca con la voz que encaja con el producto (mujer en cosmética y
  // pelo, hombre en el resto). El operador la cambia con un clic si falla.
  const [sexo, setSexo] = useState<"hombre" | "mujer">(
    producto.sexo_sugerido === "mujer" ? "mujer" : "hombre",
  );
  // Herramientas de edición, elegibles por separado. Todas marcadas por
  // defecto = el montaje completo; desmarcarlas todas deja el vídeo limpio
  // (solo la voz). Así se puede pedir, p. ej., solo el nombre del producto
  // o solo la flecha.
  const [tools, setTools] = useState<Record<ToolKey, boolean>>({
    gancho: true, titulo: true, cta: true, flecha: true,
  });
  const [uploading, setUploading] = useState(false);
  const [pct, setPct] = useState(0);
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);
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
      { onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)) },
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

  function uploadVideo(file: File) {
    setUploading(true);
    setPct(0);
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
    // XHR (no fetch) para tener progreso real de subida — mismo patrón que
    // `uploadVideo()` en calendar/page.tsx:634.
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBase}/api/v1/nicho-pov-bof/video/upload`);
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setUploading(false);
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
      setUploading(false);
      toast.error("Error de red al subir");
    };
    xhr.send(fd);
  }

  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
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
        </div>
      </div>

      {/* Copiar textos extraídos — solo se muestran los que tengan valor */}
      <div className="flex flex-wrap gap-1">
        <CopyChip label="📝 Título" text={producto.titulo ?? ""} />
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
        {/* Gancho y CTA también copiables: son los textos que se pegan a mano
            cuando se prefiere montar el vídeo en CapCut en vez de aquí. */}
        <CopyChip label="🎣 Gancho" text={producto.gancho ?? ""} />
        <CopyChip label="👉 CTA" text={producto.cta ?? ""} />
        {producto.product_url && <CopyChip label="🔗 Enlace" text={producto.product_url} />}
        {producto.clean_photo_id && (
          <>
            <button
              type="button"
              onClick={() => setVerFoto(true)}
              className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40 hover:text-foreground"
            >
              🔍 Ver foto
            </button>
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
        {(["hombre", "mujer"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSexo(s)}
            className={`flex-1 rounded px-1.5 py-1 transition ${
              sexo === s ? "bg-emerald-500 font-semibold text-white" : "text-muted-foreground"
            }`}
          >
            {s === "hombre" ? "👨 Hombre" : "👩 Mujer"}
          </button>
        ))}
      </div>

      {/* Cada herramienta por separado. Todas marcadas = montaje completo;
          ninguna = vídeo limpio (solo la voz, y sin marca si es Veo3). */}
      <div className="space-y-1.5 rounded-md border border-border/60 p-2">
        <p className="text-[10px] font-medium text-muted-foreground">
          Qué añadir al vídeo
        </p>
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

      <div className="flex gap-1.5">
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
