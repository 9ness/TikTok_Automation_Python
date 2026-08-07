"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const ROOT = "/api/v1/nicho-creativos";

export const creativosKeys = {
  all: ["nicho-creativos"] as const,
  prompt: () => [...creativosKeys.all, "prompt"] as const,
  folders: (source: string) => [...creativosKeys.all, "folders", source] as const,
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

export function usePromptCreativos() {
  return useQuery<PromptCreativos>({
    queryKey: creativosKeys.prompt(),
    queryFn: () => api.get<PromptCreativos>(`${ROOT}/prompt`),
    staleTime: Infinity,
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
