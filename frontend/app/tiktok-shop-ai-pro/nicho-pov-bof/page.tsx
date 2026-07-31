"use client";

import {
  Check,
  Clapperboard,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Copy,
  Download,
  HardDrive,
  LayoutGrid,
  Link2 as LinkIcon,
  Loader2,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  Target,
  Upload,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
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
  useSetEstado,
  useSources,
  useVendidos,
} from "@/lib/queries/nichoPovBof";
import { VideoModal } from "@/components/ui/video-modal";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type {
  BackupCheckResponse,
  ProductoItem,
  VideoUploadResponse,
} from "@/lib/types/nichoPovBof";

export default function NichoPovBofPage() {
  const [source, setSource] = useState("aleatorios_1");
  const [showAll, setShowAll] = useState(false);
  // Las fotos en crudo van colapsadas: ocupaban toda la pantalla.
  const [showFotos, setShowFotos] = useState(false);
  // Carpeta elegida a mano. Si es null se usa la "current" del backend
  // (la primera sin completar).
  const [picked, setPicked] = useState<string | null>(null);

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
  const vendidos = useVendidos(source);
  const [downloadingPhotos, setDownloadingPhotos] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState("");

  function copyText(label: string, text: string | undefined) {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado`);
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
    <div className="container mx-auto space-y-5 p-4 sm:p-6 md:p-10">
      <header className="flex items-center gap-3">
        <Target className="h-6 w-6 shrink-0 text-emerald-500" />
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold sm:text-2xl">Nicho POV BOF</h1>
          <p className="truncate text-xs text-muted-foreground sm:text-sm">
            Productos del Drive compartido · solo lectura
          </p>
        </div>
      </header>

      {/* Fuente */}
      <section className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => switchSource(s.slug)}
              className={`truncate rounded-lg border px-3 py-2 text-xs transition sm:text-sm ${
                source === s.slug
                  ? "border-emerald-500 bg-emerald-500/10 font-semibold text-emerald-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </section>

      {/* Progreso */}
      <section className="rounded-xl border border-border/60 bg-card p-3">
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
      </section>

      {/* Credenciales de EchoTik. El plan de pruebas caduca cada pocos días y
          antes había que editar el .env del VPS y recrear el container, que
          solo puede hacer quien tiene SSH. Aquí se cambian en caliente. */}
      <EchoTikPanel />
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
                    href={buildPhotoUrl(source, folder, p.id)}
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

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
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
                  <Download className="h-3.5 w-3.5" /> Descargar fotos limpias
                </>
              )}
            </button>
            <button
              type="button"
              onClick={runExtraerTextos}
              disabled={extraerTextos.isPending}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-purple-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-purple-600 disabled:opacity-50"
            >
              {extraerTextos.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Extrayendo… (~1 min)
                </>
              ) : (
                <>
                  <Sparkles className="h-3.5 w-3.5" /> Obtener textos
                </>
              )}
            </button>
            <button
              type="button"
              onClick={runBuscarUrls}
              disabled={buscarUrls.isPending || !pendientesUrl}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-emerald-500/60 px-3 py-2 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/10 disabled:opacity-50"
            >
              {buscarUrls.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando enlaces…
                </>
              ) : (
                <>
                  <LinkIcon className="h-3.5 w-3.5" />
                  {pendientesUrl
                    ? `Buscar enlaces (${pendientesUrl} llamadas)`
                    : "Enlaces al día"}
                </>
              )}
            </button>
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
                <ProductoCard key={p.producto} source={source} folder={folder} producto={p} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Productos que vendieron */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <ShoppingBag className="h-4 w-4 shrink-0 text-amber-500" />
          <p className="text-sm font-semibold">Productos que vendieron</p>
        </div>

        {vendidos.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
          </div>
        )}

        {vendidos.data && vendidos.data.length === 0 && (
          <p className="text-xs text-muted-foreground">Todavía ninguno.</p>
        )}

        {vendidos.data && vendidos.data.length > 0 && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
            {vendidos.data.map((v) => (
              <div
                key={`${v.folder}-${v.producto}`}
                className="flex items-center gap-2 rounded-lg border border-border/60 p-1.5"
              >
                {v.clean_photo_id ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={buildPhotoUrl(source, v.folder, v.clean_photo_id)}
                    alt={v.producto}
                    loading="lazy"
                    className="h-10 w-10 shrink-0 rounded object-cover"
                  />
                ) : (
                  <div className="h-10 w-10 shrink-0 rounded bg-muted" />
                )}
                <p className="min-w-0 flex-1 truncate text-[11px] font-medium">
                  {v.titulo || v.producto}
                </p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
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
function FotoModal({
  open,
  onOpenChange,
  producto,
  source,
  folder,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  producto: ProductoItem;
  source: string;
  folder: string;
}) {
  const [cual, setCual] = useState<"limpia" | "titulo">("limpia");
  const id =
    cual === "limpia" ? producto.clean_photo_id : producto.titled_photo_id;

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={() => onOpenChange(false)}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 overflow-y-auto rounded-lg border bg-card p-3"
      >
        <div className="flex items-start justify-between gap-2">
          <p className="min-w-0 flex-1 truncate text-sm font-semibold">
            Producto {producto.producto}
          </p>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Cerrar"
            className="rounded-sm p-1 text-muted-foreground hover:text-foreground"
          >
            ✕
          </button>
        </div>

        {producto.titled_photo_id && (
          <div className="grid grid-cols-2 gap-1">
            {(["limpia", "titulo"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setCual(k)}
                className={`rounded-md border px-2 py-1 text-[11px] transition ${
                  cual === k
                    ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                    : "border-border/60 text-muted-foreground"
                }`}
              >
                {k === "limpia" ? "Foto del producto" : "Captura con título"}
              </button>
            ))}
          </div>
        )}

        {id ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={buildPhotoUrl(source, folder, id)}
            alt={`Producto ${producto.producto}`}
            className="w-full rounded-md border border-border/60 object-contain"
          />
        ) : (
          <p className="py-8 text-center text-xs text-muted-foreground">
            No hay esta foto en Drive.
          </p>
        )}

        {producto.clean_photo_id && (
          <a
            href={buildCleanPhotoDownloadUrl(source, folder, producto.producto)}
            className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] font-medium transition hover:border-foreground/30"
          >
            <Download className="h-3.5 w-3.5" /> Descargar la foto del producto
          </a>
        )}
      </div>
    </div>
  );
}

function CopyChip({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        toast.success("Copiado");
      }}
      title={`Copiar: ${label}`}
      className="inline-flex max-w-full items-center gap-1 truncate rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40 hover:text-foreground"
    >
      <Copy className="h-3 w-3 shrink-0" />
      <span className="truncate">{label}</span>
    </button>
  );
}


/** Credenciales de EchoTik, cambiables sin redespliegue. */
function EchoTikPanel() {
  const estado = useEchoTikEstado();
  const guardar = useGuardarEchoTik();
  const [abierto, setAbierto] = useState(false);
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");

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
            disabled={guardar.isPending || usuario.trim().length < 4 || password.trim().length < 8}
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
              "Guardar y comprobar (1 llamada)"
            )}
          </button>
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
}: {
  source: string;
  folder: string;
  producto: ProductoItem;
}) {
  const setEstado = useSetEstado();
  const buscarUrl = useBuscarProductoUrl();
  // La búsqueda puede terminar bien y aun así no traer URL (EchoTik no
  // indexa el producto). Sin distinguirlo, el botón se quedaba igual que
  // antes de pulsarlo y el operador volvía a gastar cuota sin saberlo.
  const urlNoEncontrada = buscarUrl.isSuccess && !producto.product_url;
  const [uploaded, setUploaded] = useState(producto.uploaded);
  const [sold, setSold] = useState(producto.sold);
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
  }, [producto.uploaded, producto.sold]);

  const pushEstado = (patch: { uploaded?: boolean; sold?: boolean }) => {
    setEstado.mutate(
      { source, folder, producto: producto.producto, ...patch },
      { onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)) },
    );
  };

  const toggleUploaded = () => {
    const v = !uploaded;
    setUploaded(v);
    pushEstado({ uploaded: v });
  };

  const toggleSold = () => {
    const v = !sold;
    setSold(v);
    // Vender implica haberlo subido — mismo criterio que OutcomeBar del
    // calendario: evita el estado imposible "vendió pero no subido".
    if (v && !uploaded) setUploaded(true);
    pushEstado(v && !uploaded ? { sold: v, uploaded: true } : { sold: v });
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
              src={buildPhotoUrl(source, folder, producto.clean_photo_id)}
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
        <CopyChip label="🏪 Tienda" text={producto.tienda ?? ""} />
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
        producto={producto}
        source={source}
        folder={folder}
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
      {producto.product_url ? (
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
      )}

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
          <a
            href={buildVideoUrl(source, folder, producto.producto, producto.video_listo_at ?? 0, true)}
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
