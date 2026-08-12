"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const ROOT = "/api/v1/cuotas";

export const cuotasKeys = { hoy: () => ["cuotas", "hoy"] as const };

export interface CuotaTipo {
  /** Marcados en la app + ajuste manual. Es lo que se compara con el tope. */
  usados: number;
  marcados: number;
  ajuste: number;
  tope: number;
  aviso: number;
  avisar: boolean;
  lleno: boolean;
}

export interface CuotaHoy {
  fecha: string;
  usuario: string;
  videos: CuotaTipo;
  carruseles: CuotaTipo;
}

/** Lo publicado hoy. Se refresca solo cada minuto y al volver a la pestaña:
 *  el operador marca desde varias pantallas y la barra vive en el marco. */
export function useCuotaHoy() {
  return useQuery<CuotaHoy>({
    queryKey: cuotasKeys.hoy(),
    queryFn: () => api.get<CuotaHoy>(`${ROOT}/hoy`),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });
}

/** Fija a mano lo subido fuera de la app (o corrige el recuento). */
export function useAjustarCuota() {
  const qc = useQueryClient();
  return useMutation<CuotaHoy, Error, { tipo: "videos" | "carruseles"; valor: number }>({
    mutationFn: (body) => api.post<CuotaHoy>(`${ROOT}/ajuste`, body),
    onSuccess: (res) => qc.setQueryData(cuotasKeys.hoy(), res),
  });
}
