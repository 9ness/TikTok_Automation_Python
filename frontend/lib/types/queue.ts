/**
 * Tipos del sistema de cola. Reflejan `src/api/schemas/queue.py`.
 */

export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export type JobMode =
  | "presidents"
  | "pronosticos"
  | "subs_auto"
  | "copyright"
  | "construccion_pov"
  | "tiktok_shop"
  | "tiktok_shop_watermark"
  | "tiktok_shop_pack"
  | "tiktok_shop_plan"
  | "tiktok_shop_auto_day"
  | "tiktok_shop_ready_video"
  | "editor_auto"
  | "viralizacion_batch"
  | "viralizacion_clips"
  | "nicho_pov_bof_backup"
  | "nicho_pov_bof_video"
  | "nicho_ropa_video"
  | "nicho_ropa_personas_video"
  | "nicho_bof_cine_video"
  | "cuenta_piloto_video"
  | "nicho_pov_bof_largo_video"
  | "nicho_pov_bof_plazos_video"
  | "nicho_pov_bof_textos"
  | "nicho_pov_bof_revisar"
  | "nicho_pov_bof_largo_guiones"
  | "nicho_carruseles_preparar"
  | "nicho_carruseles_reparto";

export interface ActiveJob {
  job_id: string;
  mode: JobMode;
  title: string;
  status: JobStatus;
  progress_percent: number;
  current_step: string;
  estimated_remaining_seconds: number | null;
  elapsed_seconds: number;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  enqueued_by: string | null;
  error: string | null;
  result_path?: string | null;
  duration_seconds?: number | null;
  params?: Record<string, unknown>;
  /** Unix timestamp (segundos) a la que el job se ejecutará. Si > now →
   *  el worker lo ignora hasta esa hora. Null = ejecutar inmediato. */
  scheduled_for?: number | null;
}

export interface QueueStateResponse {
  active_jobs: ActiveJob[];
  pending_count: number;
  running_count: number;
  recent_completed: ActiveJob[];
}

// ---------------------------------------------------------------------------
// WebSocket frame
// ---------------------------------------------------------------------------
export type WsEventType =
  | "snapshot" | "update" | "progress" | "removed" | "pong" | "otros";

export interface WsSnapshotEvent {
  type: "snapshot";
  data: {
    jobs: ActiveJob[];
    /** De quién es la cola que se está viendo ("todos" si se mezclan). */
    viendo?: string;
    es_admin?: boolean;
    /** Trabajos activos de CADA UNO de los demás. Solo llega al admin. */
    otros?: Record<string, number>;
  };
}

/** Cambió el número de trabajos activos de los demás (solo admin). */
export interface WsOtrosEvent {
  type: "otros";
  data: { otros: Record<string, number> };
}
export interface WsUpdateEvent {
  type: "update";
  data: { jobs: ActiveJob[] };
}
export interface WsProgressEvent {
  type: "progress";
  data: { jobs: ActiveJob[] };
}
export interface WsRemovedEvent {
  type: "removed";
  data: { job_ids: string[] };
}
export interface WsPongEvent {
  type: "pong";
  data: Record<string, never>;
}

export type WsEvent =
  | WsSnapshotEvent
  | WsUpdateEvent
  | WsProgressEvent
  | WsRemovedEvent
  | WsOtrosEvent
  | WsPongEvent;
