"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  Gorra,
  GorrasCarpeta,
  GorrasListResponse,
  GorrasPrompt,
} from "@/lib/types/nichoGorras";

const ROOT = "/api/v1/nicho-gorras";

export const gorrasKeys = {
  all: ["nicho-gorras"] as const,
  prompts: () => [...gorrasKeys.all, "prompts"] as const,
  carpetas: () => [...gorrasKeys.all, "carpetas"] as const,
  gorras: (carpeta: string) => [...gorrasKeys.all, "gorras", carpeta] as const,
};

export function useGorrasPrompts() {
  return useQuery<GorrasPrompt[]>({
    queryKey: gorrasKeys.prompts(),
    queryFn: async () => (await api.get<{ items: GorrasPrompt[] }>(`${ROOT}/prompts`)).items ?? [],
    staleTime: Infinity,
  });
}

export function useGorrasCarpetas() {
  return useQuery<GorrasCarpeta[]>({
    queryKey: gorrasKeys.carpetas(),
    queryFn: async () => (await api.get<{ items: GorrasCarpeta[] }>(`${ROOT}/carpetas`)).items ?? [],
    staleTime: Infinity,
  });
}

export function useGorras(carpeta: string) {
  return useQuery<GorrasListResponse>({
    queryKey: gorrasKeys.gorras(carpeta),
    queryFn: () =>
      api.get<GorrasListResponse>(`${ROOT}/gorras?carpeta=${encodeURIComponent(carpeta)}`),
    enabled: Boolean(carpeta),
  });
}

export function useExtraerTextosGorras() {
  const qc = useQueryClient();
  return useMutation<GorrasListResponse, Error, string>({
    mutationFn: (carpeta) =>
      api.post<GorrasListResponse>(
        `${ROOT}/extraer-textos?carpeta=${encodeURIComponent(carpeta)}`, {},
      ),
    onSuccess: (d) => qc.setQueryData(gorrasKeys.gorras(d.carpeta), d),
  });
}

function base(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}
function keyQs(): string {
  const k = process.env.NEXT_PUBLIC_API_KEY;
  return k ? `&api_key=${encodeURIComponent(k)}` : "";
}

export function gorraFotoUrl(fileId: string): string {
  return `${base()}${ROOT}/foto?file_id=${encodeURIComponent(fileId)}${keyQs()}`;
}

export function gorraFotoLimpiaUrl(carpeta: string, producto: string): string {
  return `${base()}${ROOT}/foto-limpia?carpeta=${encodeURIComponent(
    carpeta,
  )}&producto=${encodeURIComponent(producto)}${keyQs()}`;
}

export type { Gorra };
