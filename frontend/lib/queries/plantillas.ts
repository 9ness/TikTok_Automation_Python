"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const ROOT = "/api/v1/plantillas";

export interface Plantilla {
  id: string;
  titulo: string;
  /** Para qué sirve y qué hay que rellenar antes de mandarla. */
  nota: string;
  texto: string;
}

interface Respuesta {
  ok: boolean;
  items: Plantilla[];
}

export const plantillasKeys = { all: ["plantillas"] as const };

export function usePlantillas() {
  return useQuery<Plantilla[]>({
    queryKey: plantillasKeys.all,
    queryFn: async () => (await api.get<Respuesta>(ROOT)).items ?? [],
  });
}

/** Guarda la lista ENTERA: crear, editar, reordenar y borrar pasan por aquí.
 *
 *  Son cuatro textos, así que mandar el conjunto sale más barato que llevar un
 *  índice y sincronizar borrados. La respuesta trae la lista ya limpia por el
 *  servidor, y con ella se pisa la caché — sin invalidar, que sería otra vuelta.
 */
export function useGuardarPlantillas() {
  const qc = useQueryClient();
  return useMutation<Plantilla[], Error, Plantilla[]>({
    mutationFn: async (items) =>
      (await api.post<Respuesta>(ROOT, { items })).items ?? [],
    onSuccess: (items) => qc.setQueryData(plantillasKeys.all, items),
  });
}

/** Vuelve a las plantillas de fábrica (borra las del operador). */
export function useRestaurarPlantillas() {
  const qc = useQueryClient();
  return useMutation<Plantilla[], Error, void>({
    mutationFn: async () => (await api.del<Respuesta>(ROOT)).items ?? [],
    onSuccess: (items) => qc.setQueryData(plantillasKeys.all, items),
  });
}
