"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Un día del contador: lo publicado ese día (lo apuntan los agentes). */
export interface DiaSubidas {
  fecha: string; // "2026-11-01"
  videos: number;
  carruseles: number;
  nota: string;
  actualizado: string;
}

export interface TotalesSubidas {
  videos: number;
  carruseles: number;
  total: number;
  dias_con_subida: number;
  /** Días del mes ya empezados (todo el mes si es pasado; hasta hoy si es el actual). */
  dias_transcurridos: number;
  media_dia: { videos: number; carruseles: number; total: number };
}

export interface Subidas {
  usuario: string;
  mes: string; // "2026-11"
  dias: DiaSubidas[];
  totales: TotalesSubidas;
}

/** `usuario` solo lo usa el admin para mirar el de otro. */
export function useSubidas(mes: string, usuario: string, activo: boolean) {
  const qs = new URLSearchParams({ mes });
  if (usuario) qs.set("usuario", usuario);
  return useQuery<Subidas>({
    queryKey: ["subidas", mes, usuario],
    queryFn: () => api.get<Subidas>(`/api/v1/subidas?${qs.toString()}`),
    enabled: activo && Boolean(mes),
  });
}
