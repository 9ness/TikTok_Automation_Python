"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Estado del Chrome remoto del VPS (Flow / Magnific sin el PC encendido). */
export interface EstadoNavegador {
  encendido: boolean;
  chrome_mb: number;
  disponible_mb: number;
  /** Segundos sin nadie conectado; a los `autoapagado_min` se apaga solo. */
  inactivo_s: number;
  autoapagado_min: number;
  pestanas: { titulo: string; host: string }[];
}

const KEY = ["navegador", "estado"];

export function useEstadoNavegador(activo = true) {
  return useQuery<EstadoNavegador>({
    queryKey: KEY,
    queryFn: () => api.get<EstadoNavegador>("/api/v1/navegador/estado"),
    enabled: activo,
    refetchInterval: 10_000,
    retry: false,
  });
}

export function useAccionNavegador() {
  const qc = useQueryClient();
  return useMutation<EstadoNavegador, Error, "encender" | "apagar">({
    mutationFn: (accion) => api.post<EstadoNavegador>(`/api/v1/navegador/${accion}`, {}),
    onSuccess: (estado) => qc.setQueryData(KEY, estado),
  });
}

/** La contraseña de la pantalla remota (solo admin). */
export async function pedirClaveNavegador(): Promise<string> {
  const r = await api.get<{ clave: string }>("/api/v1/navegador/clave");
  return r.clave;
}
