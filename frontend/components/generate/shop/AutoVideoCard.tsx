"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Send, Timer } from "lucide-react";
import { toast } from "sonner";

import { SchedulePicker } from "@/components/queue/SchedulePicker";
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
import { useProduct } from "@/lib/queries/products";
import { defaultVoiceForLanguage } from "@/lib/language";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { EnqueueRequest, OverlaysConfig, StrategyValue } from "@/lib/types/generation";
import type { Tier } from "@/lib/types/product";
import { useVoices } from "@/lib/queries/voices";

import { BulkGenerateDialog } from "./BulkGenerateDialog";
import { DEFAULT_OVERLAYS, OverlaysPanel } from "./OverlaysPanel";
import { PresetControls } from "./PresetControls";
import { VideoPresetsPicker } from "./VideoPresetsPicker";
import { FlaskConical, Layers, Target } from "lucide-react";
import { cn } from "@/lib/utils";
import type { VideoPreset } from "@/lib/types/product";

/** 3 modos de generación que el user elige al inicio del flujo:
 *  - `single`  → 1 preset → 1 vídeo. Click "Generar vídeo".
 *  - `batch`   → multi-select N presets → 1 vídeo por preset.
 *  - `variants`→ 1 preset → N variantes A/B (Gemini varía dimensiones).
 *
 *  El modo cambia: (a) el comportamiento de VideoPresetsPicker (single
 *  vs multi-select), (b) la barra de acción principal abajo.
 */
type GenMode = "single" | "batch" | "variants";

const MODE_META: Record<GenMode, { label: string; subtitle: string; icon: typeof Target; cls: string }> = {
  single: {
    label: "1 vídeo",
    subtitle: "Selecciona 1 preset → 1 vídeo",
    icon: Target,
    cls: "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  batch: {
    label: "Lote",
    subtitle: "N presets → 1 vídeo c/u",
    icon: Layers,
    cls: "border-sky-500 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  variants: {
    label: "Variantes A/B",
    subtitle: "1 preset → N variantes IA",
    icon: FlaskConical,
    cls: "border-violet-500 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
};

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
  // Subtítulos custom del preset (size_px, color, margin_x_pct, ...).
  // null → backend usa defaults conservadores. Se popula al aplicar preset.
  subtitle_style: Record<string, unknown> | null;
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
  subtitle_style: null,
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
  // Modo de generación (ver `GenMode`). El user lo elige al inicio.
  const [mode, setMode] = useState<GenMode>("single");
  // En modo `batch`, IDs de presets marcados. En `single` y `variants`
  // se usa `activeVideoPresetId`.
  const [batchSelectedIds, setBatchSelectedIds] = useState<Set<string>>(
    new Set(),
  );
  // En modo `variants`, cuántas variantes generar del preset activo.
  const [variantsN, setVariantsN] = useState(3);
  // Open state del BulkGenerateDialog (común para batch/variants).
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkSmart, setBulkSmart] = useState(false);

  function toggleBatchPreset(id: string) {
    setBatchSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearBatch() {
    setBatchSelectedIds(new Set());
  }

  // State para el SchedulePicker (modo single — el botón Programar).
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);

  function openBatchDialog() {
    if (batchSelectedIds.size === 0) {
      toast.error("Marca al menos 1 preset en el grid");
      return;
    }
    setBulkSmart(false);
    setBulkOpen(true);
  }

  function openVariantsDialog() {
    if (!activeVideoPresetId) {
      toast.error("Selecciona 1 preset primero");
      return;
    }
    setBulkSmart(true);
    setBulkOpen(true);
  }

  // Cargamos el producto para tener su idioma → la voz default sigue al
  // idioma elegido en la pestaña Identidad (es_ES → Spanish_*, en_US →
  // English_*…). El user puede sobrescribir con clones.
  const productQuery = useProduct(productId);
  const productLanguage = productQuery.data?.language || "es_ES";

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
      // Cadena de fallback: voz del preset (si user la fijó al editar) →
      // default del idioma del producto → voz actual del form. Así un
      // producto en en_US no usa Spanish_EnergeticBoy por accidente.
      voice_id:
        preset.kind === "scripted"
          ? preset.voice_id ||
            defaultVoiceForLanguage(productLanguage) ||
            c.voice_id
          : c.voice_id,
      hook_custom: preset.text_overlay,
      target_audience: preset.angle || c.target_audience,
      // Subtítulos: pasa el style del preset solo si voz habilitada
      // (sin voz no hay subs). Música → null para que backend salte.
      subtitle_style:
        preset.kind === "scripted" && preset.subtitle_style
          ? (preset.subtitle_style as unknown as Record<string, unknown>)
          : null,
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
    subtitle_style: config.voice_enabled ? config.subtitle_style : null,
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

  async function generate(scheduledForIso: string | null = null) {
    try {
      const payload = scheduledForIso
        ? { ...currentPayload, scheduled_for: scheduledForIso }
        : currentPayload;
      const res = await enqueue.mutateAsync(payload);
      const when = scheduledForIso
        ? ` · programado para ${new Date(scheduledForIso).toLocaleString("es-ES", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}`
        : "";
      toast.success(
        `Encolado · job ${res.job_id.slice(0, 8)} · $${res.estimated_cost.toFixed(2)} estimado${when}`,
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

        {/* ───── PASO 1 · Modo de generación ───── */}
        <div className="space-y-1.5">
          <Label className="text-xs">1 · ¿Qué quieres generar?</Label>
          <div className="grid grid-cols-3 gap-1.5">
            {(["single", "batch", "variants"] as GenMode[]).map((m) => {
              const meta = MODE_META[m];
              const Icon = meta.icon;
              const isActive = mode === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={cn(
                    "flex flex-col gap-0.5 rounded-md border-2 px-1.5 py-2 text-left text-xs transition-colors",
                    isActive
                      ? meta.cls
                      : "border-muted hover:border-muted-foreground/40",
                  )}
                >
                  <div className="flex items-center gap-1">
                    <Icon className="h-3.5 w-3.5 shrink-0" />
                    <strong className="text-[11px]">{meta.label}</strong>
                  </div>
                  <span className="text-[9px] text-muted-foreground line-clamp-2">
                    {meta.subtitle}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* ───── PASO 2 · Modelo Seedance ───── */}
        <div className="space-y-1.5">
          <Label className="text-xs">2 · Modelo Seedance</Label>
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

        {/* ───── PASO 3 · Preset(s) ───── */}
        <div className="space-y-1.5">
          <Label className="text-xs">
            3 · {mode === "batch"
              ? "Marca los presets que quieras encolar"
              : mode === "variants"
                ? "Elige el preset base de las variantes"
                : "Elige el preset"}
          </Label>
          <VideoPresetsPicker
            productId={productId}
            tier={config.tier}
            activePresetId={activeVideoPresetId}
            onPick={applyVideoPreset}
            onClear={clearVideoPreset}
            multiMode={mode === "batch"}
            selectedIds={mode === "batch" ? batchSelectedIds : undefined}
            onToggleSelect={mode === "batch" ? toggleBatchPreset : undefined}
            onSelectAll={
              mode === "batch"
                ? (ids) => setBatchSelectedIds(new Set(ids))
                : undefined
            }
          />
        </div>

        {/* En modo Variantes A/B, input de N variantes (visible solo aquí) */}
        {mode === "variants" && (
          <div className="flex items-center gap-2 rounded-md border border-violet-500/30 bg-violet-500/5 p-2">
            <Label className="text-xs whitespace-nowrap" htmlFor="variants-n">
              Nº variantes
            </Label>
            <Input
              id="variants-n"
              type="number"
              min={2}
              max={8}
              value={variantsN}
              onChange={(e) =>
                setVariantsN(
                  Math.max(2, Math.min(8, parseInt(e.target.value) || 2)),
                )
              }
              className="h-7 w-16 text-xs"
            />
            <span className="text-[10px] text-muted-foreground">
              Gemini variará text overlay, color, CTA, voz, mood…
            </span>
          </div>
        )}

        {/* ───── ACCIÓN PRINCIPAL ───── */}
        <div className="flex flex-wrap items-center gap-2">
          {mode === "single" && (
            <>
              <Button
                onClick={() => generate(null)}
                disabled={enqueue.isPending || !activeVideoPresetId}
                className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                title={!activeVideoPresetId ? "Elige un preset primero" : ""}
              >
                {enqueue.isPending ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-1.5 h-4 w-4" />
                )}
                Generar 1 vídeo
              </Button>
              <Button
                variant="outline"
                onClick={() => setScheduleDialogOpen(true)}
                disabled={enqueue.isPending || !activeVideoPresetId}
                className="border-amber-500/40 hover:bg-amber-500/10"
                title="Programar para más tarde (ej. madrugada cuando providers AI tienen cola libre)"
              >
                <Timer className="mr-1.5 h-4 w-4 text-amber-500" />
                Programar
              </Button>
            </>
          )}
          {mode === "batch" && (
            <Button
              onClick={openBatchDialog}
              disabled={enqueue.isPending || batchSelectedIds.size === 0}
              className="flex-1 bg-sky-600 hover:bg-sky-700"
            >
              <Layers className="mr-1.5 h-4 w-4" />
              Encolar lote ({batchSelectedIds.size}{" "}
              {batchSelectedIds.size === 1 ? "vídeo" : "vídeos"})
            </Button>
          )}
          {mode === "variants" && (
            <Button
              onClick={openVariantsDialog}
              disabled={enqueue.isPending || !activeVideoPresetId}
              className="flex-1 bg-violet-600 hover:bg-violet-700"
              title={!activeVideoPresetId ? "Elige el preset base primero" : ""}
            >
              <FlaskConical className="mr-1.5 h-4 w-4" />
              Generar {variantsN} variantes A/B
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            <span className="ml-1 hidden sm:inline">
              {expanded ? "Ocultar" : "Avanzado"}
            </span>
          </Button>
        </div>

        <BulkGenerateDialog
          open={bulkOpen}
          onOpenChange={setBulkOpen}
          basePayload={currentPayload}
          productId={productId}
          tier={config.tier}
          initialSmartMode={bulkSmart}
          initialSelectedPresetIds={
            bulkSmart
              ? activeVideoPresetId
                ? [activeVideoPresetId]
                : []
              : Array.from(batchSelectedIds)
          }
          initialVariantsPerPreset={bulkSmart ? variantsN : 1}
        />

        {expanded && (
          <div className="space-y-3 border-t pt-3">
            {/* Configuraciones guardadas (legacy) — solo si el user las usa. */}
            <CollapsibleCard
              title="Configuraciones guardadas"
              defaultOpen={false}
            >
              <PresetControls
                userId={userId}
                productId={productId}
                kind="auto_video"
                selectedName={selectedPreset}
                onSelectName={setSelectedPreset}
                currentConfig={config as unknown as Record<string, unknown>}
                onLoadConfig={applyConfig}
              />
            </CollapsibleCard>

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

      {/* Dialog "Programar" — confirma la hora antes de encolar. */}
      <SchedulePicker
        open={scheduleDialogOpen}
        onOpenChange={setScheduleDialogOpen}
        title="Programar vídeo"
        description="Encolará el vídeo pero el worker no lo procesará hasta la hora que indiques. Útil para que se ejecute en madrugada (00-08h Spain) cuando los providers AI tienen cola libre."
        confirmLabel="Encolar programado"
        busy={enqueue.isPending}
        onConfirm={async (iso) => {
          setScheduleDialogOpen(false);
          await generate(iso);
        }}
      />
    </Card>
  );
}
