"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Un producto con venta en un mes (lo que enseña «Productos · TikTok Shop»). */
export interface ProductoMes {
  titulo: string;
  pais: string;
  gmv: number;
  ventas: number;
  /** Tipo de producto (suplementos, hogar…), puesto al leerlo. */
  tipo?: string;
}

export interface MesStats {
  mes: string; // "2026-06"
  gmv: number;
  ventas: number;
  impresiones: number;
  clics: number;
  comision?: number;
  gmv_comision?: number;
  art_comision?: number;
  base_comision?: number;
  productos?: ProductoMes[];
  /** Pedidos de afiliados del mes por origen («Vídeo», «Carrusel», «Anuncios»…). */
  origen?: Record<string, OrigenStats>;
}

export interface OrigenStats {
  pedidos: number;
  importe: number;
  comision: number;
  /** Lo mismo, solo pedidos de España (el resto es de fuera). */
  es_pedidos?: number;
  es_importe?: number;
  /** Pedidos «No apto» (pago fallido, devolución…): no cuentan en importe ni comisión. */
  no_aptos?: number;
}

/** Un vídeo o carrusel con ventas (Pedidos de afiliados, agrupado por caption). */
export interface ContenidoStats {
  caption: string;
  tipo: string;
  pedidos: number;
  importe: number;
  comision: number;
}

export interface DiaStats {
  fecha: string; // "2026-10-01"
  impresiones?: number;
  clics?: number;
  gmv?: number;
  ventas?: number;
  visualizaciones?: number;
}

export interface Estadisticas {
  cuenta?: string;
  actualizado?: string;
  meses?: MesStats[];
  dias?: DiaStats[];
  notas?: string[];
  /** Rango de los pedidos leídos, p. ej. "1/5 – 27/10". */
  rango_pedidos?: string;
  contenidos?: ContenidoStats[];
}

export function useEstadisticas(activo: boolean) {
  return useQuery<Estadisticas>({
    queryKey: ["estadisticas"],
    queryFn: () => api.get<Estadisticas>("/api/v1/estadisticas"),
    enabled: activo,
  });
}
