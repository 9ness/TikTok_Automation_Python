/**
 * Hook para `POST /api/v1/tiktok-shop/watermark-remover/process`.
 * Sube un vídeo, lo procesa vía ffmpeg `delogo` y devuelve el path
 * relativo del output sin marca.
 */

import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type WatermarkType = "veo_flow" | "gemini_chat" | "auto";

export interface WatermarkRemoverResponse {
  output_path: string;
  output_filename: string;
  output_size_bytes: number;
  processing_seconds: number;
  watermark_type: string;
}

export interface WatermarkRemoverInput {
  file: File;
  watermark_type: WatermarkType;
}

export function useRemoveWatermark() {
  return useMutation<WatermarkRemoverResponse, Error, WatermarkRemoverInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("watermark_type", input.watermark_type);
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
