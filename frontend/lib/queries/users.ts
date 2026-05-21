"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  PilotProgressResponse,
  User,
  UserCreateInput,
  UserListResponse,
  UserUpdateInput,
} from "@/lib/types/user";

const ROOT = "/api/v1/users";

function encodeUsername(username: string): string {
  return encodeURIComponent(username);
}

export interface UsersFilters {
  limit?: number;
  offset?: number;
  niche?: string;
  include_deleted?: boolean;
}

export const userKeys = {
  all: ["users"] as const,
  list: (filters?: UsersFilters) => [...userKeys.all, "list", filters ?? {}] as const,
  detail: (username: string) => [...userKeys.all, "detail", username] as const,
  pilot: (username: string) => [...userKeys.all, "pilot", username] as const,
};

function buildQS(filters?: UsersFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  if (filters.niche) params.set("niche", filters.niche);
  if (filters.include_deleted) params.set("include_deleted", "true");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useUsers(
  filters?: UsersFilters,
  options?: Omit<UseQueryOptions<UserListResponse>, "queryKey" | "queryFn">,
) {
  return useQuery<UserListResponse>({
    queryKey: userKeys.list(filters),
    queryFn: () => api.get<UserListResponse>(`${ROOT}${buildQS(filters)}`),
    ...options,
  });
}

export function useUser(username: string | null | undefined) {
  return useQuery<User>({
    queryKey: userKeys.detail(username ?? ""),
    queryFn: () => api.get<User>(`${ROOT}/${encodeUsername(username!)}`),
    enabled: Boolean(username),
  });
}

export function usePilotProgress(username: string | null | undefined) {
  return useQuery<PilotProgressResponse>({
    queryKey: userKeys.pilot(username ?? ""),
    queryFn: () =>
      api.get<PilotProgressResponse>(`${ROOT}/${encodeUsername(username!)}/pilot-progress`),
    enabled: Boolean(username),
    staleTime: 30 * 1000,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation<User, Error, UserCreateInput>({
    mutationFn: (input) => api.post<User>(ROOT, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: userKeys.all }),
  });
}

export function useUpdateUser(username: string) {
  const qc = useQueryClient();
  return useMutation<User, Error, UserUpdateInput>({
    mutationFn: (input) => api.put<User>(`${ROOT}/${encodeUsername(username)}`, input),
    onSuccess: (data) => {
      qc.setQueryData(userKeys.detail(username), data);
      qc.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (username) => api.del<void>(`${ROOT}/${encodeUsername(username)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: userKeys.all }),
  });
}

export function useAssignProduct(username: string) {
  const qc = useQueryClient();
  return useMutation<User, Error, { productId: string }>({
    mutationFn: ({ productId }) =>
      api.post<User>(`${ROOT}/${encodeUsername(username)}/products`, {
        product_id: productId,
      }),
    onSuccess: (data) => {
      qc.setQueryData(userKeys.detail(username), data);
    },
  });
}

export function useUnassignProduct(username: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, { productId: string }>({
    mutationFn: ({ productId }) =>
      api.del<void>(
        `${ROOT}/${encodeUsername(username)}/products/${encodeURIComponent(productId)}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.detail(username) });
    },
  });
}
