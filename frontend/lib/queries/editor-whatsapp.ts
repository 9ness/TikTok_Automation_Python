"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  WaConversacion,
  WaDiagnostico,
  WaMensaje,
  WaOk,
  WaPlantillasResultado,
  WaSobre,
} from "@/lib/types/editor-whatsapp";

const ROOT = "/api/v1/editor-auto/whatsapp/bot";

export const waKeys = {
  all: ["editor-auto", "whatsapp"] as const,
  diagnostico: () => [...waKeys.all, "diagnostico"] as const,
  conversaciones: () => [...waKeys.all, "conversaciones"] as const,
  conversacion: (waId: string) => [...waKeys.all, "conversacion", waId] as const,
};

export function useWaDiagnostico() {
  return useQuery({
    queryKey: waKeys.diagnostico(),
    queryFn: () => api.get<WaSobre<WaDiagnostico>>(`${ROOT}/diagnostico`),
    refetchInterval: 30_000,
  });
}

export function useWaConversaciones(limite = 50, enabled = true) {
  return useQuery({
    queryKey: waKeys.conversaciones(),
    queryFn: () =>
      api.get<WaSobre<{ conversaciones: WaConversacion[] }>>(
        `${ROOT}/conversaciones?limite=${limite}`,
      ),
    enabled,
    refetchInterval: 20_000,
  });
}

export function useWaConversacion(waId: string | null) {
  return useQuery({
    queryKey: waKeys.conversacion(waId ?? ""),
    queryFn: () =>
      api.get<WaSobre<{ mensajes: WaMensaje[] }>>(
        `${ROOT}/conversacion?wa_id=${encodeURIComponent(waId ?? "")}`,
      ),
    enabled: !!waId,
  });
}

export function useWaPlantillas() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<WaSobre<WaPlantillasResultado>>(`${ROOT}/plantillas`),
    onSuccess: () => qc.invalidateQueries({ queryKey: waKeys.diagnostico() }),
  });
}

export function useWaSuscribir() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<WaSobre<WaOk>>(`${ROOT}/suscribir`),
    onSuccess: () => qc.invalidateQueries({ queryKey: waKeys.diagnostico() }),
  });
}

export function useWaPrueba() {
  return useMutation({
    mutationFn: (input: { telefono: string; texto?: string }) =>
      api.post<WaSobre<WaOk>>(`${ROOT}/prueba`, input),
  });
}

export function useWaPausa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { wa_id: string; minutos: number }) =>
      api.post<WaSobre<WaOk>>(`${ROOT}/pausa`, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: waKeys.conversaciones() }),
  });
}

export function useWaReanudar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { wa_id: string }) =>
      api.post<WaSobre<WaOk>>(`${ROOT}/reanudar`, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: waKeys.conversaciones() }),
  });
}
