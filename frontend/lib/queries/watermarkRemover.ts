/**
 * Hook para `POST /api/v1/tiktok-shop/watermark-remover/process`.
 * Sube un vídeo, lo procesa vía ffmpeg `delogo` y devuelve el path
 * relativo del output sin marca.
 */

import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type WatermarkType = "veo_flow" | "gemini_chat" | "auto";
export type WatermarkQuality = "fast" | "magic";

export interface WatermarkRemoverResponse {
  output_path: string;
  output_filename: string;
  output_size_bytes: number;
  processing_seconds: number;
  watermark_type: string;
  quality: string;
  cost_usd: number;
  drive_path: string | null;
  drive_subdir: string | null;
}

export interface WatermarkRemoverInput {
  file: File;
  watermark_type: WatermarkType;
  quality: WatermarkQuality;
  user_id?: string | null;
  product_id?: string | null;
}

export function useRemoveWatermark() {
  return useMutation<WatermarkRemoverResponse, Error, WatermarkRemoverInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("watermark_type", input.watermark_type);
      fd.append("quality", input.quality);
      if (input.user_id) fd.append("user_id", input.user_id);
      if (input.product_id) fd.append("product_id", input.product_id);
      return api.post<WatermarkRemoverResponse>(
        "/api/v1/tiktok-shop/watermark-remover/process",
        fd,
      );
    },
  });
}

/** Construye URL de descarga (incluye api_key). */
export function watermarkRemoverFileUrl(outputPath: string): string {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const params = new URLSearchParams({ path: outputPath });
  if (apiKey) params.set("api_key", apiKey);
  return `${api.baseUrl}/api/v1/tiktok-shop/watermark-remover/file?${params.toString()}`;
}
