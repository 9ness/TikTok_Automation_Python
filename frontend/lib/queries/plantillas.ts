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
  /** Los huecos ya rellenados (`{CUENTA: "@micuenta"}`). */
  valores: Record<string, string>;
}

export interface PlantillasDoc {
  items: Plantilla[];
  valores: Record<string, string>;
}

export const plantillasKeys = { all: ["plantillas"] as const };

export function usePlantillas() {
  return useQuery<PlantillasDoc>({
    queryKey: plantillasKeys.all,
    queryFn: async () => {
      const r = await api.get<Respuesta>(ROOT);
      return { items: r.items ?? [], valores: r.valores ?? {} };
    },
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
  return useMutation<PlantillasDoc, Error, { items: Plantilla[]; valores?: Record<string, string> }>({
    mutationFn: async (body) => {
      const r = await api.post<Respuesta>(ROOT, body);
      return { items: r.items ?? [], valores: r.valores ?? {} };
    },
    // Se pisa la caché con lo que devuelve el servidor (ya limpio) en vez de
    // invalidar: con el guardado automático, invalidar dispararía una recarga
    // por cada pulsación y la pantalla parpadearía mientras escribes.
    onSuccess: (doc) => qc.setQueryData(plantillasKeys.all, doc),
  });
}

/** Vuelve a las plantillas de fábrica (borra las del operador). */
export function useRestaurarPlantillas() {
  const qc = useQueryClient();
  return useMutation<PlantillasDoc, Error, void>({
    mutationFn: async () => {
      const r = await api.del<Respuesta>(ROOT);
      return { items: r.items ?? [], valores: r.valores ?? {} };
    },
    onSuccess: (doc) => qc.setQueryData(plantillasKeys.all, doc),
  });
}
