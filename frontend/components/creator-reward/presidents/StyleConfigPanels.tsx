"use client";

import { FontSelector } from "@/components/ui/font-selector";
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
import { useFonts } from "@/lib/queries/fonts";
import type {
  PresidentsHookConfig,
  PresidentsNumbersConfig,
  PresidentsSubsConfig,
} from "@/lib/types/creator-reward";

const HIGHLIGHT_MODES = [
  { value: "pill", label: "Pill" },
  { value: "color_swap", label: "Color swap" },
  { value: "underline", label: "Underline" },
  { value: "box_outline", label: "Box outline" },
  { value: "glow", label: "Glow" },
  { value: "none", label: "Sin marca" },
];

const ANIMATIONS = [
  { value: "swipe_left", label: "Swipe ←" },
  { value: "swipe_right", label: "Swipe →" },
  { value: "fade_in", label: "Fade in" },
  { value: "pop", label: "Pop" },
  { value: "none", label: "Sin anim." },
];

export function SubsConfigPanel({
  value,
  onChange,
}: {
  value: PresidentsSubsConfig;
  onChange: (next: PresidentsSubsConfig) => void;
}) {
  function patch<K extends keyof PresidentsSubsConfig>(key: K, v: PresidentsSubsConfig[K]) {
    onChange({ ...value, [key]: v });
  }

  // Presidentes mantiene `font_choice` como NOMBRE (back-compat con el
  // backend, que lo resuelve vía registry). El FontSelector trabaja con
  // PATHs absolutos — convertimos en ambas direcciones aquí.
  const fonts = useFonts();
  const fontEntries = fonts.data?.items ?? [];
  const currentPath =
    fontEntries.find((f) => f.name === value.font_choice)?.path ?? "";
  function setFontByPath(path: string) {
    const entry = fontEntries.find((f) => f.path === path);
    patch("font_choice", entry?.name ?? value.font_choice);
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm font-medium">
        <Switch
          checked={value.enabled}
          onCheckedChange={(v) => patch("enabled", v)}
        />
        Activar subtítulos
      </label>

      {value.enabled && (
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            <Field label="Fuente">
              <FontSelector value={currentPath} onChange={setFontByPath} />
            </Field>
            <Field label="Modo highlight">
              <Select
                value={value.highlight_mode}
                onValueChange={(v) =>
                  patch("highlight_mode", v as PresidentsSubsConfig["highlight_mode"])
                }
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HIGHLIGHT_MODES.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Case">
              <Select
                value={value.case_mode}
                onValueChange={(v) =>
                  patch("case_mode", v as PresidentsSubsConfig["case_mode"])
                }
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="UPPERCASE">UPPERCASE</SelectItem>
                  <SelectItem value="lowercase">lowercase</SelectItem>
                  <SelectItem value="Title Case">Title Case</SelectItem>
                  <SelectItem value="None">Sin cambio</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Max palabras">
              <Input
                type="number"
                min="1"
                max="10"
                className="h-9"
                value={value.max_words}
                onChange={(e) => patch("max_words", Number(e.target.value))}
              />
            </Field>

            <ColorField
              label="Highlight"
              value={value.highlight_color}
              onChange={(v) => patch("highlight_color", v)}
            />
            <ColorField
              label="Texto"
              value={value.text_color}
              onChange={(v) => patch("text_color", v)}
            />
            <ColorField
              label="Stroke"
              value={value.stroke_color}
              onChange={(v) => patch("stroke_color", v)}
            />
            <Field label="Stroke width">
              <Input
                type="number"
                min="0"
                max="10"
                className="h-9"
                value={value.stroke_width}
                onChange={(e) => patch("stroke_width", Number(e.target.value))}
              />
            </Field>

            <Field label="Y position">
              <Input
                type="number"
                step="0.05"
                min="0"
                max="1"
                className="h-9"
                value={value.y_position}
                onChange={(e) => patch("y_position", Number(e.target.value))}
              />
            </Field>
            <Field label="Font scale">
              <Input
                type="number"
                step="0.005"
                min="0.01"
                max="0.2"
                className="h-9"
                value={value.font_scale}
                onChange={(e) => patch("font_scale", Number(e.target.value))}
              />
            </Field>
            <Field label="Ancho máx.">
              <Input
                type="number"
                step="0.05"
                min="0.3"
                max="1"
                className="h-9"
                value={value.max_width}
                onChange={(e) => patch("max_width", Number(e.target.value))}
              />
            </Field>
          <label className="flex items-end gap-2 pb-1 text-sm">
            <Switch
              checked={value.shadow_enabled}
              onCheckedChange={(v) => patch("shadow_enabled", v)}
            />
            <span>Sombra</span>
          </label>
        </div>
      )}
    </div>
  );
}

export function HookConfigPanel({
  value,
  onChange,
}: {
  value: PresidentsHookConfig;
  onChange: (next: PresidentsHookConfig) => void;
}) {
  function patch<K extends keyof PresidentsHookConfig>(key: K, v: PresidentsHookConfig[K]) {
    onChange({ ...value, [key]: v });
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm font-medium">
        <Switch
          checked={value.enabled}
          onCheckedChange={(v) => patch("enabled", v)}
        />
        Activar hook box
      </label>

      {value.enabled && (
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            <Field label="Duración (s)">
              <Input
                type="number"
                step="0.5"
                min="0.5"
                max="30"
                className="h-9"
                value={value.duration}
                onChange={(e) => patch("duration", Number(e.target.value))}
              />
            </Field>
            <Field label="Animación">
              <Select
                value={value.animation}
                onValueChange={(v) =>
                  patch("animation", v as PresidentsHookConfig["animation"])
                }
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ANIMATIONS.map((a) => (
                    <SelectItem key={a.value} value={a.value}>
                      {a.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Y position">
              <Input
                type="number"
                step="0.05"
                min="0"
                max="1"
                className="h-9"
                value={value.y_position}
                onChange={(e) => patch("y_position", Number(e.target.value))}
              />
            </Field>
            <Field label="Font scale">
              <Input
                type="number"
                step="0.005"
                min="0.005"
                max="0.1"
                className="h-9"
                value={value.font_scale}
                onChange={(e) => patch("font_scale", Number(e.target.value))}
              />
            </Field>

            <ColorField
              label="Caja"
              value={value.box_color}
              onChange={(v) => patch("box_color", v)}
            />
            <ColorField
              label="Texto"
              value={value.text_color}
              onChange={(v) => patch("text_color", v)}
            />
          <ColorField
            label="Sombra"
            value={value.shadow_color}
            onChange={(v) => patch("shadow_color", v)}
          />
        </div>
      )}
    </div>
  );
}

export function NumbersConfigPanel({
  value,
  onChange,
}: {
  value: PresidentsNumbersConfig;
  onChange: (next: PresidentsNumbersConfig) => void;
}) {
  function patch<K extends keyof PresidentsNumbersConfig>(
    key: K,
    v: PresidentsNumbersConfig[K],
  ) {
    onChange({ ...value, [key]: v });
  }

  const fonts = useFonts();
  const fontEntries = fonts.data?.items ?? [];
  const currentPath =
    fontEntries.find((f) => f.name === value.font_choice)?.path ?? "";
  function setFontByPath(path: string) {
    const entry = fontEntries.find((f) => f.path === path);
    patch("font_choice", entry?.name ?? value.font_choice);
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Estilo de la variante números (header fijo + lista que se rellena). Se
        activa por vídeo desde el editor de arriba. Posiciona arrastrando en la
        previsualización.
      </p>

      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">
            Texto del header (vacío = usa el gancho del guion)
          </Label>
          <Input
            className="h-9"
            value={value.header_text}
            onChange={(e) => patch("header_text", e.target.value)}
            placeholder="Top 5 Worst US Presidents"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">
            Texto del #1 (incógnita)
          </Label>
          <Input
            className="h-9 w-28"
            value={value.mystery_text}
            onChange={(e) => patch("mystery_text", e.target.value)}
            placeholder="???"
          />
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        <Field label="Mostrar header">
          <Select
            value={value.header_mode}
            onValueChange={(v) =>
              patch("header_mode", v as PresidentsNumbersConfig["header_mode"])
            }
          >
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todo el vídeo</SelectItem>
              <SelectItem value="intro">Solo primeros seg.</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {value.header_mode === "intro" && (
          <>
            <Field label="Duración header (s)">
              <Input
                type="number"
                step="0.5"
                min="0.5"
                max="30"
                className="h-9"
                value={value.header_duration}
                onChange={(e) => patch("header_duration", Number(e.target.value))}
              />
            </Field>
            <Field label="Animación header">
              <Select
                value={value.header_animation}
                onValueChange={(v) =>
                  patch("header_animation", v as PresidentsNumbersConfig["header_animation"])
                }
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Sin anim.</SelectItem>
                  <SelectItem value="fade">Fade</SelectItem>
                  <SelectItem value="swipe_left">Swipe ←</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        <Field label="Fuente">
          <FontSelector value={currentPath} onChange={setFontByPath} />
        </Field>

        {/* Header */}
        <Field label="Header Y">
          <Input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="h-9"
            value={value.header_y_position}
            onChange={(e) => patch("header_y_position", Number(e.target.value))}
          />
        </Field>
        <Field label="Header tamaño">
          <Input
            type="number"
            step="0.002"
            min="0.01"
            max="0.1"
            className="h-9"
            value={value.header_font_scale}
            onChange={(e) => patch("header_font_scale", Number(e.target.value))}
          />
        </Field>
        <ColorField
          label="Header texto"
          value={value.header_text_color}
          onChange={(v) => patch("header_text_color", v)}
        />
        <ColorField
          label="Header caja"
          value={value.header_box_color}
          onChange={(v) => patch("header_box_color", v)}
        />
        <ColorField
          label="Header sombra"
          value={value.header_shadow_color}
          onChange={(v) => patch("header_shadow_color", v)}
        />

        {/* Lista */}
        <Field label="Lista X">
          <Input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="h-9"
            value={value.list_x_position}
            onChange={(e) => patch("list_x_position", Number(e.target.value))}
          />
        </Field>
        <Field label="Lista Y">
          <Input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="h-9"
            value={value.list_y_position}
            onChange={(e) => patch("list_y_position", Number(e.target.value))}
          />
        </Field>
        <Field label="Separación filas">
          <Input
            type="number"
            step="0.005"
            min="0.02"
            max="0.5"
            className="h-9"
            value={value.list_line_spacing}
            onChange={(e) => patch("list_line_spacing", Number(e.target.value))}
          />
        </Field>
        <Field label="Tamaño número">
          <Input
            type="number"
            step="0.002"
            min="0.01"
            max="0.2"
            className="h-9"
            value={value.number_font_scale}
            onChange={(e) => patch("number_font_scale", Number(e.target.value))}
          />
        </Field>
        <Field label="Tamaño nombre">
          <Input
            type="number"
            step="0.002"
            min="0.01"
            max="0.2"
            className="h-9"
            value={value.name_font_scale}
            onChange={(e) => patch("name_font_scale", Number(e.target.value))}
          />
        </Field>
        <ColorField
          label="Color base nº (4,5…)"
          value={value.number_color}
          onChange={(v) => patch("number_color", v)}
        />
        <label className="flex items-end gap-2 pb-1 text-sm">
          <Switch
            checked={value.number_medal_colors}
            onCheckedChange={(v) => patch("number_medal_colors", v)}
          />
          <span>Medallas 1/2/3</span>
        </label>
        {value.number_medal_colors && (
          <>
            <ColorField
              label="#1 Oro"
              value={value.number_color_gold}
              onChange={(v) => patch("number_color_gold", v)}
            />
            <ColorField
              label="#2 Plata"
              value={value.number_color_silver}
              onChange={(v) => patch("number_color_silver", v)}
            />
            <ColorField
              label="#3 Bronce"
              value={value.number_color_bronze}
              onChange={(v) => patch("number_color_bronze", v)}
            />
          </>
        )}
        <ColorField
          label="Color nombre"
          value={value.name_color}
          onChange={(v) => patch("name_color", v)}
        />
        <ColorField
          label="Nombre stroke"
          value={value.name_stroke_color}
          onChange={(v) => patch("name_stroke_color", v)}
        />
        <Field label="Stroke width">
          <Input
            type="number"
            min="0"
            max="10"
            className="h-9"
            value={value.name_stroke_width}
            onChange={(e) => patch("name_stroke_width", Number(e.target.value))}
          />
        </Field>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex h-9 items-center gap-2 rounded-md border border-input bg-background px-2">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent p-0 [&::-webkit-color-swatch-wrapper]:p-0 [&::-webkit-color-swatch]:rounded [&::-webkit-color-swatch]:border-0"
          aria-label={label}
        />
        <span className="flex-1 truncate font-mono text-xs uppercase text-muted-foreground">
          {value}
        </span>
      </div>
    </div>
  );
}
