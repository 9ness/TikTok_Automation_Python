"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Dónde vive el Chrome: el del VPS o el del PC de casa (WSL, por Tailscale). */
export type MaquinaNavegador = "vps" | "casa";

/** Estado del Chrome remoto (Flow / Magnific sin el PC del operador delante). */
export interface EstadoNavegador {
  /** Solo `casa`: el PC no responde (apagado, sin sesión de Windows o sin Tailscale). */
  sin_conexion?: boolean;
  encendido: boolean;
  chrome_mb: number;
  disponible_mb: number;
  /** Segundos sin nadie conectado; a los `autoapagado_min` se apaga solo. */
  inactivo_s: number;
  autoapagado_min: number;
  pestanas: { titulo: string; host: string }[];
}

const key = (maquina: MaquinaNavegador) => ["navegador", "estado", maquina];

export function useEstadoNavegador(activo = true, maquina: MaquinaNavegador = "vps") {
  return useQuery<EstadoNavegador>({
    queryKey: key(maquina),
    queryFn: () => api.get<EstadoNavegador>(`/api/v1/navegador/estado?maquina=${maquina}`),
    enabled: activo,
    refetchInterval: 10_000,
    retry: false,
  });
}

export function useAccionNavegador(maquina: MaquinaNavegador = "vps") {
  const qc = useQueryClient();
  return useMutation<EstadoNavegador, Error, "encender" | "apagar">({
    mutationFn: (accion) =>
      api.post<EstadoNavegador>(`/api/v1/navegador/${accion}?maquina=${maquina}`, {}),
    onSuccess: (estado) => qc.setQueryData(key(maquina), estado),
  });
}

/** La contraseña de la pantalla remota (solo admin). */
export async function pedirClaveNavegador(maquina: MaquinaNavegador = "vps"): Promise<string> {
  const r = await api.get<{ clave: string }>(`/api/v1/navegador/clave?maquina=${maquina}`);
  return r.clave;
}
