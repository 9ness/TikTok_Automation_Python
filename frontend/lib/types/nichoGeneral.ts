/** Nicho General · UGC — el anuncio de tres clips. */

export interface OpcionUGC {
  clave: string;
  label: string;
  /** Solo en los personajes: su descripción, para regenerar la imagen. Vacía
   *  si ese personaje aún no está creado. */
  ficha?: string;
  /** Solo en los nichos: con qué sexo se escribe su versión principal. */
  sexo?: string;
}

export interface ConfigUGCResponse {
  ganchos: OpcionUGC[];
  duraciones: OpcionUGC[];
  /** Los nichos de producto y los dos sexos: de cada combinación hay un
   *  personaje distinto. */
  nichos: OpcionUGC[];
  sexos: OpcionUGC[];
  /** Los personajes que existen de verdad (`belleza_mujer_2`…). */
  personajes: OpcionUGC[];
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
  /** La versión con el otro sexo, si se ha pedido para este producto. */
  escenas_alt: EscenaUGC[];
  voz_alt: string;
  /** De qué nicho es. Lo pone Gemini al escribir las escenas y se corrige a
   *  mano si se equivoca; es lo que decide el personaje. */
  nicho: string;
  personaje: string;
  personaje_sexo: string;
  /** `belleza_mujer`… El nombre de la foto que se adjunta en Flow. */
  personaje_clave: string;
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
