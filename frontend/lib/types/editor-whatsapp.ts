/** Tipos del bot de WhatsApp (Editor Auto). Todo tolerante: el bot puede
 *  devolver menos campos de los esperados. */

export type WaSobre<T> =
  | { configurado: false; faltan?: string[] }
  | { configurado: true; alcanzable: false; error?: string }
  | { configurado: true; alcanzable: true; datos?: T };

export interface WaPaso {
  id: string;
  titulo: string;
  ok: boolean | null;
  detalle: string;
}

export interface WaPlantilla {
  nombre: string;
  estado: string;
  categoria: string;
  idioma: string;
  motivo: string;
}

export interface WaPlantillaPropuesta {
  nombre: string;
  categoria: string;
  texto: string;
  estado: string; // sin_enviar | PENDING | APPROVED | REJECTED
}

export interface WaDiagnostico {
  proveedor: "meta" | "360dialog";
  listo: boolean;
  faltan: string[];
  pasos: WaPaso[];
  numero: { telefono: string; nombre: string; calidad: string; en_app: boolean | null } | null;
  webhook: { url: string; verificado: number; ultimo_recibido: number };
  plantillas: WaPlantilla[];
  plantillas_propuestas: WaPlantillaPropuesta[];
  mes: { enviados: number; tope: number };
  horario: string;
  abierto_ahora: boolean;
  ia: { activa: boolean; modelo: string };
}

export interface WaConversacion {
  wa_id: string;
  nombre: string;
  ultimo_entrante: number;
  pausado_hasta: number;
  motivo_pausa: string;
  mensajes: number;
  ultimo_texto: string;
}

export interface WaMensaje {
  direccion: "entra" | "sale" | "eco";
  origen: string;
  tipo: string;
  texto: string;
  ts: number;
}

export interface WaPlantillasResultado {
  enviadas: string[];
  ya_estaban: string[];
  errores: { nombre: string; error: string }[];
}

export interface WaOk {
  ok: boolean;
  error?: string;
}
