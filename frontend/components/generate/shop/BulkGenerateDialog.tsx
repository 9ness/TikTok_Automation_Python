"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useEnqueueGeneration } from "@/lib/queries/generations";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import { useGenerateVariants, useProduct } from "@/lib/queries/products";
import type { EnqueueRequest } from "@/lib/types/generation";
import type {
  VariantDimension,
  VideoPreset,
} from "@/lib/types/product";
import { VARIANT_DIMENSIONS } from "@/lib/types/product";
import { cn } from "@/lib/utils";

const DIMENSION_LABEL: Record<VariantDimension, string> = {
  text_overlay: "Hook texto",
  text_overlay_color: "Color del texto",
  text_overlay_position: "Posición del texto",
  cta_arrow: "Flecha CTA",
  voice_tone: "Tono voz",
  voice_script: "Guion (reescritura mínima)",
  music_mood: "Música",
  shot_style: "Single vs multi-shot",
  hooks_alternatives: "Hooks alternativos",
  subtitle_style: "Estilo subtítulos",
};

/** Construye el payload EnqueueRequest aplicando los campos de un preset
 *  encima de un base. Mismo mapeo que `applyVideoPreset` en AutoVideoCard
 *  para que el comportamiento sea consistente. */
function applyPresetToPayload(
  base: EnqueueRequest,
  preset: VideoPreset,
): EnqueueRequest {
  const preferredTier =
    preset.compatible_tiers.find((t) =>
      ["standard", "advanced", "pro"].includes(t),
    ) ?? base.tier;
  const resolvedStrategy =
    preset.shot_style === "single_shot"
      ? "cinematic"
      : preset.shot_style === "multi_shot"
        ? "dynamic"
        : (preset.strategy === "cinematic" ? "cinematic" : "dynamic");
  return {
    ...base,
    tier: preferredTier as EnqueueRequest["tier"],
    strategy: resolvedStrategy as EnqueueRequest["strategy"],
    duration_seconds: preset.duration_s,
    voice_enabled: preset.kind === "scripted",
    voice_id:
      preset.kind === "scripted"
        ? preset.voice_id || base.voice_id || null
        : null,
    hook_custom: preset.text_overlay || base.hook_custom,
    target_audience: preset.angle || base.target_audience,
    overlays: base.overlays
      ? {
          ...base.overlays,
          cta_arrow: {
            enabled: preset.cta_arrow_style.enabled,
            sticker_file: preset.cta_arrow_style.sticker_file,
            position_x_pct: preset.cta_arrow_style.position_x_pct,
            position_y_pct: preset.cta_arrow_style.position_y_pct,
            scale_width_pct: preset.cta_arrow_style.scale_width_pct,
            rotation_deg: preset.cta_arrow_style.rotation_deg,
            flip_horizontal: preset.cta_arrow_style.flip_horizontal,
            flip_vertical: preset.cta_arrow_style.flip_vertical,
            duration_seconds: preset.cta_arrow_style.duration_seconds,
            fallback_last_seconds: preset.cta_arrow_style.duration_seconds,
          },
        }
      : base.overlays,
  };
}

export function BulkGenerateDialog({
  open,
  onOpenChange,
  basePayload,
  productId,
  tier,
  initialSmartMode,
  initialSelectedPresetIds,
  initialVariantsPerPreset,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  basePayload: EnqueueRequest;
  productId: string;
  tier: string;
  /** Si el caller abre el diálogo con un modo concreto (batch vs A/B),
   *  inicializa el toggle smartMode con este valor. Útil cuando el modo
   *  del AutoVideoCard ya está fijado por el user en la pestaña externa. */
  initialSmartMode?: boolean;
  /** Pre-selecciona estos presets (por id). Útil cuando el user ya marcó
   *  un preset (modo "Variantes A/B" o "Lote") en el AutoVideoCard. */
  initialSelectedPresetIds?: string[];
  /** Valor inicial del input "variantes por preset". En modo Variantes
   *  A/B tiene sentido un default mayor (ej. 3); en Lote suele ser 1. */
  initialVariantsPerPreset?: number;
}) {
  const product = useProduct(productId);
  const enqueue = useEnqueueGeneration();
  const generateVariants = useGenerateVariants(productId);
  const openQueue = useDrawerStore((s) => s.openQueue);

  const presets = product.data?.video_presets ?? [];
  const compatible = useMemo(
    () => presets.filter((p) => p.compatible_tiers.includes(tier)),
    [presets, tier],
  );

  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(initialSelectedPresetIds ?? []),
  );
  const [variantsPerPreset, setVariantsPerPreset] = useState(
    initialVariantsPerPreset ?? 1,
  );
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(
    null,
  );
  // Modo smart variants: en vez de N copias idénticas, llama a Gemini
  // para que genere N variantes A/B (cada una con hipótesis distinta).
  const [smartMode, setSmartMode] = useState(initialSmartMode ?? false);

  // Cuando el dialog se reabre con nuevas props (mode change desde fuera),
  // resincroniza el estado interno. Sin esto el state queda pegado al
  // primer mount.
  useEffect(() => {
    if (open) {
      setSelectedIds(new Set(initialSelectedPresetIds ?? []));
      setSmartMode(initialSmartMode ?? false);
      setVariantsPerPreset(initialVariantsPerPreset ?? 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const [smartDims, setSmartDims] = useState<Set<VariantDimension>>(
    () => new Set(["text_overlay", "text_overlay_color", "cta_arrow"]),
  );

  function toggleDim(d: VariantDimension) {
    setSmartDims((s) => {
      const n = new Set(s);
      if (n.has(d)) n.delete(d);
      else n.add(d);
      return n;
    });
  }

  function togglePreset(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll(filter?: "music" | "scripted") {
    setSelectedIds(
      new Set(
        compatible
          .filter((p) => !filter || p.kind === filter)
          .map((p) => p.id),
      ),
    );
  }

  function clearSel() {
    setSelectedIds(new Set());
  }

  const selectedPresets = compatible.filter((p) => selectedIds.has(p.id));
  const totalVideos = selectedPresets.length * variantsPerPreset;

  // Estimación gruesa: $0.018 standard / 0.047 advanced / 0.072 pro × dur ×
  // (voice ? +TTS) por vídeo. Pero diferentes presets pueden tener tier
  // distinto si el user no lo fijó; aquí asumimos `basePayload.tier`.
  const rate =
    ({
      standard: 0.018,
      advanced: 0.047,
      pro: 0.072,
      veo3_prompt_only: 0.35,
    } as Record<string, number>)[tier] ?? 0.018;
  const estimatedCost = selectedPresets.reduce(
    (acc, p) => acc + rate * p.duration_s * variantsPerPreset,
    0,
  );

  async function handleEnqueueAll() {
    if (selectedPresets.length === 0) {
      toast.error("Selecciona al menos un preset");
      return;
    }
    if (variantsPerPreset < 1 || variantsPerPreset > 5) {
      toast.error("Variantes por preset entre 1 y 5");
      return;
    }

    // Construye la lista final de presets a encolar.
    // - smartMode=false → cada preset original × variantsPerPreset copias
    // - smartMode=true  → para cada preset original, Gemini genera N variantes
    //                     con hipótesis distintas y cada variante es 1 job.
    let presetsToEnqueue: VideoPreset[] = [];

    if (smartMode) {
      if (smartDims.size === 0) {
        toast.error("Elige al menos una dimensión a variar");
        return;
      }
      toast(`Generando ${selectedPresets.length * variantsPerPreset} variantes con IA…`, {
        duration: 3000,
      });
      // Llamar al endpoint de variants por cada preset. Esto puede tardar
      // (1 call Gemini por preset). Lo hacemos secuencial para no saturar.
      try {
        for (const p of selectedPresets) {
          const r = await generateVariants.mutateAsync({
            presetId: p.id,
            input: {
              count: variantsPerPreset,
              dimensions: Array.from(smartDims),
            },
          });
          if (r.variants.length === 0) {
            toast.warning(
              `Sin variantes para "${p.name}" — uso copias idénticas.`,
            );
            for (let i = 0; i < variantsPerPreset; i++) {
              presetsToEnqueue.push(p);
            }
          } else {
            presetsToEnqueue.push(...r.variants);
          }
        }
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Generación variantes falló",
        );
        return;
      }
    } else {
      // Modo clásico: N copias idénticas por preset
      for (const p of selectedPresets) {
        for (let i = 0; i < variantsPerPreset; i++) {
          presetsToEnqueue.push(p);
        }
      }
    }

    // Encolar uno a uno con barra de progreso
    setProgress({ done: 0, total: presetsToEnqueue.length });
    let ok = 0;
    let fail = 0;
    for (let i = 0; i < presetsToEnqueue.length; i++) {
      const p = presetsToEnqueue[i];
      if (!p) continue;
      try {
        await enqueue.mutateAsync(applyPresetToPayload(basePayload, p));
        ok++;
      } catch {
        fail++;
      }
      setProgress({ done: i + 1, total: presetsToEnqueue.length });
    }
    toast.success(
      `${ok} vídeo(s) encolados${fail > 0 ? ` · ${fail} fallaron` : ""}${
        smartMode ? " (con variantes A/B inteligentes)" : ""
      }`,
    );
    setProgress(null);
    onOpenChange(false);
    openQueue();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Generación masiva</DialogTitle>
          <DialogDescription>
            Elige presets compatibles con el tier <strong>{tier}</strong>, decide
            cuántas variantes por preset y encola todos los vídeos de golpe.
          </DialogDescription>
        </DialogHeader>

        {compatible.length === 0 ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
            No hay presets compatibles con el tier <strong>{tier}</strong>. Genera
            presets desde la página del producto.
          </p>
        ) : (
          <div className="space-y-3">
            {/* Acciones rápidas */}
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              <button
                type="button"
                onClick={() => selectAll()}
                className="rounded-full border px-2 py-0.5 hover:bg-accent/40"
              >
                Todos ({compatible.length})
              </button>
              <button
                type="button"
                onClick={() => selectAll("music")}
                className="rounded-full border px-2 py-0.5 hover:bg-accent/40"
              >
                🎵 Solo música
              </button>
              <button
                type="button"
                onClick={() => selectAll("scripted")}
                className="rounded-full border px-2 py-0.5 hover:bg-accent/40"
              >
                🎤 Solo scripted
              </button>
              <button
                type="button"
                onClick={clearSel}
                className="rounded-full border px-2 py-0.5 hover:bg-accent/40"
              >
                ✕ Limpiar
              </button>
            </div>

            {/* Variantes por preset + modo smart */}
            <div className="flex items-center gap-2">
              <Label htmlFor="bulk-n" className="text-xs">
                Variantes por preset
              </Label>
              <Input
                id="bulk-n"
                type="number"
                min={1}
                max={5}
                value={variantsPerPreset}
                onChange={(e) =>
                  setVariantsPerPreset(
                    Math.max(1, Math.min(5, parseInt(e.target.value || "1", 10))),
                  )
                }
                className="h-8 w-20"
              />
              <span className="text-[10px] text-muted-foreground">(1-5)</span>
            </div>

            {/* Modo smart: variantes A/B con IA */}
            <div
              className={cn(
                "rounded-md border-2 p-2 transition-colors",
                smartMode
                  ? "border-emerald-500/60 bg-emerald-500/10"
                  : "border-muted bg-muted/20",
              )}
            >
              <label className="flex cursor-pointer items-start gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={smartMode}
                  onChange={(e) => setSmartMode(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5"
                />
                <div className="flex-1">
                  <strong className="block">
                    🧪 Variantes A/B inteligentes (Gemini)
                  </strong>
                  <span className="text-[10px] text-muted-foreground">
                    En lugar de N copias idénticas, Gemini analiza cada preset
                    y crea N variantes con cambios mínimos (color, posición,
                    hook reescrito, flecha…) — cada una testea una hipótesis
                    distinta. Coste extra: ~$0.002 por preset analizado.
                  </span>
                </div>
              </label>

              {smartMode && (
                <div className="mt-2 space-y-1">
                  <p className="text-[10px] font-medium">
                    Dimensiones a variar:
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {VARIANT_DIMENSIONS.map((d) => {
                      const on = smartDims.has(d);
                      return (
                        <button
                          key={d}
                          type="button"
                          onClick={() => toggleDim(d)}
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-[10px]",
                            on
                              ? "border-emerald-500 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                              : "border-muted hover:bg-accent/40",
                          )}
                        >
                          {DIMENSION_LABEL[d]}
                        </button>
                      );
                    })}
                  </div>
                  {smartDims.size === 0 && (
                    <p className="text-[10px] text-rose-600">
                      Marca al menos una dimensión.
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Grid de presets seleccionables */}
            <div className="grid max-h-64 gap-1.5 overflow-y-auto rounded-md border p-2 sm:grid-cols-2">
              {compatible.map((p) => {
                const sel = selectedIds.has(p.id);
                return (
                  <label
                    key={p.id}
                    className={cn(
                      "flex cursor-pointer gap-2 rounded p-1.5 text-[11px]",
                      sel
                        ? "bg-emerald-500/15 ring-1 ring-emerald-500"
                        : "hover:bg-accent/40",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={sel}
                      onChange={() => togglePreset(p.id)}
                      className="mt-0.5 h-3.5 w-3.5"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <span>{p.kind === "music" ? "🎵" : "🎤"}</span>
                        <strong className="truncate">{p.name}</strong>
                      </div>
                      <p className="truncate text-[10px] text-muted-foreground">
                        {p.angle || p.style} · {p.duration_s}s ·{" "}
                        {p.text_overlay || p.title || "—"}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>

            {/* Resumen */}
            <Card className="border-emerald-500/30 bg-emerald-500/5">
              <CardContent className="p-3 text-xs">
                <p>
                  <strong>{selectedPresets.length}</strong> preset(s) ×{" "}
                  <strong>{variantsPerPreset}</strong> variante(s) ={" "}
                  <strong className="text-emerald-700 dark:text-emerald-300">
                    {totalVideos} vídeo(s)
                  </strong>
                </p>
                <p className="text-muted-foreground">
                  Coste estimado:{" "}
                  <strong>${estimatedCost.toFixed(2)}</strong> (sin voz / SFX
                  ni overlays). Tier: {tier}.
                </p>
              </CardContent>
            </Card>

            {progress && (
              <div className="rounded-md border bg-muted/30 p-2 text-xs">
                Encolando… {progress.done}/{progress.total}
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-emerald-500 transition-all"
                    style={{
                      width: `${(progress.done / progress.total) * 100}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={!!progress}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleEnqueueAll}
            disabled={
              selectedPresets.length === 0 ||
              enqueue.isPending ||
              !!progress
            }
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {progress ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-2 h-4 w-4" />
            )}
            Encolar {totalVideos} vídeo{totalVideos !== 1 ? "s" : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
