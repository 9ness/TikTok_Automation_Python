"use client";

import { useState } from "react";
import { AlertCircle, Check, Clock, Download, ExternalLink, Loader2, Play, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { useCancelJob, useRemoveJob } from "@/lib/queries/queue";
import { useQueueStore } from "@/lib/stores/queueStore";
import { JobVideoDialog } from "./JobVideoDialog";
import {
  describeJobParams,
  MODE_ICON,
  MODE_TO_PROGRAM,
  PROGRAM_BORDER,
  PROGRAM_ICON,
  PROGRAM_LABEL,
  SUBMODULE_LABEL,
} from "@/lib/queue-meta";
import type { ActiveJob, JobStatus } from "@/lib/types/queue";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<JobStatus, string> = {
  pending: "En cola",
  running: "Procesando",
  completed: "Completado",
  failed: "Fallado",
  cancelled: "Cancelado",
};

export function JobCard({ job }: { job: ActiveJob }) {
  const cancel = useCancelJob();
  const remove = useRemoveJob();
  const dismissRecentLocal = useQueueStore((s) => s.dismissRecent);
  const [videoOpen, setVideoOpen] = useState(false);

  async function handleDismiss() {
    try {
      await remove.mutateAsync(job.job_id);
      dismissRecentLocal(job.job_id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al eliminar.");
    }
  }
  const program = MODE_TO_PROGRAM[job.mode];
  const isRunning = job.status === "running";
  const isFailed = job.status === "failed";
  const isCompleted = job.status === "completed";
  const isCancellable = job.status === "pending" || job.status === "running";
  const isDismissible =
    job.status === "completed" || job.status === "failed" || job.status === "cancelled";
  const hasVideo = isCompleted && !!job.result_path;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
  const downloadUrl = hasVideo
    ? `${api.baseUrl}/api/v1/queue/${job.job_id}/download${qs}`
    : null;
  const filename = job.result_path?.split(/[/\\]/).pop() ?? `${job.job_id}.mp4`;
  const driveSearchUrl = hasVideo
    ? `https://drive.google.com/drive/search?q=${encodeURIComponent(filename)}`
    : null;
  const programIsShop = program === "tiktok_shop";
  const showSubmodule = !programIsShop;
  const details = describeJobParams(job.mode, job.params);
  const ProgramIcon = PROGRAM_ICON[program];
  const SubmoduleIcon = MODE_ICON[job.mode];

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
          <p className="truncate text-xs text-muted-foreground">
            {job.job_id.slice(0, 8)}
            {job.duration_seconds != null &&
              job.duration_seconds > 0 &&
              ` · ⏱ ${formatDuration(job.duration_seconds)}`}
            {details.length > 0 && ` · ${details.join(" · ")}`}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge variant={badgeVariant(job.status)} className="gap-1">
            {iconFor(job.status)}
            {STATUS_LABEL[job.status]}
          </Badge>
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
              {job.estimated_remaining_seconds != null &&
                job.estimated_remaining_seconds > 0 &&
                ` · ${formatSeconds(job.estimated_remaining_seconds)}`}
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

      {hasVideo && (
        <div className="mt-2 flex flex-wrap gap-1">
          <Button
            size="sm"
            variant="default"
            className="h-7 gap-1 text-xs"
            onClick={() => setVideoOpen(true)}
          >
            <Play className="h-3 w-3" />
            Reproducir
          </Button>
          {downloadUrl && (
            <Button asChild size="sm" variant="outline" className="h-7 gap-1 text-xs">
              <a href={downloadUrl} download={filename}>
                <Download className="h-3 w-3" />
                Descargar
              </a>
            </Button>
          )}
          {driveSearchUrl && (
            <Button asChild size="sm" variant="outline" className="h-7 gap-1 text-xs">
              <a href={driveSearchUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-3 w-3" />
                Drive
              </a>
            </Button>
          )}
        </div>
      )}

      {hasVideo && (
        <JobVideoDialog
          job={job}
          open={videoOpen}
          onOpenChange={setVideoOpen}
        />
      )}
    </div>
  );
}

function badgeVariant(status: JobStatus): "default" | "secondary" | "destructive" | "outline" {
  if (status === "running") return "default";
  if (status === "failed") return "destructive";
  if (status === "completed") return "outline";
  return "secondary";
}

function iconFor(status: JobStatus) {
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin" />;
  if (status === "completed") return <Check className="h-3 w-3" />;
  if (status === "failed") return <AlertCircle className="h-3 w-3" />;
  return <Clock className="h-3 w-3" />;
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`;
  const min = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${min}m ${sec}s`;
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
