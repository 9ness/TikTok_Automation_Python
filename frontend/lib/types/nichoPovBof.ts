// Espejo de `src/api/schemas/nicho_pov_bof/models.py`.

export interface SourceInfo {
  slug: string;
  label: string;
  /** Solo en "Top vendidos": vendidos que faltan por copiar a la carpeta. */
  pendientes: number;
}

export interface SourcesListResponse {
  items: SourceInfo[];
}

export interface ProductFolder {
  name: string;
  id: string;
  completed: boolean;
  /** El Drive del curso ya no tiene esta carpeta: sale de nuestra copia. */
  desde_copia?: boolean;
  /** Cuántos de sus productos ya tienen enlazada la ficha de TikTok Shop. */
  con_url?: number;
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
  /** De qué carpeta es. Solo viene relleno en el listado de TODAS las carpetas
   *  (Top vendidos ordenado por ventas); en el normal se sabe por la pantalla. */
  folder?: string;
  /** Sus fotos salen de NUESTRA copia: el Drive del curso ya no las tiene. */
  desde_copia?: boolean;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  titulo: string | null;
  titulo_tiktok_completo: string | null;
  tienda: string | null;
  caption: string | null;
  /** Dos emojis que acompañan al caption (reacción + producto). */
  emojis?: string;
  /** Promesa detectada en el caption; vacío/null si es seguro publicarlo. */
  caption_riesgo: string | null;
  gancho: string | null;
  cta: string | null;
  /** Ya metido en el escaparate de TikTok. Es el paso que MÁS tiempo cuesta
   *  del día: hay que buscar cada producto a mano en el Marketplace porque
   *  EchoTik solo da con la ficha 1 de cada 4 veces y su cuota gratis (100
   *  llamadas al mes) no llega ni de lejos al volumen diario. */
  en_escaparate: boolean;
  uploaded: boolean;
  /** Cuándo se marcó como subido (epoch). 0 = sin marcar. */
  uploaded_at: number;
  /** Solo en "Top vendidos": ventas del producto de origen y cuándo entró. */
  ventas: number;
  vendido_at: number;
  /** Precio leído de la ficha (0 = no se pudo leer). */
  precio: number;
  /** Precio de antes del descuento (0 si no hay). Solo informativo. */
  precio_lista: number;
  /** Precio por encima del umbral → guion de plazos y vídeo de dos clips. */
  modo_plazos: boolean;
  clip1: boolean;
  clip2: boolean;
  /** Solo en plazos: el guion del curso que le ha tocado. */
  guion: string;
  guion_caracteres: number;
  sold: boolean;
  video_path: string | null;
  /** Cambia en cada montaje: se usa para romper la caché del navegador y que
   *  Ver/Descargar apunten siempre a la última versión. */
  video_listo_at?: number;
  /** Hay un montaje de este producto en cola o en curso (lo dice la cola). */
  montando?: boolean;
  /** Voz que encaja con el producto; solo es el valor inicial de la ficha. */
  sexo_sugerido?: "hombre" | "mujer";
  /** Aviso si no se pudo confirmar cuál de las fotos es la del producto. */
  foto_aviso?: string;
  /** Cuándo se subió al Drive del curso (ISO). Dice si el producto es NUEVO en
   *  una carpeta que ya se había trabajado. */
  subida_at?: string;
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
/** Entrada del ranking de vendidos. No es un `ProductoItem`: viene de su
 *  propio índice en Redis con una copia de lo justo para pintarlo, porque
 *  recorrer las 31 carpetas para encontrar dos ventas costaba 8 segundos. */
export interface VendidoItem {
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  tienda: string;
  clean_photo_id: string;
  product_url: string;
  /** Cuántas se han vendido. Un producto que repite es la mejor señal. */
  unidades: number;
  vendido_at: number;
  updated_at: number;
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

/** Una cuenta del banco de EchoTik. El plan gratis da 100 llamadas al mes, así
 *  que una cuenta seca vuelve a servir pasado el mes: por eso interesa
 *  `renueva_at` (primer uso + 30 días) y no solo si está agotada. */
export interface EchoTikCuenta {
  usuario: string;
  usuario_mascara: string;
  nota: string;
  activa: boolean;
  llamadas: number;
  primer_uso_at: number | null;
  ultimo_uso_at: number | null;
  renueva_at: number | null;
  disponible: boolean;
  sin_cuota: boolean;
}

export interface EchoTikCuentasResponse {
  ok: boolean;
  items: EchoTikCuenta[];
  mensaje: string;
}

export interface EchoTikCuentaRequest {
  usuario: string;
  password: string;
  nota: string;
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
  en_escaparate?: boolean;
  uploaded?: boolean;
  sold?: boolean;
  /** A qué nicho se le apunta la venta. Solo se manda al marcar "vendió". */
  nicho?: string;
  /** Precio escrito a mano cuando la ficha no se deja leer. Sin precio el
   *  producto nunca pasa a plazos. -1 lo borra. */
  precio?: number;
}

export interface VideoUploadResponse {
  ok: boolean;
  job_id: string | null;
  message: string;
}

export interface HashtagsResponse {
  ok: boolean;
  /** Hashtags que se pegan al final de todos los captions. */
  tags: string[];
}

/** Resultado del buscador global. No es un `ProductoItem`: barre las 35
 *  carpetas de las dos fuentes, así que trae `folder` y `source` (hacen falta
 *  para la foto y para marcar la venta), y deja fuera lo caro de resolver
 *  (caption, gancho, prompts…). */
export interface ProductoBuscado {
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  clean_photo_id: string;
  product_url: string;
  en_escaparate: boolean;
  uploaded: boolean;
  sold: boolean;
  /** Unidades si ya está en el ranking; 0 si todavía no vendió. */
  unidades: number;
}

/** Producto que apareció DESPUÉS de haber trabajado ya su carpeta, porque
 *  antes se perdía (fotos sin extensión, o dos productos fundidos bajo el
 *  mismo número). Lista TEMPORAL: cuando no queden, se puede quitar. */
export interface ProductoRecuperado {
  source: string;
  folder: string;
  /** El producto ENTERO: se trabaja aquí mismo, como en su carpeta. */
  producto: ProductoItem;
}
