"use client";

import { ArrowDown, ChevronDown, ChevronRight, Loader2, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  StickerPreview9x16,
  type StickerPreviewConfig,
} from "@/components/editor-auto/StickerPreview9x16";
import {
  PhotoPreview9x16,
  type PhotoPreviewConfig,
} from "@/components/editor-auto/PhotoPreview9x16";
import { SubsPreview9x16, type SubsPreviewConfig } from "@/components/editor-auto/SubsPreview9x16";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  useArrowStickers,
  useEditorAutoTools,
  useEditorUser,
  useUpdateEditorUser,
} from "@/lib/queries/editor-auto";
import { useFonts } from "@/lib/queries/fonts";
import { useSubsAutoPresets } from "@/lib/queries/creator-reward/subsAuto";
import type { ConfigSchemaField, ToolStep } from "@/lib/types/editor-auto";

export function UserFlowEditor({ userId }: { userId: string }) {
  const user = useEditorUser(userId);
  const tools = useEditorAutoTools();
  const update = useUpdateEditorUser(userId);

  const [steps, setSteps] = useState<ToolStep[]>([]);

  useEffect(() => {
    if (user.data) setSteps(user.data.tool_flow);
  }, [user.data]);

  if (user.isLoading || tools.isLoading) {
    return (
      <Card>
        <CardContent className="flex h-64 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!user.data || !tools.data) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-destructive">
          Error cargando usuario o tools.
        </CardContent>
      </Card>
    );
  }

  const orderedTools = [...tools.data].sort(
    (a, b) => a.position_weight - b.position_weight,
  );
  const stepsOrderedForPreview = [...steps]
    .map((s, i) => ({ ...s, _originalIdx: i }))
    .filter((s) => s.enabled)
    .sort((a, b) => {
      const wA = tools.data!.find((t) => t.tool_id === a.tool_id)?.position_weight ?? 999;
      const wB = tools.data!.find((t) => t.tool_id === b.tool_id)?.position_weight ?? 999;
      return wA - wB;
    });

  const usedToolIds = new Set(steps.map((s) => s.tool_id));
  const availableToAdd = orderedTools.filter((t) => !usedToolIds.has(t.tool_id));

  const addTool = (toolId: string) => {
    const tool = tools.data!.find((t) => t.tool_id === toolId);
    if (!tool) return;
    setSteps([
      ...steps,
      { tool_id: toolId, enabled: true, config: { ...tool.default_config } },
    ]);
  };

  const removeStep = (idx: number) => {
    setSteps(steps.filter((_, i) => i !== idx));
  };

  const toggleStep = (idx: number, enabled: boolean) => {
    setSteps(steps.map((s, i) => (i === idx ? { ...s, enabled } : s)));
  };

  const updateStepConfig = (idx: number, key: string, value: unknown) => {
    setSteps(
      steps.map((s, i) =>
        i === idx ? { ...s, config: { ...s.config, [key]: value } } : s,
      ),
    );
  };

  const applyPresetToStep = (idx: number, presetCfg: Record<string, unknown>) => {
    setSteps(
      steps.map((s, i) =>
        i === idx ? { ...s, config: { ...s.config, ...presetCfg } } : s,
      ),
    );
  };

  const handleSave = () => {
    update.mutate({ tool_flow: steps });
  };

  const dirty =
    JSON.stringify(steps) !==
    JSON.stringify(user.data.tool_flow);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Flujo de <code>{user.data.name}</code>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
              Orden de ejecución (auto-ordenado por peso)
            </Label>
            <div className="mt-2 space-y-1">
              {stepsOrderedForPreview.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Sin herramientas habilitadas. Añade alguna abajo.
                </p>
              ) : (
                stepsOrderedForPreview.map((s, idx) => {
                  const tool = tools.data!.find((t) => t.tool_id === s.tool_id);
                  return (
                    <div key={s._originalIdx} className="flex items-center gap-2 text-sm">
                      <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                        {idx + 1}
                      </span>
                      {tool?.display_name ?? s.tool_id}
                      <Badge variant="outline" className="text-xs">
                        peso {tool?.position_weight ?? "?"}
                      </Badge>
                      {idx < stepsOrderedForPreview.length - 1 && (
                        <ArrowDown className="h-3 w-3 text-muted-foreground" />
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {steps.length > 0 && (
            <div className="space-y-3">
              <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                Herramientas configuradas
              </Label>
              {steps.map((step, idx) => {
                const tool = tools.data!.find((t) => t.tool_id === step.tool_id);
                if (!tool) return null;
                return (
                  <StepCard
                    key={`${step.tool_id}-${idx}`}
                    step={step}
                    tool={tool}
                    onRemove={() => removeStep(idx)}
                    onToggle={(en) => toggleStep(idx, en)}
                    onConfigChange={(k, v) => updateStepConfig(idx, k, v)}
                    onApplyPreset={(cfg) => applyPresetToStep(idx, cfg)}
                  />
                );
              })}
            </div>
          )}

          {availableToAdd.length > 0 && (
            <div>
              <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                Añadir herramienta
              </Label>
              <div className="mt-2 flex flex-wrap gap-2">
                {availableToAdd.map((t) => (
                  <Button
                    key={t.tool_id}
                    variant="outline"
                    size="sm"
                    onClick={() => addTool(t.tool_id)}
                  >
                    <Plus className="mr-1 h-3 w-3" />
                    {t.display_name}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button onClick={handleSave} disabled={!dirty || update.isPending}>
              {update.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Guardar flujo
            </Button>
            {dirty && (
              <span className="text-xs text-muted-foreground">
                Hay cambios sin guardar.
              </span>
            )}
            {update.isError && (
              <span className="text-xs text-destructive">
                {(update.error as Error).message}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StepCard({
  step,
  tool,
  onRemove,
  onToggle,
  onConfigChange,
  onApplyPreset,
}: {
  step: ToolStep;
  tool: { tool_id: string; display_name: string; description: string; config_schema: ConfigSchemaField[] };
  onRemove: () => void;
  onToggle: (enabled: boolean) => void;
  onConfigChange: (key: string, value: unknown) => void;
  onApplyPreset: (config: Record<string, unknown>) => void;
}) {
  const [open, setOpen] = useState(false);
  // Si la tool es `subs_auto`, las claves de su config_schema coinciden con
  // las que pinta el preview (font_path, highlight_*, text_color, etc.) →
  // basta con castear `step.config` a `SubsPreviewConfig`.
  const isSubsAuto = tool.tool_id === "subs_auto";
  const subsPreviewConfig: SubsPreviewConfig | null = isSubsAuto
    ? {
        font_path: String(step.config.font_path ?? ""),
        highlight_mode: String(step.config.highlight_mode ?? "pill"),
        highlight_color: String(step.config.highlight_color ?? "#BB0808"),
        text_color: String(step.config.text_color ?? "#FFFFFF"),
        stroke_color: String(step.config.stroke_color ?? "#000000"),
        stroke_width: Number(step.config.stroke_width ?? 3),
        case_mode: String(step.config.case_mode ?? "UPPERCASE"),
        font_scale: Number(step.config.font_scale ?? 0.045),
        max_words: Number(step.config.max_words ?? 3),
        y_position: Number(step.config.y_position ?? 0.78),
        max_width: Number(step.config.max_width ?? 0.85),
      }
    : null;
  const isStickerArrow = tool.tool_id === "sticker_arrow";
  const stickerPreviewConfig: StickerPreviewConfig | null = isStickerArrow
    ? {
        sticker_file: String(step.config.sticker_file ?? ""),
        position_x_pct: Number(step.config.position_x_pct ?? 50),
        position_y_pct: Number(step.config.position_y_pct ?? 80),
        scale_width_pct: Number(step.config.scale_width_pct ?? 25),
        // `rotation_deg` puede llegar como string del select; normalizamos
        // a number aquí para que el preview CSS lo aplique sin parsear.
        rotation_deg: Number(step.config.rotation_deg ?? 0),
        flip_horizontal: Boolean(step.config.flip_horizontal ?? false),
        flip_vertical: Boolean(step.config.flip_vertical ?? false),
      }
    : null;
  const isPhotoInsert = tool.tool_id === "photo_insert";
  const photoPreviewConfig: PhotoPreviewConfig | null = isPhotoInsert
    ? {
        position_x_pct: Number(step.config.position_x_pct ?? 50),
        position_y_pct: Number(step.config.position_y_pct ?? 28),
        scale_width_pct: Number(step.config.scale_width_pct ?? 38),
      }
    : null;
  const hasPreview = Boolean(
    subsPreviewConfig || stickerPreviewConfig || photoPreviewConfig,
  );
  return (
    <div className="rounded-md border bg-card/50">
      <div className="flex items-center gap-2 p-2">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="text-muted-foreground hover:text-foreground"
          aria-label={open ? "Colapsar" : "Expandir"}
        >
          {open ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </button>
        <span className="flex-1 text-sm font-medium">{tool.display_name}</span>
        <Switch checked={step.enabled} onCheckedChange={onToggle} />
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onRemove}
          aria-label="Quitar"
        >
          <X className="h-3.5 w-3.5 text-destructive" />
        </Button>
      </div>
      {open && (
        <div className="border-t bg-muted/30 p-3">
          <p className="mb-3 text-xs text-muted-foreground">{tool.description}</p>
          <div
            className={
              hasPreview ? "grid gap-4 lg:grid-cols-[1fr_280px]" : "space-y-3"
            }
          >
            <div className="space-y-3">
              {tool.config_schema.map((field) => (
                <ConfigField
                  key={field.key}
                  field={field}
                  value={step.config[field.key] as unknown}
                  onChange={(v) => onConfigChange(field.key, v)}
                  onApplyPreset={onApplyPreset}
                />
              ))}
            </div>
            {subsPreviewConfig && (
              <div className="lg:sticky lg:top-4 lg:h-fit">
                <SubsPreview9x16
                  config={subsPreviewConfig}
                  onYChange={(y) => onConfigChange("y_position", y)}
                />
              </div>
            )}
            {stickerPreviewConfig && (
              <div className="lg:sticky lg:top-4 lg:h-fit">
                <StickerPreview9x16
                  config={stickerPreviewConfig}
                  onPositionChange={(x, y) => {
                    onConfigChange("position_x_pct", x);
                    onConfigChange("position_y_pct", y);
                  }}
                  onScaleChange={(s) => onConfigChange("scale_width_pct", s)}
                  onRotationChange={(deg) =>
                    onConfigChange("rotation_deg", deg)
                  }
                />
              </div>
            )}
            {photoPreviewConfig && (
              <div className="lg:sticky lg:top-4 lg:h-fit">
                <PhotoPreview9x16
                  config={photoPreviewConfig}
                  onPositionChange={(x, y) => {
                    onConfigChange("position_x_pct", x);
                    onConfigChange("position_y_pct", y);
                  }}
                  onScaleChange={(s) => onConfigChange("scale_width_pct", s)}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ConfigField({
  field,
  value,
  onChange,
  onApplyPreset,
}: {
  field: ConfigSchemaField;
  value: unknown;
  onChange: (v: unknown) => void;
  /** Solo relevante para `preset_picker` — aplica un preset completo. */
  onApplyPreset?: (config: Record<string, unknown>) => void;
}) {
  const id = `cfg-${field.key}`;
  if (field.type === "font_picker") {
    return <FontPickerField id={id} field={field} value={value} onChange={onChange} />;
  }
  if (field.type === "select_sticker") {
    return <StickerPickerField id={id} field={field} value={value} onChange={onChange} />;
  }
  if (field.type === "preset_picker") {
    return (
      <PresetPickerField
        id={id}
        field={field}
        value={value}
        onChange={onChange}
        onApplyPreset={onApplyPreset}
      />
    );
  }
  if (field.type === "bool") {
    return (
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{field.label}</Label>
        <Switch
          id={id}
          checked={Boolean(value)}
          onCheckedChange={(v) => onChange(Boolean(v))}
        />
      </div>
    );
  }
  if (field.type === "select" && field.options) {
    return (
      <div className="space-y-1">
        <Label htmlFor={id}>{field.label}</Label>
        <select
          id={id}
          className="w-full rounded border bg-background p-1.5 text-sm"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (field.type === "text") {
    return (
      <div className="space-y-1">
        <Label htmlFor={id}>{field.label}</Label>
        <Textarea
          id={id}
          rows={3}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    );
  }
  if (field.type === "color") {
    return (
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{field.label}</Label>
        <input
          id={id}
          type="color"
          className="h-8 w-12 cursor-pointer rounded border bg-background"
          value={String(value ?? "#000000")}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    );
  }
  if (field.type === "int" || field.type === "float") {
    return (
      <div className="space-y-1">
        <Label htmlFor={id}>{field.label}</Label>
        <Input
          id={id}
          type="number"
          min={field.min}
          max={field.max}
          step={field.step ?? (field.type === "int" ? 1 : 0.01)}
          value={typeof value === "number" ? value : Number(value ?? 0)}
          onChange={(e) =>
            onChange(
              field.type === "int"
                ? parseInt(e.target.value, 10)
                : parseFloat(e.target.value),
            )
          }
        />
      </div>
    );
  }
  // string — caja de texto por defecto.
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{field.label}</Label>
      <Input
        id={id}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

/** Basename de un path que puede venir con separadores Windows o POSIX.
 * `os.path.basename` en Linux NO trata `\` como separador, así que un path
 * Windows guardado en localStorage (dev local) o en un preset viejo se vería
 * entero en la UI. Aquí dividimos manualmente por `/` y `\` antes de mostrar. */
function crossPlatformBasename(path: string): string {
  if (!path) return "";
  const normalized = path.replace(/\\/g, "/");
  const i = normalized.lastIndexOf("/");
  return i >= 0 ? normalized.slice(i + 1) : normalized;
}

function FontPickerField({
  id,
  field,
  value,
  onChange,
}: {
  id: string;
  field: ConfigSchemaField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const fonts = useFonts();
  const items = fonts.data?.items ?? [];
  const current = String(value ?? "");
  // Match cross-platform: si el path exacto no está, intentamos resolver
  // por basename (caso típico: la config se creó en local Windows con path
  // `C:\Users\…\Rubik-Bold.ttf` y ahora estamos en producción Linux con
  // `/usr/share/fonts/…/Rubik-Bold.ttf`). Si el basename coincide con
  // alguna fuente del registry, usamos esa como "selected".
  const exactMatch = items.find((f) => f.path === current);
  const currentBase = crossPlatformBasename(current).toLowerCase();
  const basenameMatch = exactMatch
    ? null
    : items.find(
        (f) => crossPlatformBasename(f.path).toLowerCase() === currentBase,
      );
  const resolved = exactMatch ?? basenameMatch;
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{field.label}</Label>
      <select
        id={id}
        className="w-full rounded border bg-background p-1.5 text-sm"
        value={resolved ? resolved.path : current}
        onChange={(e) => onChange(e.target.value)}
        disabled={fonts.isLoading}
      >
        {fonts.isLoading && <option value="">cargando…</option>}
        {!fonts.isLoading && !resolved && (
          // No matchea ni por path ni por basename → mostramos solo el
          // nombre del archivo (no la ruta completa, que es ruido feo
          // tipo "D:\Proyectos…\Rubik-Bold.ttf").
          <option value={current}>
            {current ? `${crossPlatformBasename(current)} ·sin resolver` : "—"}
          </option>
        )}
        {items.map((f) => (
          <option key={f.path} value={f.path}>
            {f.name} {f.source === "bundled" ? "·bundled" : "·sistema"}
          </option>
        ))}
      </select>
    </div>
  );
}

function PresetPickerField({
  id,
  field,
  onApplyPreset,
}: {
  id: string;
  field: ConfigSchemaField;
  value: unknown;
  onChange: (v: unknown) => void;
  onApplyPreset?: (config: Record<string, unknown>) => void;
}) {
  const presets = useSubsAutoPresets();
  const items = presets.data?.items ?? [];
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{field.label}</Label>
      <select
        id={id}
        className="w-full rounded border bg-background p-1.5 text-sm"
        defaultValue=""
        onChange={(e) => {
          const sel = items.find((p) => p.name === e.target.value);
          if (sel && onApplyPreset) {
            // El preset trae font_path, highlight_*, etc. Mergeamos en la
            // config del step para que el preview reaccione al instante.
            // Cast doble: TS rechaza el cast directo porque
            // `SubsAutoStyleConfig` no tiene index signature.
            // `as unknown as Record<string, unknown>` es el escape
            // estándar recomendado por TS para estos casos.
            onApplyPreset(sel.config as unknown as Record<string, unknown>);
          }
          e.currentTarget.value = "";
        }}
        disabled={presets.isLoading}
      >
        <option value="">— aplicar preset rápido —</option>
        {items.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Convierte un nombre de archivo en label amistoso, p. ej.
 * `flecha_roja.mov` → "Flecha roja", `arrow-down-red.gif` → "Arrow down red".
 * Quita extensión, sustituye separadores por espacios, capitaliza inicial. */
function prettyFilename(filename: string): string {
  if (!filename) return "";
  const stem = filename.replace(/\.[^.]+$/, "");
  const words = stem.replace(/[_\-.]+/g, " ").trim();
  if (!words) return filename;
  return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
}

function formatStickerSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function StickerPickerField({
  id,
  field,
  value,
  onChange,
}: {
  id: string;
  field: ConfigSchemaField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const stickers = useArrowStickers();
  const items = stickers.data?.files ?? [];
  const current = String(value ?? "");
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{field.label}</Label>
      <select
        id={id}
        className="w-full rounded border bg-background p-1.5 text-sm"
        value={current}
        onChange={(e) => onChange(e.target.value)}
        disabled={stickers.isLoading}
      >
        {stickers.isLoading && <option value="">cargando…</option>}
        {!stickers.isLoading && (
          <option value="">— elige sticker —</option>
        )}
        {items.map((s) => {
          const ext = (s.ext || "").replace(/^\./, "").toUpperCase() || "?";
          return (
            <option key={s.filename} value={s.filename}>
              {prettyFilename(s.filename)} · {ext} · {formatStickerSize(s.size_bytes)}
            </option>
          );
        })}
      </select>
      {!stickers.isLoading && items.length === 0 && (
        <p className="text-[10px] text-muted-foreground">
          Sin stickers. Deposita archivos {".mov / .webm / .gif"} en{" "}
          <code className="break-all">{stickers.data?.folder}</code>.
        </p>
      )}
    </div>
  );
}
