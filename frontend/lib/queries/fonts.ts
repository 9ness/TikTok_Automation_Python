"use client";

import type React from "react";
import { useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface FontItem {
  name: string;
  path: string;
  filename: string;
  source: "bundled" | "system";
}

const ROOT = "/api/v1/fonts";

/** URL absoluta del blob de la fuente bundled (con api_key en query). */
export function buildFontFileUrl(filename: string): string {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = new URLSearchParams();
  if (apiKey) qs.append("api_key", apiKey);
  const tail = qs.toString();
  return `${api.baseUrl}${ROOT}/file/${encodeURIComponent(filename)}${tail ? `?${tail}` : ""}`;
}

/** Sanitiza un filename a un identificador CSS válido para `font-family`. */
function fontFamilyId(filename: string): string {
  const stem = filename.replace(/\.[^./\\]+$/, "");
  return `nb-${stem.replace(/[^A-Za-z0-9_-]+/g, "_")}`;
}

/** Registra (idempotente) un `@font-face` para la fuente bundled e
 *  inyecta el `<style>` en `document.head`. Devuelve el nombre de familia
 *  CSS resultante.
 *
 *  CRÍTICO: declaramos `font-weight: 1 1000` (rango ancho) para que
 *  cualquier `font-weight` en CSS se mapee al único archivo TTF sin que
 *  el navegador intente sintetizar faux-bold/faux-italic. El render real
 *  del backend usa el TTF tal cual con PIL — sintetizar en preview rompe
 *  la fidelidad WYSIWYG. */
function registerBundledFont(filename: string): string {
  const family = fontFamilyId(filename);
  if (typeof document === "undefined") return family;
  const id = `font-face-${family}`;
  if (document.getElementById(id)) return family;
  const url = buildFontFileUrl(filename);
  const style = document.createElement("style");
  style.id = id;
  style.textContent = `@font-face{font-family:'${family}';src:url('${url}') format('truetype'),url('${url}') format('opentype');font-weight:1 1000;font-style:normal;font-display:swap;}`;
  document.head.appendChild(style);
  return family;
}

/** CSS de defensa-en-profundidad: aplicar al elemento que renderiza la
 *  fuente para impedir cualquier síntesis (faux bold / faux italic). Útil
 *  para fuentes de sistema cuyo TTF en el OS solo trae una variante y el
 *  navegador podría engordar artificialmente. */
export const FONT_SYNTHESIS_NONE: React.CSSProperties = {
  fontSynthesis: "none",
} as React.CSSProperties;

/** Devuelve el `font-family` CSS para una fuente del registry. Para
 *  `bundled` carga la fuente via `@font-face` desde el backend (efecto
 *  side-effecty pero idempotente). Para `system` confía en que el OS la
 *  tiene; cae a stack común. */
export function useFontFamily(entry: FontItem | null | undefined): string {
  const filename = entry?.source === "bundled" ? entry.filename : null;
  useEffect(() => {
    if (filename) registerBundledFont(filename);
  }, [filename]);

  return useMemo(() => {
    if (!entry) return "Impact, 'Arial Black', sans-serif";
    if (entry.source === "bundled") {
      return `'${fontFamilyId(entry.filename)}', Impact, 'Arial Black', sans-serif`;
    }
    // System: usa el nombre tal cual (Impact, Arial Black, etc.) con fallbacks.
    return `'${entry.name}', Impact, 'Arial Black', sans-serif`;
  }, [entry]);
}

/** Helper: encuentra la entrada del registry por path. */
export function useFontByPath(path: string): FontItem | null {
  const fonts = useFonts();
  return useMemo(() => {
    const items = fonts.data?.items ?? [];
    return items.find((f) => f.path === path) ?? null;
  }, [fonts.data, path]);
}

export function useFonts() {
  return useQuery<{ items: FontItem[] }>({
    queryKey: ["fonts"],
    queryFn: () => api.get(`${ROOT}`),
    staleTime: 30_000,
  });
}

export function useUploadFont() {
  const qc = useQueryClient();
  return useMutation<FontItem, Error, File>({
    mutationFn: async (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post<FontItem>(`${ROOT}/upload`, fd);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fonts"] });
      // El endpoint legacy /subs-auto/fonts también delega aquí.
      qc.invalidateQueries({ queryKey: ["subs-auto", "fonts"] });
    },
  });
}

export function useDeleteFont() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (filename) =>
      api.del<void>(`${ROOT}/${encodeURIComponent(filename)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fonts"] });
      qc.invalidateQueries({ queryKey: ["subs-auto", "fonts"] });
    },
  });
}
