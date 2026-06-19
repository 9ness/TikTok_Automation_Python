"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  MatchAutoFetchRequest,
  MatchAutoFetchResponse,
  MatchPhotoFoldersResponse,
  MatchPhotoListResponse,
  MatchPhotoSaveRequest,
  MatchPhotoSaveResponse,
  MatchPhotoSearchRequest,
  MatchPhotoSearchResponse,
  MatchTeamsForDateResponse,
} from "@/lib/types/creator-reward-photos";

const ROOT = "/api/v1/creator-reward/match-photos";

export const matchPhotosKeys = {
  all: ["cr-match-photos"] as const,
  folders: () => [...matchPhotosKeys.all, "folders"] as const,
  team: (team: string) => [...matchPhotosKeys.all, "team", team] as const,
  teamsForDate: (date: string) => [...matchPhotosKeys.all, "teams", date] as const,
};

// URL absoluta para <img src> de una foto ya guardada (sirve el backend, sin auth).
export function matchPhotoFileUrl(path: string): string {
  return `${api.baseUrl}${path}`;
}

export function useSearchMatchPhotos() {
  return useMutation<MatchPhotoSearchResponse, Error, MatchPhotoSearchRequest>({
    mutationFn: (input) =>
      api.post<MatchPhotoSearchResponse>(`${ROOT}/search`, input),
  });
}

export function useMatchPhotoFolders() {
  return useQuery<MatchPhotoFoldersResponse>({
    queryKey: matchPhotosKeys.folders(),
    queryFn: () => api.get<MatchPhotoFoldersResponse>(`${ROOT}/folders`),
  });
}

export function useMatchPhotos(team: string | null) {
  return useQuery<MatchPhotoListResponse>({
    queryKey: matchPhotosKeys.team(team ?? ""),
    queryFn: () =>
      api.get<MatchPhotoListResponse>(`${ROOT}/list?team=${encodeURIComponent(team ?? "")}`),
    enabled: Boolean(team),
  });
}

export function useSaveMatchPhoto() {
  const qc = useQueryClient();
  return useMutation<MatchPhotoSaveResponse, Error, MatchPhotoSaveRequest>({
    mutationFn: (input) =>
      api.post<MatchPhotoSaveResponse>(`${ROOT}/save`, input),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: matchPhotosKeys.team(res.team) });
      qc.invalidateQueries({ queryKey: matchPhotosKeys.folders() });
    },
  });
}

export function useMatchTeamsForDate(date: string | null) {
  return useQuery<MatchTeamsForDateResponse>({
    queryKey: matchPhotosKeys.teamsForDate(date ?? ""),
    queryFn: () =>
      api.get<MatchTeamsForDateResponse>(
        `${ROOT}/teams?date=${encodeURIComponent(date ?? "")}`,
      ),
    enabled: Boolean(date),
  });
}

export function useAutoFetchMatchPhoto() {
  return useMutation<MatchAutoFetchResponse, Error, MatchAutoFetchRequest>({
    mutationFn: (input) =>
      api.post<MatchAutoFetchResponse>(`${ROOT}/auto-fetch`, input),
  });
}

export function useDeleteMatchPhoto() {
  const qc = useQueryClient();
  return useMutation<void, Error, { team: string; filename: string }>({
    mutationFn: ({ team, filename }) =>
      api.del<void>(
        `${ROOT}/photo?team=${encodeURIComponent(team)}&filename=${encodeURIComponent(filename)}`,
      ),
    onSuccess: (_void, { team }) => {
      qc.invalidateQueries({ queryKey: matchPhotosKeys.team(team) });
      qc.invalidateQueries({ queryKey: matchPhotosKeys.folders() });
    },
  });
}
