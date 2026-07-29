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
  CalendarDays,
  Captions,
  Crown,
  Film,
  HardDrive,
  HardHat,
  Package,
  Radar,
  Rocket,
  Scissors,
  ShieldOff,
  ShoppingBag,
  Trophy,
  Video,
} from "lucide-react";

import type { JobMode } from "@/lib/types/queue";

export type Program = "tiktok_shop" | "creator_reward" | "editor_auto" | "viralizacion";

export const MODE_TO_PROGRAM: Record<JobMode, Program> = {
  tiktok_shop: "tiktok_shop",
  tiktok_shop_watermark: "tiktok_shop",
  tiktok_shop_pack: "tiktok_shop",
  tiktok_shop_plan: "tiktok_shop",
  tiktok_shop_auto_day: "tiktok_shop",
  tiktok_shop_ready_video: "tiktok_shop",
  presidents: "creator_reward",
  pronosticos: "creator_reward",
  copyright: "creator_reward",
  subs_auto: "creator_reward",
  construccion_pov: "creator_reward",
  editor_auto: "editor_auto",
  viralizacion_batch: "viralizacion",
  nicho_pov_bof_backup: "viralizacion",
  nicho_pov_bof_video: "viralizacion",
};

export const PROGRAM_LABEL: Record<Program, string> = {
  tiktok_shop: "TikTok Shop",
  creator_reward: "Creator Reward",
  editor_auto: "Editor Auto",
  viralizacion: "Tiktok Shop AI Pro",
};

export const PROGRAM_ICON: Record<Program, LucideIcon> = {
  tiktok_shop: ShoppingBag,
  creator_reward: Trophy,
  editor_auto: Scissors,
  viralizacion: Rocket,
};

export const SUBMODULE_LABEL: Record<JobMode, string> = {
  tiktok_shop: "Shop",
  tiktok_shop_watermark: "Sin marca",
  tiktok_shop_pack: "Pack",
  tiktok_shop_plan: "Plan",
  tiktok_shop_auto_day: "Día auto",
  tiktok_shop_ready_video: "Vídeo listo",
  presidents: "Presidentes",
  pronosticos: "Pronósticos",
  copyright: "Quitar Copy",
  subs_auto: "Subs Auto",
  construccion_pov: "Construcción POV",
  editor_auto: "Editor Auto",
  viralizacion_batch: "Viralización 1K",
  nicho_pov_bof_backup: "Backup Productos España",
  nicho_pov_bof_video: "Nicho POV BOF",
};

export const MODE_ICON: Record<JobMode, LucideIcon> = {
  tiktok_shop: ShoppingBag,
  tiktok_shop_watermark: ShieldOff,
  tiktok_shop_pack: Package,
  tiktok_shop_plan: CalendarDays,
  tiktok_shop_auto_day: Radar,
  tiktok_shop_ready_video: Film,
  presidents: Crown,
  pronosticos: BarChart3,
  copyright: ShieldOff,
  subs_auto: Captions,
  construccion_pov: HardHat,
  editor_auto: Scissors,
  viralizacion_batch: Video,
  nicho_pov_bof_backup: HardDrive,
  nicho_pov_bof_video: Film,
};

/**
 * Acento visual por programa. Borde izquierdo coloreado.
 */
export const PROGRAM_BORDER: Record<Program, string> = {
  tiktok_shop: "border-l-4 border-l-brand-cyan",
  creator_reward: "border-l-4 border-l-brand-violet",
  editor_auto: "border-l-4 border-l-emerald-500",
  viralizacion: "border-l-4 border-l-amber-500",
};

export const PROGRAM_TEXT: Record<Program, string> = {
  tiktok_shop: "text-brand-cyan",
  creator_reward: "text-brand-violet",
  editor_auto: "text-emerald-500",
  viralizacion: "text-amber-500",
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
    case "construccion_pov":
      if (params.voice_id) out.push(`voz ${String(params.voice_id).slice(0, 18)}`);
      if (params.upscale_1080p) out.push("1080p");
      break;
    case "editor_auto":
      if (params.user_name) out.push(String(params.user_name));
      if (params.tool_count) out.push(`${params.tool_count} tool(s)`);
      break;
    case "tiktok_shop_watermark":
      if (params.watermark_type) out.push(String(params.watermark_type));
      if (params.quality) out.push(String(params.quality));
      break;
    case "tiktok_shop_plan":
      if (params.per_day) out.push(`${String(params.per_day)}/día`);
      if (params.days) out.push(`${String(params.days)} días`);
      break;
    case "tiktok_shop_auto_day":
      if (params.date) out.push(String(params.date));
      if (params.top_n) out.push(`top ${String(params.top_n)}`);
      if (params.region) out.push(String(params.region));
      break;
    case "viralizacion_batch":
      if (Array.isArray(params.ponentes) && params.ponentes.length)
        out.push(params.ponentes.join(", "));
      if (params.nombre_cuenta) out.push(String(params.nombre_cuenta));
      if (params.music_rounds != null) out.push(`música ${String(params.music_rounds)}`);
      break;
    case "nicho_pov_bof_backup":
      out.push(params.force_full ? "copia completa" : "incremental");
      break;
    case "nicho_pov_bof_video":
      if (params.folder) out.push(String(params.folder));
      if (params.producto) out.push(`producto ${String(params.producto)}`);
      if (params.con_textos === false) out.push("sin textos");
      break;
  }
  return out;
}
