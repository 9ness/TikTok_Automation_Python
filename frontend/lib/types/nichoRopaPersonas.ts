/** Nicho Ropa Con Personas (módulo 7) — espejo de
 *  `src/api/schemas/nicho_ropa_personas/models.py`. */

/** Una modelo creada por el usuario. `ficha_texto` es el JSON ya formateado:
 *  es literalmente lo que se copia y se pega en la IA de imagen. */
export interface ChicaInfo {
  id: string;
  nombre: string;
  ficha_texto: string;
  creada_at: number;
}

export interface RopaPersonasPrompts {
  movimiento: string;
  /** Para cuando la IA se niega a vestir a la chica (bikinis, lencería). */
  extraer_prenda: string;
}

export interface CarpetaRopaPersonas {
  slug: string;
  label: string;
}

export interface PrendaPersonas {
  producto: string;
  clean_photo_id: string | null;
  titled_photo_id: string | null;
  foto_aviso: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  /** El emoji que se quema junto al título. */
  emojis: string;
  caption_riesgo: string;
  uploaded: boolean;
  video_path: string | null;
  video_listo_at: number;
  montando: boolean;
}

export interface PrendasPersonasResponse {
  carpeta: string;
  items: PrendaPersonas[];
  textos_extraidos: boolean;
  montando: boolean;
}
