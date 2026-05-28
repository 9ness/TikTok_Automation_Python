/**
 * Hook para `POST /api/v1/tiktok-shop/watermark-remover/process`.
 * Sube un vídeo, lo procesa vía ffmpeg `delogo` y devuelve el path
 * relativo del output sin marca.
 */

import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type WatermarkType = "veo_flow" | "gemini_chat" | "auto";
export type WatermarkQuality = "fast" | "magic";

export interface WatermarkEnqueueResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
  watermark_type: string;
  quality: string;
}

export interface WatermarkRemoverInput {
  file: File;
  watermark_type: WatermarkType;
  quality: WatermarkQuality;
  user_id: string;
  product_id: string;
}

export function useEnqueueWatermarkRemoval() {
  return useMutation<WatermarkEnqueueResponse, Error, WatermarkRemoverInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("watermark_type", input.watermark_type);
      fd.append("quality", input.quality);
      fd.append("user_id", input.user_id);
      fd.append("product_id", input.product_id);
      return api.post<WatermarkEnqueueResponse>(
        "/api/v1/tiktok-shop/watermark-remover/enqueue",
        fd,
      );
    },
  });
}
