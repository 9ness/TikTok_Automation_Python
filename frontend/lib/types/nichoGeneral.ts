/** Nicho General · UGC — el anuncio de tres clips. */

export interface OpcionUGC {
  clave: string;
  label: string;
}

export interface ConfigUGCResponse {
  ganchos: OpcionUGC[];
  duraciones: OpcionUGC[];
  escenas: number;
  /** El de crear el personaje: se usa una vez por persona, con una foto de
   *  Pinterest, y su resultado va a Flow. */
  prompt_personaje: string;
}

export interface EscenaUGC {
  n: number;
  titulo: string;
  /** Va a Flow con el personaje y la foto del producto. */
  prompt_imagen: string;
  /** Va sobre la imagen que salga del anterior. */
  prompt_video: string;
  /** Lo que se dice en voz alta: sirve para contarlo y para reconocer el clip. */
  guion: string;
  caracteres: number;
}

export interface ProductoUGC {
  producto: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  caption: string;
  precio: string;
  plazos: boolean;
  clean_photo_id?: string | null;
  titled_photo_id?: string | null;
  product_url: string;
  en_escaparate: boolean;
  escenas: EscenaUGC[];
  voz: string;
  personaje: string;
  personaje_sexo: string;
  clips: string[];
  video_path?: string | null;
  video_listo_at: number;
  montando: boolean;
  uploaded: boolean;
  sold: boolean;
}

export interface ProductosUGCResponse {
  items: ProductoUGC[];
  gancho: string;
  duracion: string;
}
