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
  /** De qué carpeta es. Solo en el listado de TODAS las carpetas (Top
   *  vendidos por ventas). */
  folder?: string;
  /** Sus fotos salen de NUESTRA copia: el Drive del curso ya no las tiene. */
  desde_copia?: boolean;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  foto_aviso: string;
  /** Cuándo se subió al Drive del curso (ISO). */
  subida_at?: string;
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
  /** Solo en "Top vendidos": ventas del producto de origen y cuándo entró. */
  ventas: number;
  vendido_at: number;
  /** Precio leído por el POV BOF (0 = no detectado) y el de antes del descuento. */
  precio: number;
  precio_lista: number;
  /** Por encima del umbral: el guion lleva la frase de financiación. */
  modo_plazos: boolean;
  /** Lo propio de este nicho: el guion que locuta la IA. */
  guion: string;
  /** En qué modo se escribió el guion guardado. */
  guion_plazos: boolean;
  subliminal: string;
  guion_caracteres: number;
  clip1: boolean;
  clip2: boolean;
  /** Tercer clip: solo cuando el guion no cabe en dos. */
  clip3?: boolean;
  clip4?: boolean;
  /** Cuántos clips pide este guion (2, o 3 si la voz no cabe en dos). */
  clips_necesarios?: number;
  voz_label: string;
  voz_sexo: string;
  // Progreso INDIVIDUAL de este nicho.
  en_escaparate: boolean;
  uploaded: boolean;
  /** Cuándo se marcó como subido (epoch). 0 = sin marcar. */
  uploaded_at: number;
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
  /** El Drive del curso ya no tiene esta carpeta: sale de nuestra copia. */
  desde_copia?: boolean;
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
