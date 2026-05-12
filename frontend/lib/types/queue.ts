/**
 * Tipos del sistema de cola. Reflejan `src/api/schemas/queue.py`.
 */

export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export type JobMode =
  | "presidents"
  | "pronosticos"
  | "subs_auto"
  | "copyright"
  | "tiktok_shop";

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
export type WsEventType = "snapshot" | "update" | "progress" | "removed" | "pong";

export interface WsSnapshotEvent {
  type: "snapshot";
  data: { jobs: ActiveJob[] };
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
  | WsPongEvent;
