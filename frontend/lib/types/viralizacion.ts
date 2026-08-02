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

export interface CarpetasListResponse {
  items: string[];
}

export interface StyleChoice {
  key: string;
  label: string;
}

export interface StylesListResponse {
  items: StyleChoice[];
}

export interface RoundPlan {
  ronda: number;
  n_videos: number;
  default_style: string;
}

export interface RoundPlanResponse {
  total_videos: number;
  rounds: RoundPlan[];
}

export interface ViralizacionGenerateRequest {
  ponentes: string[];
  cantidad: Record<string, number>;
  nombre_cuenta: string;
  music_rounds: number;
  /** Estilo de cada ronda: índice 0 = ronda 1. Vacío = rotación automática. */
  round_styles?: string[];
  /** Estilos elegidos; los vídeos se reparten entre ellos a partes iguales. */
  styles_pool?: string[];
}

export interface ViralizacionGenerateResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
  total_videos: number;
}

/** Un corte propuesto sobre un audio largo, todavía sin cortar. */
export interface ClipPropuesto {
  inicio: number;
  fin: number;
  duracion: number;
  /** Frase con la que arranca — es lo que decide si el vídeo retiene. */
  gancho: string;
  tema: string;
  porque: string;
}

export interface PropuestaClips {
  ponente: string;
  fichero: string;
  clips: ClipPropuesto[];
  at: number | null;
}

export interface PropuestasListResponse {
  items: PropuestaClips[];
}

export interface SubirAudioLargoResponse {
  ok: boolean;
  job_id: string | null;
  ponente: string;
  fichero: string;
  mensaje: string;
}

export interface CortarClipsResponse {
  ok: boolean;
  creados: string[];
  mensaje: string;
}
