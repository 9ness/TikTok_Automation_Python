"use client";

import { useMemo } from "react";
import { Mic, Music, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useProduct } from "@/lib/queries/products";
import type { VideoPreset } from "@/lib/types/product";
import { cn } from "@/lib/utils";

const STYLE_BADGE: Record<string, { label: string; cls: string }> = {
  voiceover: {
    label: "Voiceover",
    cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  },
  creator_pov: {
    label: "Creator POV",
    cls: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  },
};

/** Lista de VideoPresets del producto, filtrados por tier compatible.
 *  Click → ejecuta `onPick(preset)` que aplica los campos al form. */
export function VideoPresetsPicker({
  productId,
  tier,
  activePresetId,
  onPick,
  onClear,
}: {
  productId: string;
  /** Tier actualmente seleccionado en el form (filtra presets compatibles). */
  tier: string;
  /** ID del preset activo (para resaltar la card). */
  activePresetId: string | null;
  onPick: (preset: VideoPreset) => void;
  onClear: () => void;
}) {
  const product = useProduct(productId);
  const presets = product.data?.video_presets ?? [];

  // Filtra los compatibles con el tier seleccionado. Si tier=veo3_prompt_only
  // se filtra por "veo3_prompt_only".
  const compatible = useMemo(
    () => presets.filter((p) => p.compatible_tiers.includes(tier)),
    [presets, tier],
  );

  const musicCount = compatible.filter((p) => p.kind === "music").length;
  const scriptedCount = compatible.filter((p) => p.kind === "scripted").length;

  if (product.isLoading) {
    return (
      <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        Cargando presets…
      </div>
    );
  }

  if (presets.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-3 text-xs">
        Este producto aún no tiene presets. Ve a la página del producto → tab{" "}
        <strong>Presets</strong> → <strong>Generar todos</strong>.
      </div>
    );
  }

  if (compatible.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-3 text-xs">
        Ninguno de los {presets.length} presets es compatible con el tier{" "}
        <strong>{tier}</strong>. Cambia de tier o regenera presets desde el
        producto.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
          <strong>Presets del producto</strong>
          <span className="text-muted-foreground">
            {compatible.length} compat. {musicCount > 0 && `· 🎵 ${musicCount}`}
            {scriptedCount > 0 && ` · 🎤 ${scriptedCount}`}
          </span>
        </div>
        {activePresetId && (
          <button
            type="button"
            onClick={onClear}
            className="text-[10px] text-muted-foreground hover:text-foreground"
          >
            ✕ Limpiar
          </button>
        )}
      </div>

      {/* Grid scroll horizontal en mobile, grid 3 cols desktop */}
      <div className="-mx-1 flex gap-2 overflow-x-auto pb-1 sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible md:grid-cols-3">
        {compatible.map((p) => (
          <PresetMiniCard
            key={p.id}
            preset={p}
            active={activePresetId === p.id}
            onPick={() => onPick(p)}
          />
        ))}
      </div>
    </div>
  );
}

function PresetMiniCard({
  preset,
  active,
  onPick,
}: {
  preset: VideoPreset;
  active: boolean;
  onPick: () => void;
}) {
  const Icon = preset.kind === "music" ? Music : Mic;
  const accent = preset.kind === "music" ? "sky" : "violet";
  const styleMeta = STYLE_BADGE[preset.style];

  return (
    <button
      type="button"
      onClick={onPick}
      className={cn(
        "min-w-[220px] shrink-0 rounded-md border-2 p-2 text-left transition-all sm:min-w-0",
        active
          ? `border-${accent}-500 bg-${accent}-500/15`
          : `border-${accent}-500/30 bg-${accent}-500/5 hover:border-${accent}-500/60`,
        // Workaround: Tailwind necesita las clases literales — uso style fallback
        active && preset.kind === "music" && "border-sky-500 bg-sky-500/15",
        active && preset.kind === "scripted" && "border-violet-500 bg-violet-500/15",
      )}
    >
      <div className="flex items-center gap-1.5">
        <Icon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            preset.kind === "music" ? "text-sky-500" : "text-violet-500",
          )}
        />
        <strong className="truncate text-[11px]">{preset.name}</strong>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        {preset.angle && (
          <Badge variant="secondary" className="px-1 py-0 text-[9px]">
            {preset.angle}
          </Badge>
        )}
        {styleMeta && (
          <span
            className={cn(
              "rounded px-1 py-0 text-[9px]",
              styleMeta.cls,
            )}
          >
            {styleMeta.label}
          </span>
        )}
        <span className="text-[9px] text-muted-foreground">
          {preset.duration_s}s
        </span>
      </div>
      {preset.text_overlay && (
        <p className="mt-1 line-clamp-2 text-[10px] italic text-muted-foreground">
          &ldquo;{preset.text_overlay}&rdquo;
        </p>
      )}
    </button>
  );
}
