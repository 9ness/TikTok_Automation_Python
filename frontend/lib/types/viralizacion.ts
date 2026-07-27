/**
 * Tipos del Programa 4 — Viralización. Reflejan
 * `src/api/schemas/viralizacion/models.py`.
 */

export interface PonenteInfo {
  slug: string;
  label: string;
  n_audios: number;
  hooks_available: number;
  hooks_total: number;
  paisajes_available: number;
  paisajes_total: number;
}

export interface PonentesListResponse {
  items: PonenteInfo[];
}

export interface ViralizacionGenerateRequest {
  ponentes: string[];
  cantidad: Record<string, number>;
  nombre_cuenta: string;
  music_rounds: number;
}

export interface ViralizacionGenerateResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
  total_videos: number;
}
