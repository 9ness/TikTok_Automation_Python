"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface MeResponse {
  username: string;
  available_users: string[];
}

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<MeResponse>(`/api/v1/auth/me`),
    staleTime: 5 * 60 * 1000,
  });
}
