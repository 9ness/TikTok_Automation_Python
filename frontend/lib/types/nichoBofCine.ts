/** Nicho BOF Cinematográfico (módulo 10) — espejo de
 *  `src/api/schemas/nicho_bof_cine/models.py`. */

export interface CinePrompts {
  /** Se usa DOS veces: hacen falta dos imágenes por producto. */
  imagen: string;
  video: string;
}

export interface CineSource {
  slug: string;
  label: string;
}

export interface CineFolder {
  name: string;
  id: string;
  completed: boolean;
}

export interface CineFoldersResponse {
  source: string;
  items: CineFolder[];
  total: number;
  completed_count: number;
  current: string | null;
}

export interface CineProducto {
  producto: string;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  emojis: string;
  caption_riesgo: string;
  gancho: string;
  cta: string;
  sexo_sugerido: "hombre" | "mujer";
  /** Los dos clips de ~5s. Hasta que no están los dos no se monta nada. */
  clip1: boolean;
  clip2: boolean;
  /** Escaparate: índice único por (tienda|nombre), común a todos los nichos. */
  en_escaparate: boolean;
  uploaded: boolean;
  video_path: string | null;
  video_listo_at: number;
  montando: boolean;
}

export interface CineProductosResponse {
  source: string;
  folder: string;
  items: CineProducto[];
  textos_extraidos: boolean;
  montando: boolean;
}

export interface CineUploadResponse {
  job_id: string;
  encolado: boolean;
  message: string;
}
