"use client";

import { useEffect, useState } from "react";
import { AlertCircle, ArrowUp, ChevronUp, ChevronDown, Check, Clock, Coins, Download, ExternalLink, FileText, Film, Loader2, Play, ShoppingBag, Timer, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
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
import {
  useCancelJob,
  useDeleteJobWithFile,
  useJobSummary,
  useRemoveJob,
  useReorderJob,
  useRescheduleJob,
} from "@/lib/queries/queue";
import { useMe } from "@/lib/queries/auth";
import { useQueueStore } from "@/lib/stores/queueStore";
import { JobDetailDialog } from "./JobDetailDialog";
import { JobVideoDialog } from "./JobVideoDialog";
import { SchedulePicker, formatScheduledFor } from "./SchedulePicker";
import {
  describeJobParams,
  MODE_ICON,
  MODE_TO_PROGRAM,
  PROGRAM_BORDER,
  PROGRAM_ICON,
  PROGRAM_LABEL,
  SUBMODULE_LABEL,
  type Program,
} from "@/lib/queue-meta";
import type { ActiveJob, JobStatus } from "@/lib/types/queue";
import { colorDeUsuario, nombreDueno } from "@/lib/usuarios-color";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<JobStatus, string> = {
  pending: "En cola",
  running: "Procesando",
  completed: "Completado",
  failed: "Fallado",
  cancelled: "Cancelado",
};

/** Sub-estado derivado del `progress_label`. Lo usamos cuando el job
 *  está RUNNING pero realmente está esperando un servicio externo
 *  (Atlas Cloud) — el user lo distingue de "procesando activamente". */
function detectSubState(label: string | undefined): "waiting_atlas" | null {
  if (!label) return null;
  const lower = label.toLowerCase();
  // Heartbeat de Atlas: "⏳ Clip 1: 12m05s (status=processing)…"
  // o "🎥 Atlas Cloud renderizando clips…"
  if (lower.includes("atlas") || /\(status=(processing|pending|queued)/.test(lower)) {
    return "waiting_atlas";
  }
  return null;
}

/** Devuelve la clase Tailwind del badge según estado/sub-estado +
 *  label corto + icono. Distinto color por estado para que el user
 *  identifique de un vistazo qué está pasando con cada job. */
function statusBadge(job: ActiveJob): {
  label: string;
  cls: string;
  Icon: typeof Clock;
  spin?: boolean;
} {
  if (job.status === "pending") {
    // Si está programado para el futuro, mostramos badge ámbar específico
    // con la hora de ejecución incrustada — el user lo ve sin abrir la card.
    if (job.scheduled_for != null && job.scheduled_for > Date.now() / 1000) {
      return {
        label: `Programado · ${formatScheduledFor(job.scheduled_for)}`,
        cls: "border-amber-500/50 bg-amber-500/15 text-amber-700 dark:text-amber-300",
        Icon: Timer,
      };
    }
    // El puesto lo calcula el servidor sobre la cola ENTERA. Contarlo aquí
    // mentiría: cada uno solo ve lo suyo, así que Ana se vería siempre la
    // primera aunque tuviera veinte por delante.
    const puesto = job.queue_position;
    return {
      label: puesto
        ? `En cola · nº ${puesto}${
            job.queue_pending_total ? ` de ${job.queue_pending_total}` : ""
          }`
        : "En cola",
      cls: "border-sky-500/40 bg-sky-500/15 text-sky-700 dark:text-sky-300",
      Icon: Clock,
    };
  }
  if (job.status === "running") {
    const sub = detectSubState(job.current_step);
    if (sub === "waiting_atlas") {
      return {
        label: "Esperando Atlas",
        cls: "border-amber-500/50 bg-amber-500/15 text-amber-700 dark:text-amber-300",
        Icon: Timer,
      };
    }
    return {
      label: "Procesando",
      cls: "border-blue-500/50 bg-blue-500/15 text-blue-700 dark:text-blue-300",
      Icon: Loader2,
      spin: true,
    };
  }
  if (job.status === "completed") {
    return {
      label: "Completado",
      cls: "border-emerald-500/50 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
      Icon: Check,
    };
  }
  if (job.status === "failed") {
    return {
      label: "Fallado",
      cls: "border-red-500/50 bg-red-500/15 text-red-700 dark:text-red-300",
      Icon: AlertCircle,
    };
  }
  // cancelled
  return {
    label: "Cancelado",
    cls: "border-slate-500/40 bg-slate-500/15 text-slate-700 dark:text-slate-300",
    Icon: X,
  };
}

/** Tick cada 1s mientras `enabled` para recalcular elapsed sin esperar
 *  a que el backend emita progress events. Devuelve `Date.now()` para
 *  poder hacer cálculos derivados estables dentro del render. */
function useTickEverySecond(enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [enabled]);
  return now;
}

export function JobCard({ job }: { job: ActiveJob }) {
  const cancel = useCancelJob();
  const remove = useRemoveJob();
  const deleteWithFile = useDeleteJobWithFile();
  const reorder = useReorderJob();
  const reschedule = useRescheduleJob();
  const dismissRecentLocal = useQueueStore((s) => s.dismissRecent);
  // Quién mira. Sale de la sesión, no de `viendo` del store: `viendo` es el
  // FILTRO ("todos" cuando se mira la cola entera), no la persona. Mientras no
  // se sepa se deja vacío: `nombreDueno` daría "ness" por defecto y a Ana le
  // saldría medio segundo la etiqueta en sus propios trabajos.
  const sesion = useMe().data?.username;
  const yo = sesion ? nombreDueno(sesion) : "";
  const [videoOpen, setVideoOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);

  const isScheduledFuture =
    job.status === "pending" &&
    job.scheduled_for != null &&
    job.scheduled_for > Date.now() / 1000;

  async function handleDeleteWithFile() {
    try {
      await deleteWithFile.mutateAsync(job.job_id);
      dismissRecentLocal(job.job_id);
      toast.success("Vídeo eliminado del disco y de la cola.");
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : "Error al eliminar el vídeo.",
      );
    } finally {
      setDeleteConfirmOpen(false);
    }
  }

  async function handleDismiss() {
    try {
      await remove.mutateAsync(job.job_id);
      dismissRecentLocal(job.job_id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al eliminar.");
    }
  }
  // Fallback defensivo: un `mode` que el frontend aún no conozca (p.ej. uno
  // nuevo del backend) NO debe tumbar todo el drawer con un icono undefined.
  const program: Program = MODE_TO_PROGRAM[job.mode] ?? "tiktok_shop";
  // Dueño del trabajo: solo se enseña si NO es de quien está mirando.
  const duenoNombre = nombreDueno(job.enqueued_by);
  const colorDueno = colorDeUsuario(duenoNombre);
  const esDeOtro = Boolean(yo) && duenoNombre !== yo;
  const isRunning = job.status === "running";
  const isFailed = job.status === "failed";
  const isCompleted = job.status === "completed";

  // Tick cliente: el WS emite `elapsed_seconds` cuando hay progress, pero
  // entre eventos pueden pasar varios segundos. Recomputamos cada 1s
  // contra `started_at` para que el contador se vea fluido.
  const nowMs = useTickEverySecond(isRunning);
  const elapsedLive: number = (() => {
    if (isRunning && job.started_at != null) {
      return Math.max(0, nowMs / 1000 - job.started_at);
    }
    return job.elapsed_seconds ?? 0;
  })();
  // Tiempo total de generación para jobs ya terminados — preferimos la
  // diferencia exacta `finished_at - started_at` y caemos a
  // `elapsed_seconds` si el backend no envió ambos timestamps.
  const generationSeconds: number | null = !isRunning
    ? job.finished_at != null && job.started_at != null
      ? Math.max(0, job.finished_at - job.started_at)
      : (job.elapsed_seconds ?? null)
    : null;

  // Para jobs completed/failed, hacemos fetch del /summary que trae
  // total_cost_usd + duration cacheada (fallback si el WS no llegó a
  // sincronizar duration_seconds). Skip para jobs running (el dialog
  // tiene su propio fetch live cuando se abre).
  const summary = useJobSummary(
    isCompleted || isFailed ? job.job_id : null,
    { live: false },
  );
  const effectiveDurationS =
    job.duration_seconds ?? summary.data?.output_duration_seconds ?? null;
  const costUsd = summary.data?.total_cost_usd ?? null;
  const createdAt = job.created_at;
  const isCancellable = job.status === "pending" || job.status === "running";
  const isDismissible =
    job.status === "completed" || job.status === "failed" || job.status === "cancelled";
  // Estos modos producen N ficheros, no uno: `result_path` es una CARPETA.
  // Reproducir/descargar no aplica (el endpoint espera un fichero); solo
  // tiene sentido abrir la carpeta en Drive.
  const isFolderResult =
    job.mode === "viralizacion_batch" || job.mode === "nicho_pov_bof_backup";
  const hasVideo = isCompleted && !!job.result_path && !isFolderResult;
  const hasFolder = isCompleted && !!job.result_path && isFolderResult;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
  const downloadUrl = hasVideo
    ? `${api.baseUrl}/api/v1/queue/${job.job_id}/download${qs}`
    : null;
  const filename = job.result_path?.split(/[/\\]/).pop() ?? `${job.job_id}.mp4`;
  const driveSearchUrl =
    hasVideo || hasFolder
      ? `https://drive.google.com/drive/search?q=${encodeURIComponent(filename)}`
      : null;
  const programIsShop = program === "tiktok_shop";
  const showSubmodule = !programIsShop;
  const details = describeJobParams(job.mode, job.params);
  const ProgramIcon = PROGRAM_ICON[program] ?? ShoppingBag;
  const SubmoduleIcon = MODE_ICON[job.mode] ?? ShoppingBag;

  async function handleCancel() {
    try {
      await cancel.mutateAsync(job.job_id);
      toast.success("Job cancelado.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al cancelar.");
    }
  }

  return (
    <div
      className={cn(
        "rounded-md border bg-card p-3 shadow-sm",
        PROGRAM_BORDER[program],
        isFailed && "border-destructive/40",
        isCompleted && "border-green-500/40",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant="outline" className="gap-1 text-xs">
              <ProgramIcon className="h-3 w-3" strokeWidth={1.75} />
              {PROGRAM_LABEL[program]}
            </Badge>
            {/* De quién es. Solo cuando NO es de quien mira: en la cola propia
                sobra, y con "Todas" es lo primero que hace falta saber. Cada
                persona con su color, el mismo de los circulitos de la
                cabecera. */}
            {esDeOtro && (
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[11px] font-semibold",
                  colorDueno.pildora,
                )}
                title={`Encolado por ${duenoNombre}`}
              >
                <span className={cn("h-1.5 w-1.5 rounded-full", colorDueno.punto)} />
                {duenoNombre}
              </span>
            )}
            {showSubmodule && (
              <Badge variant="secondary" className="gap-1 text-xs">
                <SubmoduleIcon className="h-3 w-3" strokeWidth={1.75} />
                {SUBMODULE_LABEL[job.mode]}
              </Badge>
            )}
          </div>
          <p className="mt-1 truncate text-sm font-medium" title={job.title}>
            {job.title || "(sin título)"}
          </p>
          <p
            className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground"
            title={`Job ID: ${job.job_id}`}
          >
            {effectiveDurationS != null && effectiveDurationS > 0 && (
              <span
                className="inline-flex items-center gap-0.5 tabular-nums"
                title="Duración del vídeo final"
              >
                <Film className="h-3 w-3" strokeWidth={1.75} />
                {formatDuration(effectiveDurationS)}
              </span>
            )}
            {generationSeconds != null && generationSeconds > 0 && (
              <span
                className="inline-flex items-center gap-0.5 tabular-nums"
                title="Tiempo de generación (cuánto tardó en producirse)"
              >
                · <Timer className="h-3 w-3" strokeWidth={1.75} />
                {formatSeconds(generationSeconds)}
              </span>
            )}
            {(createdAt != null || (costUsd != null && costUsd > 0)) && (
              // Hora + coste en el MISMO span → flex-wrap no los separa
              // a líneas distintas. Si la card es estrecha, los dos saltan
              // juntos a una segunda línea.
              <span className="inline-flex items-center gap-1.5 tabular-nums whitespace-nowrap">
                {createdAt != null && (
                  <span
                    className="inline-flex items-center gap-0.5"
                    title={`Creado a las ${formatClockTime(createdAt)}`}
                  >
                    · <Clock className="h-3 w-3" strokeWidth={1.75} />
                    {formatClockTime(createdAt)}
                  </span>
                )}
                {costUsd != null && costUsd > 0 && (
                  <span
                    className="inline-flex items-center gap-0.5 text-amber-500"
                    title={`Coste APIs externas: $${costUsd.toFixed(4)} USD`}
                  >
                    · <Coins className="h-3 w-3" strokeWidth={1.75} />
                    ${costUsd.toFixed(3)}
                  </span>
                )}
              </span>
            )}
            {details.length > 0 && <span>· {details.join(" · ")}</span>}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          {(() => {
            const meta = statusBadge(job);
            return (
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                  meta.cls,
                )}
                title={job.current_step || meta.label}
              >
                <meta.Icon
                  className={cn("h-3 w-3", meta.spin && "animate-spin")}
                />
                {meta.label}
              </span>
            );
          })()}
          {job.status === "pending" && (
            <div className="flex items-center gap-0.5">
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6"
                onClick={() =>
                  reorder.mutate(
                    { jobId: job.job_id, direction: "top" },
                    {
                      onError: (e) => toast.error(`No se pudo mover: ${e.message}`),
                    },
                  )
                }
                disabled={reorder.isPending}
                aria-label="Mover al principio"
                title="Mover al principio (próximo en ejecutarse)"
              >
                <ArrowUp className="h-3 w-3" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6"
                onClick={() =>
                  reorder.mutate(
                    { jobId: job.job_id, direction: "up" },
                    {
                      onError: (e) => toast.error(`No se pudo mover: ${e.message}`),
                    },
                  )
                }
                disabled={reorder.isPending}
                aria-label="Subir 1 posición"
                title="Subir 1 posición"
              >
                <ChevronUp className="h-3 w-3" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6"
                onClick={() =>
                  reorder.mutate(
                    { jobId: job.job_id, direction: "down" },
                    {
                      onError: (e) => toast.error(`No se pudo mover: ${e.message}`),
                    },
                  )
                }
                disabled={reorder.isPending}
                aria-label="Bajar 1 posición"
                title="Bajar 1 posición"
              >
                <ChevronDown className="h-3 w-3" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className={cn(
                  "h-6 w-6",
                  isScheduledFuture && "text-amber-600 dark:text-amber-400",
                )}
                onClick={() => setScheduleOpen(true)}
                disabled={reschedule.isPending}
                aria-label="Programar"
                title={
                  isScheduledFuture
                    ? "Cambiar hora programada"
                    : "Programar para más tarde"
                }
              >
                <Timer className="h-3 w-3" />
              </Button>
            </div>
          )}
          {isCancellable && (
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              onClick={handleCancel}
              disabled={cancel.isPending}
              aria-label={`Cancelar ${job.job_id.slice(0, 8)}`}
            >
              {cancel.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <X className="h-3 w-3" />
              )}
            </Button>
          )}
          {isDismissible && (
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={handleDismiss}
              disabled={remove.isPending}
              aria-label={`Quitar de recientes ${job.job_id.slice(0, 8)}`}
              title="Quitar de recientes"
            >
              {remove.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <X className="h-3 w-3" />
              )}
            </Button>
          )}
        </div>
      </div>

      {isScheduledFuture && job.scheduled_for != null && (
        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-1.5 rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-[11px]">
          <span className="flex min-w-0 items-center gap-1 text-amber-700 dark:text-amber-300">
            <Timer className="h-3 w-3 shrink-0" />
            <span className="truncate">
              Se ejecutará <strong>{formatScheduledFor(job.scheduled_for)}</strong>
            </span>
          </span>
          <button
            type="button"
            onClick={() => setScheduleOpen(true)}
            disabled={reschedule.isPending}
            className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-amber-700 underline-offset-2 hover:bg-amber-500/15 hover:underline disabled:opacity-50 dark:text-amber-300"
          >
            Cambiar
          </button>
        </div>
      )}

      {isRunning && (
        <div className="mt-2 space-y-1">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${Math.min(100, job.progress_percent)}%` }}
            />
          </div>
          <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className="min-w-0 flex-1 truncate">
              {stripDuplicatedNumbers(job.current_step) || "…"}
            </span>
            <span className="shrink-0 font-mono tabular-nums">
              {job.progress_percent.toFixed(0)}%
              {elapsedLive > 0 && ` · ${formatSeconds(elapsedLive)}`}
              {job.estimated_remaining_seconds != null &&
                job.estimated_remaining_seconds > 0 &&
                ` · ETA ${formatSeconds(job.estimated_remaining_seconds)}`}
            </span>
          </div>
        </div>
      )}

      {isFailed && job.error && (
        <p
          className="mt-2 line-clamp-2 text-xs text-destructive"
          title={job.error}
        >
          {job.error}
        </p>
      )}

      {/* Botón "Ver detalle" — abre dialog con métricas resumidas + tab
          de logs raw. Disponible para todos los estados del job. */}
      {(isRunning || isCompleted || isFailed) && (
        <div className="mt-2">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 text-xs"
            onClick={() => setDetailOpen(true)}
          >
            <FileText className="h-3 w-3" />
            Ver detalle
          </Button>
        </div>
      )}

      {hasFolder && driveSearchUrl && (
        <div className="mt-2 space-y-1">
          <Button asChild size="sm" variant="default" className="h-7 gap-1 px-3 text-[10px] sm:text-xs">
            <a href={driveSearchUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-2.5 w-2.5 shrink-0 sm:h-3 sm:w-3" />
              <span className="truncate">Abrir carpeta en Drive</span>
            </a>
          </Button>
          <p className="text-[10px] text-muted-foreground">
            Son varios vídeos: se abren desde la carpeta{" "}
            <span className="font-medium text-foreground">{filename}</span>.
          </p>
        </div>
      )}

      {hasVideo && (
        <div className="mt-2 grid grid-cols-4 gap-1 sm:flex sm:flex-wrap">
          <Button
            size="sm"
            variant="default"
            className="h-7 min-w-0 gap-0.5 px-1.5 text-[10px] sm:gap-1 sm:px-3 sm:text-xs"
            onClick={() => setVideoOpen(true)}
          >
            <Play className="h-2.5 w-2.5 shrink-0 sm:h-3 sm:w-3" />
            <span className="truncate">Reproducir</span>
          </Button>
          {downloadUrl && (
            <Button asChild size="sm" variant="outline" className="h-7 min-w-0 gap-0.5 px-1.5 text-[10px] sm:gap-1 sm:px-3 sm:text-xs">
              <a href={downloadUrl} download={filename}>
                <Download className="h-2.5 w-2.5 shrink-0 sm:h-3 sm:w-3" />
                <span className="truncate">Descargar</span>
              </a>
            </Button>
          )}
          {driveSearchUrl && (
            <Button asChild size="sm" variant="outline" className="h-7 min-w-0 gap-0.5 px-1.5 text-[10px] sm:gap-1 sm:px-3 sm:text-xs">
              <a href={driveSearchUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-2.5 w-2.5 shrink-0 sm:h-3 sm:w-3" />
                <span className="truncate">Drive</span>
              </a>
            </Button>
          )}
          {/* Eliminar — borra MP4 del disco (Drive sync borrará en Google
              Drive) + quita el job del historial. Requiere confirmación. */}
          <Button
            size="sm"
            variant="outline"
            className="h-7 min-w-0 gap-0.5 border-destructive/40 px-1.5 text-[10px] text-destructive hover:bg-destructive/10 hover:text-destructive sm:gap-1 sm:px-3 sm:text-xs"
            onClick={() => setDeleteConfirmOpen(true)}
            disabled={deleteWithFile.isPending}
          >
            {deleteWithFile.isPending ? (
              <Loader2 className="h-2.5 w-2.5 shrink-0 animate-spin sm:h-3 sm:w-3" />
            ) : (
              <Trash2 className="h-2.5 w-2.5 shrink-0 sm:h-3 sm:w-3" />
            )}
            <span className="truncate">Eliminar</span>
          </Button>
        </div>
      )}

      {/* AlertDialog de confirmación — el borrado es destructivo (no
          reversible salvo que Drive tenga papelera). */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar este vídeo?</AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              <span className="block">
                Se borrará el archivo{" "}
                <code className="rounded bg-muted px-1 text-xs">{filename}</code>{" "}
                del disco local. Drive Desktop sincronizará el borrado a
                Google Drive (se quedará 30 días en la papelera de Drive
                por si quieres recuperarlo).
              </span>
              <span className="block">
                También se eliminará el job de la lista de Recientes.
                <strong className="text-destructive">
                  {" "}Esta acción no se puede deshacer desde la app.
                </strong>
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteWithFile.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteWithFile}
              disabled={deleteWithFile.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteWithFile.isPending ? (
                <>
                  <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                  Eliminando…
                </>
              ) : (
                <>
                  <Trash2 className="mr-2 h-3 w-3" />
                  Sí, eliminar
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {hasVideo && (
        <JobVideoDialog
          job={job}
          open={videoOpen}
          onOpenChange={setVideoOpen}
        />
      )}

      <JobDetailDialog
        jobId={job.job_id}
        title={job.title || job.job_id}
        isRunning={isRunning}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />

      <SchedulePicker
        open={scheduleOpen}
        onOpenChange={setScheduleOpen}
        initialScheduledFor={job.scheduled_for ?? null}
        title="Reprogramar job"
        description={`Cambia la hora a la que este job se ejecutará. Job actual: ${job.title.slice(0, 80)}`}
        confirmLabel="Guardar"
        busy={reschedule.isPending}
        onConfirm={(iso) => {
          reschedule.mutate(
            { jobId: job.job_id, scheduledForIso: iso },
            {
              onSuccess: () => {
                toast.success(
                  iso === null
                    ? "Job desprogramado — se ejecutará inmediatamente."
                    : "Hora actualizada.",
                );
                setScheduleOpen(false);
              },
              onError: (e) => toast.error(`No se pudo reprogramar: ${e.message}`),
            },
          );
        }}
      />
    </div>
  );
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`;
  const min = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${min}m ${sec}s`;
}

/** Hora del día en HH:MM local desde un timestamp epoch en segundos. */
function formatClockTime(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}

/** Duración del vídeo final en formato mm:ss (o ss si < 60s). */
function formatDuration(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  const min = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${min}:${sec.toString().padStart(2, "0")}`;
}

/** Quita números redundantes del mensaje del runner cuando el card ya los
 *  va a renderizar a la derecha. Por ejemplo, el mensaje de transcribe
 *  podría incluir "63%" o "1m47s restantes" si en el futuro alguien lo
 *  vuelve a meter. Aquí lo limpiamos para evitar la duplicación visual. */
function stripDuplicatedNumbers(s: string): string {
  return s
    .replace(/\s*\d+\s*%/g, "")
    .replace(/\s*~?\d+m\s*\d+s\s*restantes/gi, "")
    .replace(/\s*~?\d+s\s*restantes/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}
