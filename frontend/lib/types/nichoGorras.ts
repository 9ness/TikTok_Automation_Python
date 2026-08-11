/** Nicho Gorras (módulo 11) — espejo de
 *  `src/api/schemas/nicho_gorras/models.py`.
 *
 *  No hay nada de vídeo: este nicho no edita. Solo encontrar la gorra y
 *  copiar sus textos. */

export interface GorrasPrompt {
  slug: string;
  label: string;
  texto: string;
}

export interface GorrasCarpeta {
  slug: string;
  label: string;
}

export interface Gorra {
  producto: string;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  foto_aviso: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  emojis: string;
  caption_riesgo: string;
  /** Escaparate: índice único por (tienda|nombre), común a todos los nichos. */
  en_escaparate: boolean;
}

export interface GorrasListResponse {
  carpeta: string;
  items: Gorra[];
  textos_extraidos: boolean;
}
