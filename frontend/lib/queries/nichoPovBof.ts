"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  BackupCheckResponse,
  BackupSyncResponse,
  FoldersListResponse,
  MarkCompletedRequest,
  MarkCompletedResponse,
  PhotosListResponse,
  SourcesListResponse,
} from "@/lib/types/nichoPovBof";

const ROOT = "/api/v1/nicho-pov-bof";

export const nichoPovBofKeys = {
  all: ["nicho-pov-bof"] as const,
  sources: () => [...nichoPovBofKeys.all, "sources"] as const,
  folders: (source: string) => [...nichoPovBofKeys.all, "folders", source] as const,
  photos: (source: string, folder: string) =>
    [...nichoPovBofKeys.all, "photos", source, folder] as const,
};

export function useSources() {
  return useQuery<SourcesListResponse>({
    queryKey: nichoPovBofKeys.sources(),
    queryFn: () => api.get<SourcesListResponse>(`${ROOT}/sources`),
  });
}

export function useFolders(source: string) {
  return useQuery<FoldersListResponse>({
    queryKey: nichoPovBofKeys.folders(source),
    queryFn: () =>
      api.get<FoldersListResponse>(`${ROOT}/folders?source=${encodeURIComponent(source)}`),
    enabled: Boolean(source),
  });
}

export function usePhotos(source: string, folder: string | null) {
  return useQuery<PhotosListResponse>({
    queryKey: nichoPovBofKeys.photos(source, folder ?? ""),
    queryFn: () =>
      api.get<PhotosListResponse>(
        `${ROOT}/photos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}`,
      ),
    enabled: Boolean(source && folder),
  });
}

export function useMarkCompleted(source: string) {
  const qc = useQueryClient();
  return useMutation<MarkCompletedResponse, Error, MarkCompletedRequest>({
    mutationFn: (body) => api.post<MarkCompletedResponse>(`${ROOT}/complete`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: nichoPovBofKeys.folders(source) });
    },
  });
}

/** Comprobar cambios en el Drive de origen. Bajo demanda: el listado
 *  recursivo tarda ~1 min, así que no se dispara solo al abrir la página. */
export function useBackupCheck() {
  return useMutation<BackupCheckResponse, Error, void>({
    mutationFn: () => api.get<BackupCheckResponse>(`${ROOT}/backup/check`),
  });
}

export function useBackupSync() {
  return useMutation<BackupSyncResponse, Error, { force_full: boolean }>({
    mutationFn: (body) => api.post<BackupSyncResponse>(`${ROOT}/backup/sync`, body),
  });
}

/** URL de la foto (api_key por query — un <img> no manda headers). */
export function buildPhotoUrl(source: string, folder: string, fileId: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  return `${base}${ROOT}/photo?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&file_id=${encodeURIComponent(fileId)}${qs}`;
}
