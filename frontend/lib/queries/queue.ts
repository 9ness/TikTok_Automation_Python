"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface JobLogsResponse {
  job_id: string;
  status: string;
  title: string;
  lines: string[];
  error: string | null;
  current_step: string;
  started_at: number | null;
  finished_at: number | null;
}

export interface FalseStartPreview {
  kind: string | null;
  first_attempt: string | null;
  kept_version: string | null;
  reason: string | null;
}

export interface LongGapPreview {
  t_start: number;
  t_end: number;
  gap_s: number;
  after_word_idx?: number;
  before_word_idx?: number;
  after_word?: string;
  before_word?: string;
}

export interface RemainingSilencePreview {
  duration_s: number | null;
  input_start: number | null;
  input_end: number | null;
  before_word: string | null;
  after_word: string | null;
}

export interface JobSummaryResponse {
  job_id: string;
  status: string;
  mode: string;
  title: string;
  generation_seconds: number | null;
  output_duration_seconds: number | null;
  created_at?: number;
  started_at?: number | null;
  finished_at?: number | null;
  total_cost_usd?: number | null;
  cost_lines_count?: number;
  error: string | null;
  has_diagnostic: boolean;
  diagnostic_path?: string;
  diagnostic_error?: string;
  // Solo para mode=tiktok_shop — extraído del Generation linkado
  tier_used?: string;
  model_used?: string | null;
  /** Modelo i2v que realmente renderizó cada clip (puede mezclar si
   *  hubo failover). Ej: ["Hailuo 02", "Kling 2.1"] o ["Hailuo 02"]. */
  clips_renderer?: string[];
  // Solo si has_diagnostic === true (editor_auto)
  input_duration_seconds?: number;
  output_duration_seconds_calc?: number;
  cut_duration_seconds?: number;
  cut_pct?: number;
  cuts_by_source?: Record<string, number>;
  n_cuts_merged?: number;
  n_keep_segments?: number;
  head_trim_seconds?: number | null;
  tail_trim_seconds?: number | null;
  n_long_gaps_cut?: number;
  long_gaps_preview?: LongGapPreview[];
  n_phantom_words?: number;
  n_false_starts_cut?: number;
  false_starts_preview?: FalseStartPreview[];
  ai_cuts_by_reason?: Record<string, number>;
  quality_score?: number | null;
  quality_verdict?: string | null;
  /** Veredicto explicable: etiqueta + dimensiones + avisos baja confianza. */
  verdict_detail?: {
    overall?: "ok" | "revisar" | "fallo" | string;
    label?: string;
    dimensions?: { dim: string; ok: boolean; detail?: string }[];
    low_confidence?: string[];
  } | null;
  /** Auto-corrección: intentos con score antes→después por reintento. */
  self_heal?: {
    target?: number;
    attempts?: number;
    history?: {
      attempt: number;
      score_before?: number | null;
      score_after?: number | null;
      n_residue_cuts?: number;
      n_guarded_cuts?: number;
      n_restores?: number;
      actions?: string[];
    }[];
  } | null;
  needs_requeue?: boolean;
  transcription_ok?: boolean;
  n_loose_words?: number;
  loose_words_preview?: string[];
  n_surviving_stretched?: number;
  n_silences_remaining?: number;
  silences_remaining_preview?: RemainingSilencePreview[];
  tools_used?: string[] | null;
}

/** Resumen ejecutivo del job: lee el diagnostic JSON del editor_auto
 *  y devuelve métricas pre-procesadas (duraciones, % cortado, quality,
 *  breakdown de cortes). Si el job no es editor_auto, devuelve datos
 *  básicos sin diagnostic. */
export function useJobSummary(jobId: string | null, options?: { live?: boolean }) {
  return useQuery<JobSummaryResponse>({
    queryKey: ["queue", "summary", jobId],
    queryFn: () =>
      api.get<JobSummaryResponse>(
        `/api/v1/queue/${encodeURIComponent(jobId!)}/summary`,
      ),
    enabled: Boolean(jobId),
    refetchInterval: options?.live ? 3000 : false,
    refetchOnWindowFocus: false,
  });
}

/** Lazy fetch de los logs del job — `enabled=false` por defecto, el caller
 *  activa el query al abrir el dialog. Si el job está running, refresca
 *  cada 2s para ir viendo logs en tiempo real. */
export function useJobLogs(jobId: string | null, options?: { live?: boolean }) {
  return useQuery<JobLogsResponse>({
    queryKey: ["queue", "logs", jobId],
    queryFn: () => api.get<JobLogsResponse>(`/api/v1/queue/${encodeURIComponent(jobId!)}/logs`),
    enabled: Boolean(jobId),
    refetchInterval: options?.live ? 2000 : false,
    refetchOnWindowFocus: false,
  });
}

export function useCancelJob() {
  return useMutation<void, Error, string>({
    mutationFn: (jobId) => api.del<void>(`/api/v1/queue/${encodeURIComponent(jobId)}`),
  });
}

/** Programa o desprograma un job PENDING.
 *  `scheduled_for`: ISO 8601 string en el futuro → el worker espera a
 *  esa hora. `null` o pasado → desprograma (ejecuta inmediato). */
export function useRescheduleJob() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string; scheduled_for: number | null },
    Error,
    { jobId: string; scheduledForIso: string | null }
  >({
    mutationFn: ({ jobId, scheduledForIso }) =>
      api.patch<{ job_id: string; scheduled_for: number | null }>(
        `/api/v1/queue/${encodeURIComponent(jobId)}/schedule`,
        { scheduled_for: scheduledForIso },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}

/** Reordena un job PENDING en la cola. `direction`:
 *   - "up": sube 1 posición (intercambia con el PENDING anterior)
 *   - "down": baja 1 posición
 *   - "top": al principio (próximo en ejecutarse) */
export function useReorderJob() {
  const qc = useQueryClient();
  return useMutation<
    void,
    Error,
    { jobId: string; direction: "up" | "down" | "top" }
  >({
    mutationFn: ({ jobId, direction }) =>
      api.post<void>(
        `/api/v1/queue/${encodeURIComponent(jobId)}/reorder?direction=${direction}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}

/**
 * Para jobs en estado FINAL (completed/failed/cancelled): elimina del
 * historial persistente (queue_state.json). Para jobs activos: cancela.
 *
 * El backend hace lo correcto según el estado.
 */
export function useRemoveJob() {
  return useMutation<void, Error, string>({
    mutationFn: (jobId) => api.del<void>(`/api/v1/queue/${encodeURIComponent(jobId)}`),
  });
}

/** Borra el job del historial Y también el MP4 final del disco (Drive
 *  sincronizado). Solo válido para jobs en estado final con result_path
 *  bajo una raíz segura (TIKTOK_EDITOR/TIKTOK_SHOP/output del CR). */
export function useDeleteJobWithFile() {
  return useMutation<void, Error, string>({
    mutationFn: (jobId) =>
      api.del<void>(
        `/api/v1/queue/${encodeURIComponent(jobId)}?delete_file=true`,
      ),
  });
}

export function useClearRecentJobs() {
  return useMutation<{ removed: number }, Error, void>({
    mutationFn: () => api.del<{ removed: number }>(`/api/v1/queue/recent/all`),
  });
}

/** Health check del backend. Devuelve `{status, version, redis_configured}`. */
export interface HealthResponse {
  status: string;
  version: string;
  redis_configured: boolean;
}

export async function checkApiHealth(): Promise<HealthResponse> {
  return api.get<HealthResponse>("/api/health");
}
