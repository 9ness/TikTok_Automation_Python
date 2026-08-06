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
  titulo: string;
  tienda: string;
  caption: string;
  emojis: string;
  gancho: string;
  cta: string;
  caption_riesgo: string;
  sexo_sugerido: string;
  /** Lo propio de este nicho: el guion que locuta la IA. */
  guion: string;
  subliminal: string;
  guion_caracteres: number;
  clip1: boolean;
  clip2: boolean;
  voz_label: string;
  voz_sexo: string;
  uploaded: boolean;
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
