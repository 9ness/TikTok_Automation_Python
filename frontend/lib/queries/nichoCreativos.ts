"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const ROOT = "/api/v1/nicho-creativos";

export const creativosKeys = {
  all: ["nicho-creativos"] as const,
  prompt: () => [...creativosKeys.all, "prompt"] as const,
  folders: (source: string) => [...creativosKeys.all, "folders", source] as const,
  subidos: (source: string, folder: string) =>
    [...creativosKeys.all, "subidos", source, folder] as const,
};

export interface PromptCreativos {
  imagen: string;
  /** El generador no lo deduce del prompt: hay que enseñarlo al copiar. */
  formato: string;
}

export interface CarpetaCreativos {
  name: string;
  completed: boolean;
}

export interface FoldersCreativos {
  source: string;
  items: CarpetaCreativos[];
  current: string | null;
  done: number;
  total: number;
}

// Sin `Infinity`: un prompt retocado tiene que llegar al móvil (ver
// `usePrompts` del POV BOF, donde esto congeló el prompt viejo).
export function usePromptCreativos() {
  return useQuery<PromptCreativos>({
    queryKey: creativosKeys.prompt(),
    queryFn: () => api.get<PromptCreativos>(`${ROOT}/prompt`),
    staleTime: 60_000,
  });
}

/** Las carpetas son las del POV BOF (mismo Drive); lo que cambia es cuáles
 *  están hechas — un creativo no es un vídeo. */
export function useFoldersCreativos(source: string) {
  return useQuery<FoldersCreativos>({
    queryKey: creativosKeys.folders(source),
    queryFn: () =>
      api.get<FoldersCreativos>(`${ROOT}/folders?source=${encodeURIComponent(source)}`),
    enabled: Boolean(source),
  });
}

export function useCompletarCarpetaCreativos() {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean },
    Error,
    { source: string; folder: string; completed: boolean }
  >({
    mutationFn: (body) => api.post(`${ROOT}/complete`, body),
    onSuccess: (_r, v) =>
      void qc.invalidateQueries({ queryKey: creativosKeys.folders(v.source) }),
  });
}

/** Qué creativos de la carpeta ya se han publicado.
 *
 *  Va aparte de la lista de productos (que es la del POV BOF) porque es lo
 *  ÚNICO que este nicho guarda por su cuenta: "subido" allí es el vídeo y aquí
 *  el creativo, y son dos publicaciones distintas del mismo producto. */
export function useSubidosCreativos(source: string, folder: string | null) {
  return useQuery<Record<string, number>>({
    queryKey: creativosKeys.subidos(source, folder ?? ""),
    queryFn: async () =>
      (
        await api.get<{ items: string[]; horas: Record<string, number> }>(
          `${ROOT}/subidos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
            folder ?? "",
          )}`,
        )
      ).horas ?? {},
    enabled: Boolean(source && folder),
  });
}

/** Lo marca el operador a mano: aquí no hay montaje que termine. */
export function useMarcarSubidoCreativo(source: string, folder: string | null) {
  const qc = useQueryClient();
  return useMutation<
    { items: string[]; horas: Record<string, number> },
    Error,
    { producto: string; uploaded: boolean }
  >({
    mutationFn: (body) =>
      api.post<{ items: string[]; horas: Record<string, number> }>(`${ROOT}/subido`, {
        source,
        folder: folder ?? "",
        ...body,
      }),
    onSuccess: (res) => {
      qc.setQueryData(creativosKeys.subidos(source, folder ?? ""), res.horas ?? {});
      // Un creativo publicado cuenta como carrusel en el tope del día.
      void qc.invalidateQueries({ queryKey: ["cuotas", "hoy"] });
    },
  });
}
