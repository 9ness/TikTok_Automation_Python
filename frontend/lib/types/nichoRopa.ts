// Espejo de `src/api/schemas/nicho_ropa/models.py`.

export interface PromptsRopaResponse {
  imagen: string;
  /** Los dos se derivan del mismo texto: la diferencia es la frase de la mano. */
  video_con_manos: string;
  video_sin_manos: string;
}

export interface PrendaItem {
  producto: string;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  /** Aviso si no se pudo distinguir cuál es la foto de la prenda. */
  foto_aviso: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  emojis: string;
  /** Promesa detectada en el caption; vacío si es seguro publicarlo. */
  caption_riesgo: string;
  uploaded: boolean;
  video_path: string | null;
  video_listo_at: number;
  /** Hay un montaje de esta prenda en cola o en curso. */
  montando: boolean;
}

export interface PrendasListResponse {
  items: PrendaItem[];
  textos_extraidos: boolean;
  montando: boolean;
}

export interface VideoRopaUploadResponse {
  ok: boolean;
  job_id: string | null;
  message: string;
}
