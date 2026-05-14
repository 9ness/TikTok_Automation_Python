/**
 * Mapping programa / submódulo + extracción de info relevante por modo.
 *
 * NOTA: los componentes que renderizan los labels usan `<Icon>` del
 * mapping `MODE_ICON` / `PROGRAM_ICON` (lucide). El texto del label NO
 * lleva emoji.
 */

import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Captions,
  Crown,
  Scissors,
  ShieldOff,
  ShoppingBag,
  Trophy,
} from "lucide-react";

import type { JobMode } from "@/lib/types/queue";

export type Program = "tiktok_shop" | "creator_reward" | "editor_auto";

export const MODE_TO_PROGRAM: Record<JobMode, Program> = {
  tiktok_shop: "tiktok_shop",
  presidents: "creator_reward",
  pronosticos: "creator_reward",
  copyright: "creator_reward",
  subs_auto: "creator_reward",
  editor_auto: "editor_auto",
};

export const PROGRAM_LABEL: Record<Program, string> = {
  tiktok_shop: "TikTok Shop",
  creator_reward: "Creator Reward",
  editor_auto: "Editor Auto",
};

export const PROGRAM_ICON: Record<Program, LucideIcon> = {
  tiktok_shop: ShoppingBag,
  creator_reward: Trophy,
  editor_auto: Scissors,
};

export const SUBMODULE_LABEL: Record<JobMode, string> = {
  tiktok_shop: "Shop",
  presidents: "Presidentes",
  pronosticos: "Pronósticos",
  copyright: "Quitar Copy",
  subs_auto: "Subs Auto",
  editor_auto: "Editor Auto",
};

export const MODE_ICON: Record<JobMode, LucideIcon> = {
  tiktok_shop: ShoppingBag,
  presidents: Crown,
  pronosticos: BarChart3,
  copyright: ShieldOff,
  subs_auto: Captions,
  editor_auto: Scissors,
};

/**
 * Acento visual por programa. Borde izquierdo coloreado.
 */
export const PROGRAM_BORDER: Record<Program, string> = {
  tiktok_shop: "border-l-4 border-l-brand-cyan",
  creator_reward: "border-l-4 border-l-brand-violet",
  editor_auto: "border-l-4 border-l-emerald-500",
};

export const PROGRAM_TEXT: Record<Program, string> = {
  tiktok_shop: "text-brand-cyan",
  creator_reward: "text-brand-violet",
  editor_auto: "text-emerald-500",
};

/**
 * Extrae info relevante de `params` para mostrar bajo el título según el modo.
 */
export function describeJobParams(
  mode: JobMode,
  params: Record<string, unknown> | undefined,
): string[] {
  if (!params) return [];
  const out: string[] = [];
  switch (mode) {
    case "tiktok_shop":
      if (params.tier) out.push(`tier ${String(params.tier)}`);
      if (params.duration) out.push(`${params.duration}s`);
      if (params.resolution) out.push(String(params.resolution));
      if (params.is_shoppable) out.push("shoppable");
      break;
    case "presidents":
      if (params.title_prefix) out.push(String(params.title_prefix));
      if (params.topic) out.push(`tema: ${String(params.topic)}`);
      if (params.top_count) out.push(`top ${String(params.top_count)}`);
      break;
    case "pronosticos":
      if (params.target_date) out.push(String(params.target_date));
      if (params.version_id != null && params.version_id !== "")
        out.push(`v${String(params.version_id)}`);
      break;
    case "copyright":
      if (params.clean_mode) out.push(String(params.clean_mode));
      break;
    case "subs_auto":
      if (params.quality_label) out.push(String(params.quality_label));
      if (params.model_size) out.push(`whisper ${String(params.model_size)}`);
      break;
    case "editor_auto":
      if (params.user_name) out.push(String(params.user_name));
      if (params.tool_count) out.push(`${params.tool_count} tool(s)`);
      break;
  }
  return out;
}
