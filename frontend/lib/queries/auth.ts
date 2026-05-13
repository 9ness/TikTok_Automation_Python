"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface MeResponse {
  username: string | null;
  available_users: string[];
}

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<MeResponse>(`/api/v1/auth/me`),
    staleTime: 60 * 1000,
    refetchOnWindowFocus: true,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation<
    { username: string; exp: number },
    Error,
    { username: string; password: string }
  >({
    mutationFn: (body) =>
      api.post<{ username: string; exp: number }>(`/api/v1/auth/login`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => api.post<void>(`/api/v1/auth/logout`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}
