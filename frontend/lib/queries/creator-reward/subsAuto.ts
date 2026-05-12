"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  SubsAutoEnqueueRequest,
  SubsAutoEnqueueResponse,
  SubsAutoStyleConfig,
  SubsAutoTranscribeResponse,
} from "@/lib/types/creator-reward";

const ROOT = "/api/v1/creator-reward/subs-auto";

export interface SubsAutoPresetItem {
  name: string;
  config: SubsAutoStyleConfig;
}
export interface SubsAutoFontItem {
  label: string;
  path: string;
}
export interface SubsAutoHighlightModeItem {
  label: string;
  value: SubsAutoStyleConfig["highlight_mode"];
}

export function useSubsAutoPresets() {
  return useQuery<{ items: SubsAutoPresetItem[] }>({
    queryKey: ["subs-auto", "presets"],
    queryFn: () => api.get(`${ROOT}/presets`),
    staleTime: Infinity, // catálogo estático
  });
}

export function useSubsAutoFonts() {
  return useQuery<{ items: SubsAutoFontItem[] }>({
    queryKey: ["subs-auto", "fonts"],
    queryFn: () => api.get(`${ROOT}/fonts`),
    staleTime: Infinity,
  });
}

export function useSubsAutoHighlightModes() {
  return useQuery<{ items: SubsAutoHighlightModeItem[] }>({
    queryKey: ["subs-auto", "highlight-modes"],
    queryFn: () => api.get(`${ROOT}/highlight-modes`),
    staleTime: Infinity,
  });
}

export function buildSubsAutoFrameUrl(inputPath: string, second: number): string {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = new URLSearchParams({
    input_path: inputPath,
    second: second.toFixed(2),
  });
  if (apiKey) qs.append("api_key", apiKey);
  return `${api.baseUrl}${ROOT}/frame?${qs.toString()}`;
}

export interface TranscribeInput {
  file: File;
  model_size: string;
  language: string | null;
  audio_type: string;
  reference_text?: string | null;
  /** Callback opcional invocado en cada evento de progreso del stream NDJSON. */
  onProgress?: (frac: number, msg: string) => void;
}

/** Lee el stream NDJSON de `POST /transcribe` y resuelve con el evento
 *  `{type:"result", ...}`. Los eventos `progress` van al callback; un evento
 *  `error` se traduce a Error rechazado. */
async function streamTranscribe(
  url: string,
  fd: FormData,
  onProgress?: (frac: number, msg: string) => void,
): Promise<SubsAutoTranscribeResponse> {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const res = await fetch(url, {
    method: "POST",
    body: fd,
    headers: apiKey ? { "X-API-Key": apiKey } : undefined,
  });
  if (!res.ok) {
    const txt = await res.text();
    let msg = txt;
    try {
      const j = JSON.parse(txt);
      msg = j.message || j.detail || txt;
    } catch {
      /* not json */
    }
    throw new Error(msg || `HTTP ${res.status}`);
  }
  if (!res.body) throw new Error("Respuesta sin body — stream no soportado.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: SubsAutoTranscribeResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Procesar líneas completas; mantener el sobrante (línea parcial).
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let ev: { type: string; [k: string]: unknown };
      try {
        ev = JSON.parse(trimmed);
      } catch {
        continue;
      }
      if (ev.type === "progress") {
        onProgress?.(Number(ev.frac) || 0, String(ev.msg ?? ""));
      } else if (ev.type === "error") {
        throw new Error(String(ev.message ?? "Transcripción falló."));
      } else if (ev.type === "result") {
        result = ev as unknown as SubsAutoTranscribeResponse;
      }
    }
  }
  if (!result) throw new Error("Stream cerrado sin resultado final.");
  return result;
}

export function useTranscribe() {
  return useMutation<SubsAutoTranscribeResponse, Error, TranscribeInput>({
    mutationFn: async (input) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("model_size", input.model_size);
      if (input.language) fd.append("language", input.language);
      fd.append("audio_type", input.audio_type);
      if (input.reference_text) fd.append("reference_text", input.reference_text);
      return streamTranscribe(
        `${api.baseUrl}${ROOT}/transcribe`,
        fd,
        input.onProgress,
      );
    },
  });
}

export function useEnqueueSubsAuto() {
  return useMutation<SubsAutoEnqueueResponse, Error, SubsAutoEnqueueRequest>({
    mutationFn: (input) =>
      api.post<SubsAutoEnqueueResponse>(`${ROOT}/enqueue`, input),
  });
}
