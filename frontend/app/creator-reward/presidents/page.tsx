"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, RotateCcw, Send } from "lucide-react";
import { toast } from "sonner";

import {
  PresidentsBatchEditor,
  emptyItem,
} from "@/components/creator-reward/presidents/PresidentsBatchEditor";
import { PresetManager } from "@/components/creator-reward/presidents/PresetManager";
import { PresidentsPreview } from "@/components/creator-reward/presidents/PresidentsPreview";
import {
  HookConfigPanel,
  NumbersConfigPanel,
  SubsConfigPanel,
} from "@/components/creator-reward/presidents/StyleConfigPanels";
import { Button } from "@/components/ui/button";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
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
import { useLocalStorageState } from "@/lib/hooks/useLocalStorageState";
import {
  useEnqueuePresidents,
  usePresidentsPreset,
} from "@/lib/queries/creator-reward/presidents";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type {
  EngineVersion,
  PresidentsHookConfig,
  PresidentsItem,
  PresidentsNumbersConfig,
  PresidentsSubsConfig,
  ResolutionLabel,
} from "@/lib/types/creator-reward";

const DEFAULT_SUBS: PresidentsSubsConfig = {
  enabled: false,
  font_choice: "Impact",
  highlight_color: "#BB0808",
  text_color: "#FFFFFF",
  stroke_color: "#000000",
  stroke_width: 3,
  case_mode: "UPPERCASE",
  font_scale: 0.04,
  max_words: 4,
  y_position: 0.62,
  shadow_enabled: false,
  shadow_color: "#000000",
  shadow_opacity: 0.8,
  shadow_blur: 33,
  shadow_distance: 8,
  shadow_angle: -45,
  highlight_mode: "pill",
  max_width: 0.85,
};

const DEFAULT_HOOK: PresidentsHookConfig = {
  enabled: false,
  duration: 5.0,
  animation: "swipe_left",
  y_position: 0.33,
  shadow_color: "#BB0808",
  box_color: "#FFFFFF",
  text_color: "#0B0B0B",
  font_scale: 0.02,
};

const DEFAULT_NUMBERS: PresidentsNumbersConfig = {
  font_choice: "Impact",
  mystery_text: "???",
  header_text: "",
  header_mode: "all",
  header_duration: 5.0,
  header_animation: "none",
  header_y_position: 0.07,
  header_font_scale: 0.024,
  header_text_color: "#0B0B0B",
  header_box_color: "#FFFFFF",
  header_shadow_color: "#1E01C4",
  list_x_position: 0.07,
  list_y_position: 0.32,
  list_line_spacing: 0.105,
  number_font_scale: 0.044,
  name_font_scale: 0.036,
  number_color: "#FFFFFF",
  number_medal_colors: true,
  number_color_gold: "#FFD700",
  number_color_silver: "#C0C0C0",
  number_color_bronze: "#CD7F32",
  name_color: "#FFFFFF",
  name_stroke_color: "#000000",
  name_stroke_width: 3,
};

const RESOLUTIONS: ResolutionLabel[] = [
  "1080p (Lento)",
  "720p (Medio)",
  "480p (Rápido)",
  "240p (Ultra Rápido)",
];

// Preset shape del backend (Streamlit-compatible): flat keys `subs_*` y `hook_*`.
// El frontend usa nested {subs:{...}, hook:{...}} — convertir en ambos sentidos.
function flatToNested(flat: Record<string, unknown>): {
  subs?: Partial<PresidentsSubsConfig>;
  hook?: Partial<PresidentsHookConfig>;
  numbers?: Partial<PresidentsNumbersConfig>;
  creativeMode?: boolean;
  engine?: EngineVersion;
  resolution?: ResolutionLabel;
} {
  // Si ya viene nested, úsalo tal cual
  if (typeof flat.subs === "object" && flat.subs !== null) {
    return flat as ReturnType<typeof flatToNested>;
  }
  const subs: Partial<PresidentsSubsConfig> = {};
  const hook: Partial<PresidentsHookConfig> = {};
  const numbers: Partial<PresidentsNumbersConfig> = {};
  const s = (k: string) => (typeof flat[k] === "string" ? (flat[k] as string) : undefined);
  const n = (k: string) => (typeof flat[k] === "number" ? (flat[k] as number) : undefined);
  const b = (k: string) => (typeof flat[k] === "boolean" ? (flat[k] as boolean) : undefined);

  if (b("subs_enabled") !== undefined) subs.enabled = b("subs_enabled");
  if (s("subs_font_choice")) subs.font_choice = s("subs_font_choice");
  if (s("subs_highlight_color")) subs.highlight_color = s("subs_highlight_color");
  if (s("subs_text_color")) subs.text_color = s("subs_text_color");
  if (s("subs_stroke_color")) subs.stroke_color = s("subs_stroke_color");
  if (n("subs_stroke_width") !== undefined) subs.stroke_width = n("subs_stroke_width");
  if (s("subs_case")) subs.case_mode = s("subs_case") as PresidentsSubsConfig["case_mode"];
  if (n("subs_font_scale") !== undefined) subs.font_scale = n("subs_font_scale");
  if (n("subs_max_words") !== undefined) subs.max_words = n("subs_max_words");
  if (n("subs_y_position") !== undefined) subs.y_position = n("subs_y_position");
  if (b("subs_shadow_enabled") !== undefined) subs.shadow_enabled = b("subs_shadow_enabled");
  if (s("subs_shadow_color")) subs.shadow_color = s("subs_shadow_color");
  if (n("subs_shadow_opacity") !== undefined) subs.shadow_opacity = n("subs_shadow_opacity");
  if (n("subs_shadow_blur") !== undefined) subs.shadow_blur = n("subs_shadow_blur");
  if (n("subs_shadow_distance") !== undefined) subs.shadow_distance = n("subs_shadow_distance");
  if (n("subs_shadow_angle") !== undefined) subs.shadow_angle = n("subs_shadow_angle");
  if (n("subs_max_width") !== undefined) subs.max_width = n("subs_max_width");
  if (s("subs_highlight_mode"))
    subs.highlight_mode = s("subs_highlight_mode") as PresidentsSubsConfig["highlight_mode"];

  if (b("hook_enabled") !== undefined) hook.enabled = b("hook_enabled");
  if (n("hook_duration") !== undefined) hook.duration = n("hook_duration");
  if (s("hook_animation"))
    hook.animation = s("hook_animation") as PresidentsHookConfig["animation"];
  if (n("hook_y_position") !== undefined) hook.y_position = n("hook_y_position");
  if (s("hook_shadow_color")) hook.shadow_color = s("hook_shadow_color");
  if (s("hook_box_color")) hook.box_color = s("hook_box_color");
  if (s("hook_text_color")) hook.text_color = s("hook_text_color");
  if (n("hook_font_scale") !== undefined) hook.font_scale = n("hook_font_scale");

  if (s("numbers_font_choice")) numbers.font_choice = s("numbers_font_choice");
  if (s("numbers_mystery_text") !== undefined)
    numbers.mystery_text = s("numbers_mystery_text");
  if (s("numbers_header_text") !== undefined)
    numbers.header_text = s("numbers_header_text");
  if (s("numbers_header_mode"))
    numbers.header_mode = s("numbers_header_mode") as PresidentsNumbersConfig["header_mode"];
  if (n("numbers_header_duration") !== undefined)
    numbers.header_duration = n("numbers_header_duration");
  if (s("numbers_header_animation"))
    numbers.header_animation = s("numbers_header_animation") as PresidentsNumbersConfig["header_animation"];
  if (n("numbers_header_y_position") !== undefined)
    numbers.header_y_position = n("numbers_header_y_position");
  if (n("numbers_header_font_scale") !== undefined)
    numbers.header_font_scale = n("numbers_header_font_scale");
  if (s("numbers_header_text_color")) numbers.header_text_color = s("numbers_header_text_color");
  if (s("numbers_header_box_color")) numbers.header_box_color = s("numbers_header_box_color");
  if (s("numbers_header_shadow_color")) numbers.header_shadow_color = s("numbers_header_shadow_color");
  if (n("numbers_list_x_position") !== undefined)
    numbers.list_x_position = n("numbers_list_x_position");
  if (n("numbers_list_y_position") !== undefined)
    numbers.list_y_position = n("numbers_list_y_position");
  if (n("numbers_list_line_spacing") !== undefined)
    numbers.list_line_spacing = n("numbers_list_line_spacing");
  if (n("numbers_number_font_scale") !== undefined)
    numbers.number_font_scale = n("numbers_number_font_scale");
  if (n("numbers_name_font_scale") !== undefined)
    numbers.name_font_scale = n("numbers_name_font_scale");
  if (s("numbers_number_color")) numbers.number_color = s("numbers_number_color");
  if (b("numbers_number_medal_colors") !== undefined)
    numbers.number_medal_colors = b("numbers_number_medal_colors");
  if (s("numbers_number_color_gold")) numbers.number_color_gold = s("numbers_number_color_gold");
  if (s("numbers_number_color_silver")) numbers.number_color_silver = s("numbers_number_color_silver");
  if (s("numbers_number_color_bronze")) numbers.number_color_bronze = s("numbers_number_color_bronze");
  if (s("numbers_name_color")) numbers.name_color = s("numbers_name_color");
  if (s("numbers_name_stroke_color")) numbers.name_stroke_color = s("numbers_name_stroke_color");
  if (n("numbers_name_stroke_width") !== undefined)
    numbers.name_stroke_width = n("numbers_name_stroke_width");

  return {
    subs,
    hook,
    numbers,
    creativeMode: b("creative_mode"),
    engine: s("engine_version") as EngineVersion | undefined,
    resolution: s("resolution") as ResolutionLabel | undefined,
  };
}

function nestedToFlat(
  subs: PresidentsSubsConfig,
  hook: PresidentsHookConfig,
  numbers: PresidentsNumbersConfig,
  creativeMode: boolean,
  engine: EngineVersion,
  resolution: ResolutionLabel,
): Record<string, unknown> {
  return {
    subs_enabled: subs.enabled,
    subs_font_choice: subs.font_choice,
    subs_highlight_color: subs.highlight_color,
    subs_text_color: subs.text_color,
    subs_stroke_color: subs.stroke_color,
    subs_stroke_width: subs.stroke_width,
    subs_case: subs.case_mode,
    subs_font_scale: subs.font_scale,
    subs_max_words: subs.max_words,
    subs_y_position: subs.y_position,
    subs_shadow_enabled: subs.shadow_enabled,
    subs_shadow_color: subs.shadow_color,
    subs_shadow_opacity: subs.shadow_opacity,
    subs_shadow_blur: subs.shadow_blur,
    subs_shadow_distance: subs.shadow_distance,
    subs_shadow_angle: subs.shadow_angle,
    subs_highlight_mode: subs.highlight_mode,
    subs_max_width: subs.max_width,
    hook_enabled: hook.enabled,
    hook_duration: hook.duration,
    hook_animation: hook.animation,
    hook_y_position: hook.y_position,
    hook_shadow_color: hook.shadow_color,
    hook_box_color: hook.box_color,
    hook_text_color: hook.text_color,
    hook_font_scale: hook.font_scale,
    numbers_font_choice: numbers.font_choice,
    numbers_mystery_text: numbers.mystery_text,
    numbers_header_text: numbers.header_text,
    numbers_header_mode: numbers.header_mode,
    numbers_header_duration: numbers.header_duration,
    numbers_header_animation: numbers.header_animation,
    numbers_header_y_position: numbers.header_y_position,
    numbers_header_font_scale: numbers.header_font_scale,
    numbers_header_text_color: numbers.header_text_color,
    numbers_header_box_color: numbers.header_box_color,
    numbers_header_shadow_color: numbers.header_shadow_color,
    numbers_list_x_position: numbers.list_x_position,
    numbers_list_y_position: numbers.list_y_position,
    numbers_list_line_spacing: numbers.list_line_spacing,
    numbers_number_font_scale: numbers.number_font_scale,
    numbers_name_font_scale: numbers.name_font_scale,
    numbers_number_color: numbers.number_color,
    numbers_number_medal_colors: numbers.number_medal_colors,
    numbers_number_color_gold: numbers.number_color_gold,
    numbers_number_color_silver: numbers.number_color_silver,
    numbers_number_color_bronze: numbers.number_color_bronze,
    numbers_name_color: numbers.name_color,
    numbers_name_stroke_color: numbers.name_stroke_color,
    numbers_name_stroke_width: numbers.name_stroke_width,
    creative_mode: creativeMode,
    engine_version: engine,
    resolution,
  };
}

export default function PresidentsPage() {
  const enqueue = useEnqueuePresidents();
  const openQueue = useDrawerStore((s) => s.openQueue);

  const [items, setItems] = useState<PresidentsItem[]>([emptyItem()]);
  const [creativeMode, setCreativeMode] = useLocalStorageState(
    "presidents.creative_mode.v2",
    false,
  );
  const [engine, setEngine] = useLocalStorageState<EngineVersion>(
    "presidents.engine.v2",
    "v2_estable",
  );
  const [resolution, setResolution] = useLocalStorageState<ResolutionLabel>(
    "presidents.resolution.v2",
    "1080p (Lento)",
  );
  const [subs, setSubs] = useLocalStorageState<PresidentsSubsConfig>(
    "presidents.subs.v2",
    DEFAULT_SUBS,
  );
  const [hook, setHook] = useLocalStorageState<PresidentsHookConfig>(
    "presidents.hook.v2",
    DEFAULT_HOOK,
  );
  const [numbers, setNumbers] = useLocalStorageState<PresidentsNumbersConfig>(
    "presidents.numbers.v1",
    DEFAULT_NUMBERS,
  );

  // Para PresetManager: enviar flat al guardar (compatible con Streamlit).
  const flatConfig = useMemo(
    () => nestedToFlat(subs, hook, numbers, creativeMode, engine, resolution),
    [subs, hook, numbers, creativeMode, engine, resolution],
  );

  function loadPreset(loaded: Record<string, unknown>) {
    const n = flatToNested(loaded);
    if (n.subs) setSubs({ ...DEFAULT_SUBS, ...n.subs });
    if (n.hook) setHook({ ...DEFAULT_HOOK, ...n.hook });
    if (n.numbers) setNumbers({ ...DEFAULT_NUMBERS, ...n.numbers });
    if (typeof n.creativeMode === "boolean") setCreativeMode(n.creativeMode);
    if (n.resolution) setResolution(n.resolution);
    if (n.engine) setEngine(n.engine);
  }

  // Auto-cargar __default en primera visita (sin localStorage previo).
  const [bootstrapped, setBootstrapped] = useLocalStorageState(
    "presidents.bootstrapped.v1",
    false,
  );
  const defaultPreset = usePresidentsPreset(bootstrapped ? null : "__default");
  useEffect(() => {
    if (!bootstrapped && defaultPreset.data) {
      loadPreset(defaultPreset.data.config);
      setBootstrapped(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrapped, defaultPreset.data]);

  function resetStyles() {
    setSubs(DEFAULT_SUBS);
    setHook(DEFAULT_HOOK);
    setNumbers(DEFAULT_NUMBERS);
    setCreativeMode(false);
    setEngine("v2_estable");
    setResolution("1080p (Lento)");
    toast.success("Estilos restablecidos a defaults.");
  }

  // La previsualización de la variante números refleja el primer vídeo que
  // la tenga activada (o el primero del lote).
  const numbersItem = items.find((it) => it.numbers_variant);
  const numbersActive = Boolean(numbersItem);
  const previewTopCount = numbersItem?.top_count ?? items[0]?.top_count ?? 5;

  async function submit() {
    if (items.length === 0) return;
    try {
      const res = await enqueue.mutateAsync({
        items,
        creative_mode: creativeMode,
        engine_version: engine,
        resolution,
        subs,
        hook,
        numbers,
      });
      toast.success(`${res.total_enqueued} vídeo(s) encolados.`);
      openQueue();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al encolar.");
    }
  }

  const canSubmit = items.length > 0 && !enqueue.isPending;

  return (
    <div className="container mx-auto space-y-4 p-6 md:p-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Presidentes Top 5</h1>
          <p className="text-sm text-muted-foreground">
            Genera rankings de presidentes USA con guion IA + assets locales.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={resetStyles}
          title="Restablece subs + hook + opciones globales a sus valores por defecto."
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset estilos
        </Button>
      </header>

      <CollapsibleCard
        title="Presets"
        subtitle="Cargar / guardar configuraciones de estilo"
      >
        <PresetManager config={flatConfig} onLoad={loadPreset} />
      </CollapsibleCard>

      <CollapsibleCard
        title="Ajustes globales"
        subtitle={`${resolution} · ${engine}${creativeMode ? " · ✨ creativo" : ""}`}
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Resolución</Label>
            <Select value={resolution} onValueChange={(v) => setResolution(v as ResolutionLabel)}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RESOLUTIONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Motor</Label>
            <Select value={engine} onValueChange={(v) => setEngine(v as EngineVersion)}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="v2_estable">v2_estable</SelectItem>
                <SelectItem value="v1_estable">v1_estable</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <label className="flex h-9 items-center gap-2 rounded-md border bg-background px-3 text-sm sm:col-span-2 lg:col-span-1">
            <Switch checked={creativeMode} onCheckedChange={setCreativeMode} />
            <span className="whitespace-nowrap">✨ Modo creativo</span>
          </label>
        </div>
      </CollapsibleCard>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <div className="min-w-0 space-y-4">
          <PresidentsBatchEditor items={items} onChange={setItems} />

          <CollapsibleCard
            title="Subtítulos karaoke"
            subtitle={
              subs.enabled
                ? `${subs.font_choice} · ${subs.highlight_mode} · ${subs.highlight_color}`
                : "Desactivado"
            }
          >
            <SubsConfigPanel value={subs} onChange={setSubs} />
          </CollapsibleCard>

          <CollapsibleCard
            title="Hook box"
            subtitle={
              hook.enabled
                ? `${hook.duration}s · ${hook.animation} · ${hook.shadow_color}`
                : "Desactivado"
            }
          >
            <HookConfigPanel value={hook} onChange={setHook} />
          </CollapsibleCard>

          <CollapsibleCard
            title="🔢 Variante números"
            subtitle={
              numbersActive
                ? `Activa · ${numbers.font_choice} · lista X=${numbers.list_x_position.toFixed(2)}`
                : "Actívala por vídeo arriba"
            }
          >
            <NumbersConfigPanel value={numbers} onChange={setNumbers} />
          </CollapsibleCard>
        </div>

        <div className="space-y-3 lg:sticky lg:top-6">
          <PresidentsPreview
            subs={subs}
            hook={hook}
            numbers={numbers}
            numbersActive={numbersActive}
            topCount={previewTopCount}
            onNumbersChange={(patch) => setNumbers({ ...numbers, ...patch })}
          />
          <Button
            onClick={submit}
            disabled={!canSubmit}
            size="lg"
            className="w-full"
          >
            {enqueue.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Encolar {items.length} vídeo{items.length === 1 ? "" : "s"}
          </Button>
        </div>
      </div>
    </div>
  );
}
