/**
 * Tipos del Nicho POV BOF Largo.
 * Reflejan `src/api/schemas/nicho_pov_bof_largo/models.py`.
 */

export interface VozLargo {
  id: string;
  label: string;
}

export interface VocesLargo {
  hombre: VozLargo[];
  mujer: VozLargo[];
}

export interface ProductoLargo {
  producto: string;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  foto_aviso: string;
  // Textos y enlaces — compartidos con el POV BOF (los extrae/busca él).
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  emojis: string;
  gancho: string;
  cta: string;
  caption_riesgo: string;
  sexo_sugerido: string;
  product_url: string;
  url_match_name: string;
  url_match_score: number;
  /** Lo propio de este nicho: el guion que locuta la IA. */
  guion: string;
  subliminal: string;
  guion_caracteres: number;
  clip1: boolean;
  clip2: boolean;
  voz_label: string;
  voz_sexo: string;
  // Progreso INDIVIDUAL de este nicho.
  en_escaparate: boolean;
  uploaded: boolean;
  sold: boolean;
  video_path: string | null;
  video_listo_at: number;
  montando: boolean;
}

export interface ProductosLargoResponse {
  source: string;
  folder: string;
  items: ProductoLargo[];
  montando: boolean;
}

export interface ClipLargoUploadResponse {
  job_id: string;
  encolado: boolean;
  message: string;
}

export interface FolderLargo {
  name: string;
  id: string;
  completed: boolean;
}

export interface FoldersLargoResponse {
  source: string;
  items: FolderLargo[];
  total: number;
  completed_count: number;
  current: string | null;
}

export interface MarkCompletedLargoResponse {
  source: string;
  folder: string;
  completed: boolean;
  completed_count: number;
  total: number;
  next_folder: string | null;
}

export interface EstadoLargoRequest {
  source: string;
  folder: string;
  producto: string;
  en_escaparate?: boolean;
  uploaded?: boolean;
  sold?: boolean;
  nicho?: string;
}
