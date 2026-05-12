"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  NanoBananaPromptInput,
  NanoBananaPromptResponse,
  PhotoLocation,
  PhotoOrigin,
  PhotoType,
  PhotoUpdateInput,
  Product,
  ProductCreateInput,
  ProductListResponse,
  ProductPhoto,
  ProductUpdateInput,
  ReanalyzeResponse,
} from "@/lib/types/product";

const ROOT = "/api/v1/products";

export interface ProductsFilters {
  limit?: number;
  offset?: number;
  category?: string;
  include_deleted?: boolean;
}

export const productKeys = {
  all: ["products"] as const,
  list: (filters?: ProductsFilters) => [...productKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...productKeys.all, "detail", id] as const,
};

function buildQueryString(filters?: ProductsFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  if (filters.category) params.set("category", filters.category);
  if (filters.include_deleted) params.set("include_deleted", "true");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useProducts(
  filters?: ProductsFilters,
  options?: Omit<UseQueryOptions<ProductListResponse>, "queryKey" | "queryFn">,
) {
  return useQuery<ProductListResponse>({
    queryKey: productKeys.list(filters),
    queryFn: () => api.get<ProductListResponse>(`${ROOT}${buildQueryString(filters)}`),
    ...options,
  });
}

export function useProduct(id: string | null | undefined) {
  return useQuery<Product>({
    queryKey: productKeys.detail(id ?? ""),
    queryFn: () => api.get<Product>(`${ROOT}/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation<Product, Error, ProductCreateInput>({
    mutationFn: (input) => api.post<Product>(ROOT, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useUpdateProduct(id: string) {
  const qc = useQueryClient();
  return useMutation<Product, Error, ProductUpdateInput>({
    mutationFn: (input) => api.put<Product>(`${ROOT}/${id}`, input),
    onSuccess: (data) => {
      qc.setQueryData(productKeys.detail(id), data);
      qc.invalidateQueries({ queryKey: productKeys.all });
    },
  });
}

export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.del<void>(`${ROOT}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export interface UploadPhotoInput {
  productId: string;
  file: File;
  location: PhotoLocation;
  type?: PhotoType;
  origin?: PhotoOrigin;
  url_origin?: string;
}

export function useUploadPhoto() {
  const qc = useQueryClient();
  return useMutation<ProductPhoto, Error, UploadPhotoInput>({
    mutationFn: async ({ productId, file, location, type, origin, url_origin }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("location", location);
      if (type) fd.append("type", type);
      if (origin) fd.append("origin", origin);
      if (url_origin) fd.append("url_origin", url_origin);
      return api.post<ProductPhoto>(`${ROOT}/${productId}/photos`, fd);
    },
    onSuccess: (_data, { productId }) => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useDeletePhoto() {
  const qc = useQueryClient();
  return useMutation<void, Error, { productId: string; photoId: string }>({
    mutationFn: ({ productId, photoId }) =>
      api.del<void>(`${ROOT}/${productId}/photos/${encodeURIComponent(photoId)}`),
    onSuccess: (_data, { productId }) => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useUpdatePhoto() {
  const qc = useQueryClient();
  return useMutation<
    ProductPhoto,
    Error,
    { productId: string; photoId: string; payload: PhotoUpdateInput }
  >({
    mutationFn: ({ productId, photoId, payload }) =>
      api.put<ProductPhoto>(
        `${ROOT}/${productId}/photos/${encodeURIComponent(photoId)}`,
        payload,
      ),
    onSuccess: (_data, { productId }) => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useReanalyzeProduct() {
  const qc = useQueryClient();
  return useMutation<ReanalyzeResponse, Error, string>({
    mutationFn: (productId) => api.post<ReanalyzeResponse>(`${ROOT}/${productId}/analyze`),
    onSuccess: (_data, productId) => {
      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
    },
  });
}

export function useGenerateNanoBananaPrompt() {
  return useMutation<
    NanoBananaPromptResponse,
    Error,
    { productId: string; payload: NanoBananaPromptInput }
  >({
    mutationFn: ({ productId, payload }) =>
      api.post<NanoBananaPromptResponse>(`${ROOT}/${productId}/nano-banana-prompt`, payload),
  });
}
