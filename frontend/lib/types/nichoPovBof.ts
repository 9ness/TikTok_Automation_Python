// Espejo de `src/api/schemas/nicho_pov_bof/models.py`.

export interface SourceInfo {
  slug: string;
  label: string;
}

export interface SourcesListResponse {
  items: SourceInfo[];
}

export interface ProductFolder {
  name: string;
  id: string;
  completed: boolean;
}

export interface FoldersListResponse {
  source: string;
  items: ProductFolder[];
  total: number;
  completed_count: number;
  /** Primera carpeta sin completar — lo que la UI muestra por defecto. */
  current: string | null;
}

export interface PhotoInfo {
  id: string;
  name: string;
  size: number;
  mime: string;
}

export interface PhotosListResponse {
  source: string;
  folder: string;
  items: PhotoInfo[];
}

export interface BackupCheckResponse {
  last_snapshot: string | null;
  has_changes: boolean;
  would_be_full: boolean;
  full_copy_ratio: number;
  n_added: number;
  n_modified: number;
  n_deleted: number;
  n_total_source: number;
  change_ratio: number;
}

export interface BackupSyncResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
}

export interface MarkCompletedRequest {
  source: string;
  folder: string;
  completed: boolean;
}

export interface MarkCompletedResponse {
  source: string;
  folder: string;
  completed: boolean;
  completed_count: number;
  total: number;
  next_folder: string | null;
}

// --- Fase 2: automatización de vídeos ---------------------------------

export interface PromptsResponse {
  imagen: string;
  video: string;
}

export interface ProductoItem {
  producto: string;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  titulo: string | null;
  titulo_tiktok_completo: string | null;
  tienda: string | null;
  caption: string | null;
  gancho: string | null;
  cta: string | null;
  uploaded: boolean;
  sold: boolean;
  video_path: string | null;
  /** Cambia en cada montaje: se usa para romper la caché del navegador y que
   *  Ver/Descargar apunten siempre a la última versión. */
  video_listo_at?: number;
  con_textos?: boolean;
  /** Ficha en TikTok Shop. Vacío = aún no se ha buscado o no se encontró
   *  nada con parecido suficiente (averiguarla gasta cuota de EchoTik). */
  product_id: string;
  product_url: string;
  url_match_name: string;
  url_match_score: number;
}

/** Item de /vendidos: agrega productos de TODAS las carpetas de la fuente,
 *  así que trae `folder` (no está en ProductoItem porque ahí el folder ya
 *  viene fijado por query param). Se necesita para poder construir la URL
 *  de la foto con `buildPhotoUrl(source, folder, id)`. */
export interface VendidoItem extends ProductoItem {
  folder: string;
}

export interface ExtraerTextosRequest {
  source: string;
  folder: string;
}

export interface ProductoUrlRequest {
  source: string;
  folder: string;
  producto: string;
}

export interface EchoTikCredsRequest {
  usuario: string;
  password: string;
  /** Gasta UNA llamada comprobando que funcionan antes de guardarlas. */
  probar: boolean;
}

export interface EchoTikCredsResponse {
  ok: boolean;
  configurado: boolean;
  usuario_mascara: string;
  origen: string;
  mensaje: string;
}

export interface ProductosUrlsRequest {
  source: string;
  folder: string;
}

export interface ProductosUrlsResponse {
  source: string;
  folder: string;
  items: ProductoItem[];
  textos_extraidos: boolean;
  /** Llamadas de EchoTik consumidas por esta ejecución. */
  llamadas: number;
  encontrados: number;
  sin_resultado: number;
  aviso: string;
}

export interface EstadoRequest {
  source: string;
  folder: string;
  producto: string;
  uploaded?: boolean;
  sold?: boolean;
}

export interface VideoUploadResponse {
  ok: boolean;
  job_id: string | null;
  message: string;
}
