"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/lib/api";
import { useEnqueueGeneration } from "@/lib/queries/generations";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { EnqueueRequest, OverlaysConfig, StrategyValue } from "@/lib/types/generation";
import type { Tier } from "@/lib/types/product";
import { useVoices } from "@/lib/queries/voices";

import { BulkGenerateDialog } from "./BulkGenerateDialog";
import { DEFAULT_OVERLAYS, OverlaysPanel } from "./OverlaysPanel";
import { PresetControls } from "./PresetControls";
import { TestBatchPanel } from "./TestBatchPanel";
import { VideoPresetsPicker } from "./VideoPresetsPicker";
import { Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import type { VideoPreset } from "@/lib/types/product";

interface AutoVideoConfig {
  tier: Tier;
  strategy: StrategyValue;
  duration_seconds: number;
  resolution: string;
  hook_category: string;
  hook_custom: string;
  target_audience: string;
  voice_enabled: boolean;
  voice_id: string;
  shoppable: boolean;
  overlays: OverlaysConfig;
}

const DEFAULT_CONFIG: AutoVideoConfig = {
  tier: "standard",
  strategy: "dynamic",
  duration_seconds: 15,
  resolution: "720p",
  hook_category: "curiosity",
  hook_custom: "",
  target_audience: "Generalista",
  voice_enabled: true,
  voice_id: "Spanish_EnergeticBoy",
  shoppable: false,
  overlays: DEFAULT_OVERLAYS,
};

const ATLAS_TIERS: { value: Tier; label: string; cost: string }[] = [
  { value: "standard", label: "🟢 Standard", cost: "$0.27/15s" },
  { value: "advanced", label: "🟡 Advanced", cost: "$0.71/15s" },
  { value: "pro", label: "🔴 Pro", cost: "$1.08/15s" },
];

const DURATIONS = [5, 10, 12, 15, 20, 24, 25, 30];

const RES_BY_TIER: Record<string, string[]> = {
  standard: ["720p"],
  advanced: ["480p", "720p"],
  pro: ["480p", "720p", "1080p-SR", "1440p-SR"],
};

const HOOK_CATEGORIES = [
  "curiosity",
  "problem_solution",
  "social_proof",
  "before_after",
  "shock",
  "tutorial",
];

interface Props {
  userId: string;
  username: string;
  productId: string;
  hideTitle?: boolean;
}

export function AutoVideoCard({ userId, username, productId, hideTitle }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [config, setConfig] = useState<AutoVideoConfig>(DEFAULT_CONFIG);
  const [selectedPreset, setSelectedPreset] = useState<string>("");
  // ID del VideoPreset del producto aplicado al form (no confundir con
  // el `selectedPreset` legacy de ShopPresetControls).
  const [activeVideoPresetId, setActiveVideoPresetId] = useState<string | null>(
    null,
  );
  const [bulkOpen, setBulkOpen] = useState(false);

  const enqueue = useEnqueueGeneration();
  const openQueue = useDrawerStore((s) => s.openQueue);
  const voices = useVoices({ language: "es" });

  /** Aplica un VideoPreset del producto a la config del Auto vídeo.
   *  Mapea: tier compat → tier, duration_s → duración, voice_id/voice_tone →
   *  voz, text_overlay → hook_custom, angle → target_audience, cta_arrow_style
   *  → overlays.cta_arrow (flecha al carrito al final del vídeo). */
  function applyVideoPreset(preset: VideoPreset) {
    const preferredTier =
      preset.compatible_tiers.find((t) =>
        ["standard", "advanced", "pro"].includes(t),
      ) ?? config.tier;
    // shot_style del preset se traduce a strategy del payload:
    //  single_shot → cinematic (1 plano)
    //  multi_shot  → dynamic (cortes)
    //  auto        → respeta el preset.strategy
    const resolvedStrategy: StrategyValue =
      preset.shot_style === "single_shot"
        ? "cinematic"
        : preset.shot_style === "multi_shot"
          ? "dynamic"
          : (preset.strategy === "cinematic" ? "cinematic" : "dynamic");
    setConfig((c) => ({
      ...c,
      tier: preferredTier as Tier,
      strategy: resolvedStrategy,
      duration_seconds: preset.duration_s,
      voice_enabled: preset.kind === "scripted",
      voice_id:
        preset.kind === "scripted"
          ? preset.voice_id || c.voice_id
          : c.voice_id,
      hook_custom: preset.text_overlay,
      target_audience: preset.angle || c.target_audience,
      overlays: {
        ...c.overlays,
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
      },
    }));
    setActiveVideoPresetId(preset.id);
    toast.success(`Preset "${preset.name}" aplicado`);
  }

  function clearVideoPreset() {
    setActiveVideoPresetId(null);
    toast("Preset desactivado — config manual");
  }

  function patch<K extends keyof AutoVideoConfig>(key: K, value: AutoVideoConfig[K]) {
    setConfig((c) => ({ ...c, [key]: value }));
  }

  function applyConfig(cfg: Record<string, unknown>) {
    setConfig((prev) => ({
      ...prev,
      ...(cfg as Partial<AutoVideoConfig>),
      // Asegura que overlays nunca sea undefined
      overlays:
        ((cfg as { overlays?: OverlaysConfig }).overlays) ?? prev.overlays ?? DEFAULT_OVERLAYS,
    }));
  }

  const resOptions: string[] = RES_BY_TIER[config.tier] ?? ["720p"];
  const fallbackRes = resOptions[0] ?? "720p";

  const currentPayload: EnqueueRequest = {
    username,
    product_id: productId,
    tier: config.tier,
    duration_seconds: config.duration_seconds,
    resolution: resOptions.includes(config.resolution) ? config.resolution : fallbackRes,
    strategy: config.strategy,
    voice_enabled: config.voice_enabled,
    voice_id: config.voice_enabled ? config.voice_id || null : null,
    hook_category: config.hook_category,
    hook_custom: config.hook_custom.trim() || null,
    target_audience: config.target_audience.trim() || "Generalista",
    shoppable: config.shoppable,
    ai_disclosure: true,
    overlays: config.overlays,
  };

  // Estimación local (espejo grueso de cost_calculator.py) — solo para preview
  // del coste por variante en el panel de batch.
  const RATE_PER_SEC: Record<string, number> = {
    standard: 0.018,
    advanced: 0.047,
    pro: 0.072,
  };
  const RES_MULT: Record<string, number> = {
    "480p": 0.7,
    "720p": 1.0,
    "1080p-SR": 1.5,
    "1440p-SR": 2.0,
  };
  const estimatedPerVideo =
    (RATE_PER_SEC[config.tier] ?? 0) *
      config.duration_seconds *
      (RES_MULT[config.resolution] ?? 1) +
    (config.voice_enabled ? config.duration_seconds * 18 * 0.00006 : 0);

  async function generate() {
    try {
      const res = await enqueue.mutateAsync(currentPayload);
      toast.success(
        `Encolado · job ${res.job_id.slice(0, 8)} · $${res.estimated_cost.toFixed(2)} estimado`,
      );
      openQueue();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al encolar.");
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4 sm:p-5">
        {!hideTitle && (
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-lg font-semibold">🎬 Auto vídeo</p>
              <p className="text-xs text-muted-foreground">
                Seedance + voz + subs + overlays → se encola y renderiza en Drive.
              </p>
            </div>
          </div>
        )}

        {/* TIER SELECTOR — visible siempre, no en colapsable */}
        <div className="space-y-1.5">
          <Label className="text-xs">Modelo Seedance</Label>
          <div className="grid grid-cols-3 gap-1.5">
            {ATLAS_TIERS.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => patch("tier", t.value)}
                className={cn(
                  "flex flex-col gap-0.5 rounded-md border-2 px-2 py-1.5 text-left text-xs transition-colors",
                  config.tier === t.value
                    ? "border-emerald-500 bg-emerald-500/15"
                    : "border-muted hover:border-emerald-500/50",
                )}
              >
                <strong className="text-[11px]">{t.label}</strong>
                <span className="text-[9px] text-muted-foreground">{t.cost}</span>
              </button>
            ))}
          </div>
        </div>

        {/* PRESETS DEL PRODUCTO (video_presets) filtrados por tier */}
        <VideoPresetsPicker
          productId={productId}
          tier={config.tier}
          activePresetId={activeVideoPresetId}
          onPick={applyVideoPreset}
          onClear={clearVideoPreset}
        />

        {/* Presets legacy (configuraciones guardadas con nombre) — solo si
            el usuario las usa. Las dejo accesibles pero discretas. */}
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            Configuraciones guardadas (avanzado)
          </summary>
          <div className="mt-2">
            <PresetControls
              userId={userId}
              productId={productId}
              kind="auto_video"
              selectedName={selectedPreset}
              onSelectName={setSelectedPreset}
              currentConfig={config as unknown as Record<string, unknown>}
              onLoadConfig={applyConfig}
            />
          </div>
        </details>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={generate} disabled={enqueue.isPending} className="flex-1">
            {enqueue.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Generar vídeo
          </Button>
          <Button variant="outline" size="sm" onClick={() => setExpanded((v) => !v)}>
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            {expanded ? "Ocultar" : "Configurar"}
          </Button>
        </div>

        {/* Generación masiva — N variantes × M presets */}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setBulkOpen(true)}
            disabled={enqueue.isPending}
            className="text-emerald-700 dark:text-emerald-300"
          >
            <Layers className="mr-1.5 h-3.5 w-3.5" />
            Generación masiva (N × presets)
          </Button>
        </div>

        <TestBatchPanel
          basePayload={currentPayload}
          estimatedCostPerVideo={estimatedPerVideo}
          disabled={enqueue.isPending}
        />

        <BulkGenerateDialog
          open={bulkOpen}
          onOpenChange={setBulkOpen}
          basePayload={currentPayload}
          productId={productId}
          tier={config.tier}
        />

        {expanded && (
          <div className="space-y-3 border-t pt-3">
            {/* Estrategia + resolución (el tier ya está fuera del expanded) */}
            <CollapsibleCard title="Estrategia & resolución" defaultOpen>
              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Estrategia</Label>
                    <Select
                      value={config.strategy}
                      onValueChange={(v) => patch("strategy", v as StrategyValue)}
                    >
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="dynamic">Dinámico TikTok</SelectItem>
                        <SelectItem value="cinematic">Cinematográfico</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Resolución</Label>
                    <Select
                      value={config.resolution}
                      onValueChange={(v) => patch("resolution", v)}
                    >
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {resOptions.map((r) => (
                          <SelectItem key={r} value={r}>{r}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Duración: {config.duration_seconds}s</Label>
                  <input
                    type="range"
                    min={5}
                    max={30}
                    step={1}
                    value={config.duration_seconds}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      const snapped = DURATIONS.reduce((prev, curr) =>
                        Math.abs(curr - v) < Math.abs(prev - v) ? curr : prev,
                      );
                      patch("duration_seconds", snapped);
                    }}
                    className="w-full"
                  />
                </div>
              </div>
            </CollapsibleCard>

            {/* Hook */}
            <CollapsibleCard title="Hook & audiencia" defaultOpen>
              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Categoría</Label>
                    <Select
                      value={config.hook_category}
                      onValueChange={(v) => patch("hook_category", v)}
                    >
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {HOOK_CATEGORIES.map((c) => (
                          <SelectItem key={c} value={c}>{c}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Audiencia</Label>
                    <Input
                      value={config.target_audience}
                      onChange={(e) => patch("target_audience", e.target.value)}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Hook custom (opcional)</Label>
                  <Input
                    value={config.hook_custom}
                    onChange={(e) => patch("hook_custom", e.target.value)}
                    placeholder="Sobrescribe la categoría con un hook concreto"
                  />
                </div>
              </div>
            </CollapsibleCard>

            {/* Voz */}
            <CollapsibleCard title="Voz">
              <div className="space-y-3">
                <label className="flex cursor-pointer items-center justify-between gap-2 rounded-md border p-2 text-sm">
                  <span>Habilitar voz narrada (MiniMax)</span>
                  <Switch
                    checked={config.voice_enabled}
                    onCheckedChange={(v) => patch("voice_enabled", v)}
                  />
                </label>
                {config.voice_enabled && (
                  <div className="space-y-1">
                    <Label className="text-xs">Voz</Label>
                    <Select
                      value={config.voice_id}
                      onValueChange={(v) => patch("voice_id", v)}
                    >
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {(voices.data?.items ?? []).map((v) => (
                          <SelectItem key={v.id} value={v.minimax_voice_id}>
                            {v.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <label className="flex cursor-pointer items-center justify-between gap-2 rounded-md border p-2 text-sm">
                  <span>Shoppable (cuenta para el Pilot Program)</span>
                  <Switch
                    checked={config.shoppable}
                    onCheckedChange={(v) => patch("shoppable", v)}
                  />
                </label>
              </div>
            </CollapsibleCard>

            {/* Overlays — Fase 3 */}
            <CollapsibleCard title="Overlays · hook box + CTA flecha">
              <OverlaysPanel
                value={config.overlays}
                onChange={(v) => patch("overlays", v)}
              />
            </CollapsibleCard>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
