"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  ConstruccionPovEnqueueRequest,
  ConstruccionPovEnqueueResponse,
} from "@/lib/types/creator-reward";

const ROOT = "/api/v1/creator-reward/construccion-pov";

export const povPresetKeys = {
  all: ["construccion-pov", "presets"] as const,
  list: () => [...povPresetKeys.all, "list"] as const,
  one: (name: string) => [...povPresetKeys.all, "one", name] as const,
};

export interface PovPreset {
  name: string;
  config: Record<string, unknown>;
}

export function useConstruccionPovPresets() {
  return useQuery<{ items: string[]; total: number }>({
    queryKey: povPresetKeys.list(),
    queryFn: () =>
      api.get<{ items: string[]; total: number }>(`${ROOT}/presets`),
  });
}

export function useConstruccionPovPreset(name: string | null) {
  return useQuery<PovPreset>({
    queryKey: povPresetKeys.one(name ?? ""),
    queryFn: () =>
      api.get<PovPreset>(`${ROOT}/presets/${encodeURIComponent(name!)}`),
    enabled: Boolean(name),
    retry: false,
  });
}

export function useSaveConstruccionPovPreset() {
  const qc = useQueryClient();
  return useMutation<
    PovPreset,
    Error,
    { name: string; config: Record<string, unknown> }
  >({
    mutationFn: ({ name, config }) =>
      api.put<PovPreset>(`${ROOT}/presets/${encodeURIComponent(name)}`, config),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: povPresetKeys.all });
    },
  });
}

export function useDeleteConstruccionPovPreset() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) =>
      api.del<void>(`${ROOT}/presets/${encodeURIComponent(name)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: povPresetKeys.all });
    },
  });
}

// `file` o `input_path_relative` son mutuamente excluyentes — al menos uno
// debe estar presente. Cuando se usa el flujo semi-automático, primero se
// llama a `useGenerateScript` (que sube el file) y después a `useEnqueue`
// con `input_path_relative` para no resubir el archivo.
export interface ConstruccionPovEnqueueRequestWithPath
  extends Omit<ConstruccionPovEnqueueRequest, "file"> {
  file?: File;
  input_path_relative?: string;
}

export function useEnqueueConstruccionPov() {
  return useMutation<
    ConstruccionPovEnqueueResponse,
    Error,
    ConstruccionPovEnqueueRequestWithPath
  >({
    mutationFn: async (input) => {
      const fd = new FormData();
      if (input.file) fd.append("file", input.file);
      if (input.input_path_relative)
        fd.append("input_path_relative", input.input_path_relative);
      fd.append("voice_id", input.voice_id);
      fd.append("font_path", input.font_path);
      fd.append("highlight_mode", input.highlight_mode);
      fd.append("highlight_color", input.highlight_color);
      fd.append("text_color", input.text_color);
      fd.append("stroke_color", input.stroke_color);
      fd.append("stroke_width", String(input.stroke_width));
      fd.append("case_mode", input.case_mode);
      fd.append("font_scale", String(input.font_scale));
      fd.append("max_words", String(input.max_words));
      fd.append("y_position", String(input.y_position));
      fd.append("pill_enabled", String(input.pill_enabled));
      fd.append("max_width", String(input.max_width));
      fd.append("sync_offset", String(input.sync_offset));
      fd.append("upscale_1080p", String(input.upscale_1080p));
      fd.append("saturation", String(input.saturation));
      fd.append("pulse_zoom", String(input.pulse_zoom));
      fd.append("mirror", String(input.mirror));
      fd.append("whisper_model_size", input.whisper_model_size);
      fd.append("quality_label", input.quality_label);
      fd.append("gemini_model", input.gemini_model);
      fd.append("original_audio_volume", String(input.original_audio_volume));
      fd.append("narration_volume", String(input.narration_volume));
      if (input.manual_script && input.manual_script.trim()) {
        fd.append("manual_script", input.manual_script);
      }
      return api.post<ConstruccionPovEnqueueResponse>(`${ROOT}/enqueue`, fd);
    },
  });
}

// ---------------------------------------------------------------------------
// Semi-auto: generar guion sin encolar (paso 1) → revisar → enqueue (paso 2)
// ---------------------------------------------------------------------------
export interface GenerateScriptResponse {
  script: string;
  target_chars: number;
  duration_seconds: number;
  input_path_relative: string;
  gemini_model: string;
}

export interface GenerateScriptInput {
  file?: File;
  input_path_relative?: string;
  gemini_model: "gemini-2.5-flash" | "gemini-2.5-pro";
}

export function useGenerateScript() {
  return useMutation<GenerateScriptResponse, Error, GenerateScriptInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      if (input.file) fd.append("file", input.file);
      if (input.input_path_relative)
        fd.append("input_path_relative", input.input_path_relative);
      fd.append("gemini_model", input.gemini_model);
      return api.post<GenerateScriptResponse>(`${ROOT}/generate-script`, fd);
    },
  });
}

// ---------------------------------------------------------------------------
// Preview prompt — para que el usuario pegue en un Gem custom de Gemini
// ---------------------------------------------------------------------------
export interface PovPromptPreview {
  system_prompt: string;
  target_chars: number;
  target_seconds: number;
}

export function usePovPromptPreview(durationSeconds: number, enabled = true) {
  return useQuery<PovPromptPreview>({
    queryKey: ["construccion-pov", "preview-prompt", durationSeconds],
    queryFn: () =>
      api.get<PovPromptPreview>(
        `${ROOT}/preview-prompt?duration_seconds=${durationSeconds}`,
      ),
    enabled,
    staleTime: 60_000,
  });
}
