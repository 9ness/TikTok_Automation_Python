/**
 * Tipos de la Cuenta Piloto. Reflejan `src/api/schemas/cuenta_piloto/models.py`.
 */

/** Un montaje del producto. Hay VARIOS por producto, a propósito. */
export interface VideoPiloto {
  n: number;
  sexo: string;
  job_id: string;
  at: number;
}

export interface ProductoPiloto {
  id: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  emojis: string;
  gancho: string;
  cta: string;
  caption_riesgo: string;
  /** Escaparate: índice único por (tienda|nombre), común a todos los nichos. */
  en_escaparate: boolean;
  tiene_ficha: boolean;
  videos: VideoPiloto[];
  creado_at: number;
  textos_at: string;
  montando: boolean;
}

export interface ProductosPilotoResponse {
  items: ProductoPiloto[];
}

export interface ProductoPilotoResponse {
  producto: ProductoPiloto;
}
