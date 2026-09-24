// Espejo de `src/api/schemas/nicho_ropa/models.py`.

export interface DuracionRopa {
  clave: string;
  label: string;
  segundos: number;
}

export interface EstiloMof10 {
  clave: string;
  label: string;
  imagen: string;
  guion: string;
  /** El texto no es del curso: lo derivamos cambiando lo de la persona. */
  derivado: boolean;
  /** En qué duración viene el guion, y cuáles admite. Vacía cuando el
   *  diálogo viene cerrado del curso y no hay tope que bajar. */
  duracion?: string;
  duraciones?: DuracionRopa[];
  /** Lo que hay que saber AL PEGARLO y no se ve en el prompt. */
  personaje?: boolean;
  /** La imagen entra en Flow como ingrediente, no como frame inicial. */
  ingrediente?: boolean;
  voz?: boolean;
  /** Si existe versión con la frase de financiación. Solo el del espejo: en
   *  los demás formatos el botón copiaba exactamente el mismo texto. */
  plazos?: boolean;
  /** Su guion promete plazos SIEMPRE: el curso lo dejó escrito en el ejemplo
   *  y no hay interruptor que lo quite. */
  plazos_fijo?: boolean;
  /** La SEGUNDA imagen, en los formatos que se graban en dos partes (calle
   *  dividido): la misma chica en otra calle. Vacía en el resto. */
  imagen2?: string;
  /** Cuántos clips hay que generar y subir. 1 = como siempre. */
  partes?: number;
  /** Lo que cabe en cada clip cuando el formato se parte. */
  caracteres_clip?: number;
  /** El montaje mete los cortes de color del principio (formato de la
   *  tienda): los genera la app, el operador solo sube los clips. */
  colores?: boolean;
  /** Plantilla para pedir en Flow la imagen 1 en otro color (`{{COLOR}}`). */
  imagen_color?: string;
  /** Clip 1 con los colores hechos por Omni (fotos como ingredientes). */
  video_omni?: string;
  /** Lo mismo para el clip 2 (de espaldas, sentadilla y cierre). */
  video_omni2?: string;
  /** Tope de caracteres que se le pide al guion. */
  caracteres?: number;
  /** El guion se escribe fuera: se pega en ChatGPT con la foto de la ficha y
   *  lo que va a Flow es lo que ese devuelva. */
  escrito_fuera?: boolean;
}

export interface PromptsRopaResponse {
  imagen: string;
  /** Los dos se derivan del mismo texto: la diferencia es la frase de la mano. */
  video_con_manos: string;
  video_sin_manos: string;
  /** Otro escenario: la prenda colgada en una percha, sin nadie. */
  video_percha: string;
  /** `mujer` | `hombre` — de qué carpeta se dedujo el prompt del espejo. */
  sexo: string;
  /** Estilos de vídeo de 10s: imagen en Flow + guion/vídeo en Omni. */
  mof10: EstiloMof10[];
  /** Los modos de grabación que existen para ESE sexo. Los manda el backend:
   *  el curso no publica los mismos formatos para hombre y para mujer. */
  modos?: ModoRopa[];
}

export interface ModoRopa {
  clave: string;
  label: string;
  /** Si el clip sale hablado. Los mudos no gastan la voz del generador. */
  voz?: boolean;
  /** "aleatorios" o "marca": son cuentas distintas, no un ajuste. */
  modalidad?: string;
  /** "calzado" cuando el formato solo vale para zapatos. */
  categoria?: string;
  /** Si necesita el personaje de referencia adjunto. */
  personaje?: boolean;
  /** Qué se ve en ese vídeo, en una frase. La manda el backend: es lo que
   *  dice el curso de cada formato. */
  desc?: string;
}

export interface CarpetaRopa {
  slug: string;
  label: string;
  /** Del catálogo de la web (prenda puesta) o de las del Drive del curso. */
  web: boolean;
  /** Catálogo del OPERADOR: las prendas las sube él, no vienen en un ZIP. */
  propia?: boolean;
  /** `mujer_muestras`, `hombre_tareas`… Vacío en las del curso y las del ZIP. */
  genero?: string;
  /** "mujer" / "hombre" — de quién es la carpeta, lo diga el slug o el género. */
  sexo?: string;
  /** Lo que pinta el chip: prendas que tiene, cuántas llevan la ficha de
   *  TikTok enlazada y cuántas tienen vídeo DEL MODO pedido. Solo vienen
   *  cuando se piden las carpetas de un sexo concreto. */
  total?: number;
  con_url?: number;
  con_video?: number;
  /** Marcada a mano como hecha, o con los vídeos hechos y pendientes de
   *  subir. Por usuario y por modo, como en el POV BOF. */
  completada?: boolean;
  pendiente?: boolean;
}

export interface CarpetasRopaResponse {
  items: CarpetaRopa[];
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
  /** Escaparate: índice único por (tienda|nombre), común a todos los nichos. */
  en_escaparate: boolean;
  /** Ficha de TikTok Shop, pegada en lote desde la web del curso. */
  product_url: string;
  /** Su web lo marca "SIN STOCK". */
  sin_stock: boolean;
  /** Su ficha ofrece pago a plazos. Sale de la captura al extraer los textos
   *  (mismo criterio que el POV BOF) y decide qué prompt de vídeo se usa. */
  plazos?: boolean;
  /** `true`/`false` si se corrigió a mano; `null` si manda la ficha. */
  plazos_manual?: boolean | null;
  /** Lo que paga hoy el comprador, leído de la captura. */
  precio?: string;
  /** El guion que escribió la IA para ESTE modo con el prompt del curso:
   *  `guion` es el bloque entero que se pega en el generador y `guion_dice`,
   *  solo lo que se oye (lo que tiene tope de caracteres). */
  guion?: string;
  /** Un bloque por clip: dos en el formato de calle dividido, donde cada clip
   *  dice su mitad. `guion` es el primero. */
  guiones?: string[];
  /** Qué huecos tienen ya su clip subido, esperando al resto (1, 2…). */
  clips_subidos?: number[];
  /** Los colores que nombra el guion (formato de la tienda), el puesto el
   *  último: son los que se recolorean al montar. */
  guion_colores?: string[];
  /** Hay captura del selector de colores subida (formato de la tienda). */
  variantes_foto?: boolean;
  /** Nombres leídos de esa captura (exactos de TikTok), antes del guion. */
  variantes_colores?: string[];
  /** Colores del guion que ya tienen su foto subida para los cortes. */
  colores_con_foto?: string[];
  /** Fotos del producto en otros colores que trajo el ZIP (para Flow). */
  fotos_color_producto?: number;
  /** Variantes con miniatura recortada de la captura (foto para Flow). */
  miniaturas_variantes?: string[];
  guion_dice?: string;
  guion_at?: number;
  uploaded: boolean;
  /** Cuándo se marcó como subido (epoch). 0 = no consta. */
  uploaded_at: number;
  /** Vendió con esta prenda. El ranking es por usuario y común a los nichos. */
  sold?: boolean;
  video_path: string | null;
  video_listo_at: number;
  /** Hay un montaje de esta prenda en cola o en curso. */
  montando: boolean;
}

export interface PrendasListResponse {
  carpeta: string;
  items: PrendaItem[];
  textos_extraidos: boolean;
  montando: boolean;
}

export interface VideoRopaUploadResponse {
  ok: boolean;
  job_id: string | null;
  message: string;
}
