"use client";

import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  CleanModeValue,
  CopyrightEnqueueResponse,
} from "@/lib/types/creator-reward";

const ROOT = "/api/v1/creator-reward/copyright";

export interface CopyrightEnqueueInput {
  file: File;
  clean_mode: CleanModeValue;
  hook_y_pct: number; // 0.20 / 0.45 / 0.75
  hook_color: string; // hex
  upscale_1080p: boolean;
  font_path?: string | null;
}

export function useEnqueueCopyright() {
  return useMutation<CopyrightEnqueueResponse, Error, CopyrightEnqueueInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("clean_mode", input.clean_mode);
      fd.append("hook_y_pct", String(input.hook_y_pct));
      fd.append("hook_color", input.hook_color);
      fd.append("upscale_1080p", String(input.upscale_1080p));
      if (input.font_path) fd.append("font_path", input.font_path);
      return api.post<CopyrightEnqueueResponse>(`${ROOT}/enqueue`, fd);
    },
  });
}
