"use client";

import { useRef, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { FontSelector } from "@/components/ui/font-selector";
import {
  buildSubsAutoFrameUrl,
  useSubsAutoHighlightModes,
  useSubsAutoPresets,
} from "@/lib/queries/creator-reward/subsAuto";
import { useFontByPath, useFontFamily } from "@/lib/queries/fonts";
import type {
  SubsAutoCaseMode,
  SubsAutoHighlightMode,
  SubsAutoStyleConfig,
} from "@/lib/types/creator-reward";

/**
 * Editor de estilos completo de Subs Auto.
 *
 * - Preset cycler (← →) en lugar de galería que ocupa espacio
 * - Todos los controles granulares (fuente, modo, colores, stroke, case,
 *   font_scale, max_words, max_width, sync_offset)
 * - Preview WYSIWYG con frame real del vídeo subido + subs CSS encima
 * - Drag vertical sobre la preview → actualiza `y_position` (CapCut-style)
 */
export function SubsAutoStyleEditor({
  style,
  onChange,
  inputPath,
  sampleText = "HELLO FROM THE OTHER SIDE",
  showSafeZones = false,
}: {
  style: SubsAutoStyleConfig;
  onChange: (next: SubsAutoStyleConfig) => void;
  inputPath: string;
  sampleText?: string;
  /** Si true, dibuja las zonas inseguras TikTok (15% arriba / 25% abajo)
   *  sobre el preview interno. Útil cuando no hay vídeo cargado (POV). */
  showSafeZones?: boolean;
}) {
  const presets = useSubsAutoPresets();
  const modes = useSubsAutoHighlightModes();
  const [presetIdx, setPresetIdx] = useState(-1); // -1 = custom
  const [frameSecond, setFrameSecond] = useState(1.0);
  const [frameBust, setFrameBust] = useState(0); // para forzar refetch del thumbnail

  const presetItems = presets.data?.items ?? [];

  function patch<K extends keyof SubsAutoStyleConfig>(
    key: K,
    value: SubsAutoStyleConfig[K],
  ) {
    onChange({ ...style, [key]: value });
    setPresetIdx(-1); // edición manual → custom
  }

  function applyPreset(idx: number) {
    const item = presetItems[idx];
    if (!item) return;
    onChange({ ...style, ...item.config });
    setPresetIdx(idx);
  }

  function cyclePreset(dir: 1 | -1) {
    if (presetItems.length === 0) return;
    const next =
      presetIdx < 0
        ? dir === 1
          ? 0
          : presetItems.length - 1
        : (presetIdx + dir + presetItems.length) % presetItems.length;
    applyPreset(next);
  }

  const currentPresetName =
    presetIdx >= 0 ? presetItems[presetIdx]?.name : "🎨 Custom";

  const frameUrl = inputPath
    ? `${buildSubsAutoFrameUrl(inputPath, frameSecond)}&_=${frameBust}`
    : null;

  return (
    <div className="space-y-3">
      {/* Preset cycler */}
      <div className="flex items-center gap-2 rounded-md border bg-card/50 p-2">
        <Sparkles className="h-4 w-4 shrink-0 text-primary" />
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={() => cyclePreset(-1)}
          disabled={presetItems.length === 0}
          aria-label="Preset anterior"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1 truncate text-center text-sm font-medium">
          {presets.isLoading ? "Cargando presets…" : currentPresetName}
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={() => cyclePreset(1)}
          disabled={presetItems.length === 0}
          aria-label="Preset siguiente"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-start">
        {/* Controles */}
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-3">
          <Field label="Fuente">
            <FontSelector
              value={style.font_path}
              onChange={(v) => patch("font_path", v)}
            />
          </Field>

          <Field label="Modo highlight">
            <Select
              value={style.highlight_mode}
              onValueChange={(v) =>
                patch("highlight_mode", v as SubsAutoHighlightMode)
              }
            >
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(modes.data?.items ?? []).map((m) => (
                  <SelectItem key={m.value} value={m.value}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Case">
            <Select
              value={style.case_mode}
              onValueChange={(v) => patch("case_mode", v as SubsAutoCaseMode)}
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

          <ColorField
            label="Highlight"
            value={style.highlight_color}
            onChange={(v) => patch("highlight_color", v)}
          />
          <ColorField
            label="Texto"
            value={style.text_color}
            onChange={(v) => patch("text_color", v)}
          />
          <ColorField
            label="Stroke"
            value={style.stroke_color}
            onChange={(v) => patch("stroke_color", v)}
          />

          <Field label="Stroke width">
            <Input
              type="number"
              min="0"
              max="10"
              className="h-9"
              value={style.stroke_width}
              onChange={(e) => patch("stroke_width", Number(e.target.value))}
            />
          </Field>
          <Field label="Font scale">
            <Input
              type="number"
              step="0.005"
              min="0.01"
              max="0.2"
              className="h-9"
              value={style.font_scale}
              onChange={(e) => patch("font_scale", Number(e.target.value))}
            />
          </Field>
          <Field label="Max palabras">
            <Input
              type="number"
              min="1"
              max="10"
              className="h-9"
              value={style.max_words}
              onChange={(e) => patch("max_words", Number(e.target.value))}
            />
          </Field>

          <Field label="Y position">
            <Input
              type="number"
              step="0.02"
              min="0"
              max="1"
              className="h-9"
              value={style.y_position}
              onChange={(e) => patch("y_position", Number(e.target.value))}
            />
          </Field>
          <Field label="Ancho máx.">
            <Input
              type="number"
              step="0.05"
              min="0.3"
              max="1"
              className="h-9"
              value={style.max_width}
              onChange={(e) => patch("max_width", Number(e.target.value))}
            />
          </Field>
          <Field label="Sync offset (ms)">
            <Input
              type="number"
              step="50"
              min="-2000"
              max="2000"
              className="h-9"
              value={style.sync_offset}
              onChange={(e) => patch("sync_offset", Number(e.target.value))}
            />
          </Field>

          <label className="col-span-full flex items-center gap-2 pt-1 text-sm">
            <Switch
              checked={style.pill_enabled}
              onCheckedChange={(v) => patch("pill_enabled", v)}
            />
            Píldora detrás (legacy)
          </label>
        </div>

        {/* Preview */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold">Preview · arrastra para Y</p>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={() => setFrameBust((n) => n + 1)}
              aria-label="Refrescar frame"
              title="Refrescar frame"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
          <SubsAutoPreview
            frameUrl={frameUrl}
            style={style}
            sampleText={sampleText}
            onYChange={(y) => patch("y_position", y)}
            showSafeZones={showSafeZones}
          />
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground">
              Segundo del vídeo: {frameSecond.toFixed(1)}s
            </Label>
            <input
              type="range"
              min="0"
              max="60"
              step="0.5"
              value={frameSecond}
              onChange={(e) => setFrameSecond(Number(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preview component — frame real + subs CSS encima + drag vertical
// ---------------------------------------------------------------------------
function SubsAutoPreview({
  frameUrl,
  style,
  sampleText,
  onYChange,
  showSafeZones = false,
}: {
  frameUrl: string | null;
  style: SubsAutoStyleConfig;
  sampleText: string;
  onYChange: (y: number) => void;
  showSafeZones?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef(false);
  const selectedFont = useFontByPath(style.font_path);
  const previewFontFamily = useFontFamily(selectedFont);

  function handlePointerDown(e: React.PointerEvent) {
    if (!containerRef.current) return;
    dragRef.current = true;
    (e.target as Element).setPointerCapture(e.pointerId);
    updateY(e.clientY);
  }
  function handlePointerMove(e: React.PointerEvent) {
    if (!dragRef.current) return;
    updateY(e.clientY);
  }
  function handlePointerUp(e: React.PointerEvent) {
    dragRef.current = false;
    try {
      (e.target as Element).releasePointerCapture(e.pointerId);
    } catch {
      // noop
    }
  }
  function updateY(clientY: number) {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const ratio = (clientY - rect.top) / rect.height;
    onYChange(Math.max(0, Math.min(1, Number(ratio.toFixed(2)))));
  }

  const words = sampleText.split(/\s+/).filter(Boolean);
  const chunk = words.slice(0, Math.min(style.max_words, words.length));
  const activeIdx = Math.min(2, chunk.length - 1);

  return (
    <div
      ref={containerRef}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      className="relative cursor-ns-resize touch-none select-none overflow-hidden rounded-md border bg-black"
      style={{
        aspectRatio: "9 / 16",
        backgroundImage: frameUrl ? `url('${frameUrl}')` : undefined,
        backgroundSize: "cover",
        backgroundPosition: "center",
        containerType: "size",
      }}
    >
      {/* Zonas inseguras TikTok (15% arriba, 25% abajo). Opcional —
          se activa con `showSafeZones`. */}
      {showSafeZones && (
        <>
          <div
            className="pointer-events-none absolute inset-x-0 top-0 border-b border-dashed border-amber-400/40 bg-amber-400/5"
            style={{ height: "15%" }}
          />
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-dashed border-amber-400/40 bg-amber-400/5"
            style={{ height: "25%" }}
          />
          <span className="pointer-events-none absolute right-1 top-1 rounded bg-amber-500/70 px-1 text-[8px] font-medium text-black">
            no-safe
          </span>
        </>
      )}

      {/* Línea Y indicator */}
      <div
        className="pointer-events-none absolute inset-x-0 h-px bg-cyan-400/60"
        style={{ top: `${style.y_position * 100}%` }}
      />
      <span
        className="pointer-events-none absolute left-1 rounded bg-cyan-500/80 px-1 text-[8px] font-medium text-black"
        style={{ top: `calc(${style.y_position * 100}% - 6px)` }}
      >
        Y={style.y_position.toFixed(2)}
      </span>

      {/* Subs chunk */}
      <div
        className="pointer-events-none absolute flex flex-wrap items-center justify-center text-center"
        style={{
          left: "50%",
          top: `${style.y_position * 100}%`,
          transform: "translate(-50%, -50%)",
          width: `${style.max_width * 100}%`,
          gap: "0.2em",
          fontSize: `${style.font_scale * 100 * (16 / 9)}cqi`,
          fontFamily: previewFontFamily,
          // Bundled: peso natural del TTF (no faux-bold). System: 900.
          fontWeight: selectedFont?.source === "bundled" ? "normal" : 900,
          fontSynthesis: "none",
          lineHeight: 1.05,
          letterSpacing: "0.01em",
          textShadow: buildStroke(style),
        }}
      >
        {chunk.map((word, i) => (
          <span
            key={i}
            className="inline-block"
            style={highlightStyle(style, i === activeIdx)}
          >
            {transformCase(word, style.case_mode)}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
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

function transformCase(text: string, mode: SubsAutoCaseMode): string {
  switch (mode) {
    case "UPPERCASE":
      return text.toUpperCase();
    case "lowercase":
      return text.toLowerCase();
    case "Title Case":
      return text.replace(
        /\w\S*/g,
        (w) => w[0]!.toUpperCase() + w.slice(1).toLowerCase(),
      );
    default:
      return text;
  }
}

function buildStroke(style: SubsAutoStyleConfig): string {
  if (style.stroke_width <= 0) return "none";
  const em = style.stroke_width / 80;
  const dirs: [number, number][] = [
    [-1, -1], [0, -1], [1, -1],
    [-1, 0],           [1, 0],
    [-1, 1],  [0, 1],  [1, 1],
  ];
  return dirs
    .map(
      ([dx, dy]) =>
        `${(dx * em).toFixed(3)}em ${(dy * em).toFixed(3)}em 0 ${style.stroke_color}`,
    )
    .join(", ");
}

function highlightStyle(
  style: SubsAutoStyleConfig,
  active: boolean,
): React.CSSProperties {
  const base: React.CSSProperties = {
    color: style.text_color,
    padding: "0 0.05em",
  };
  if (!active) return base;
  switch (style.highlight_mode) {
    case "pill":
      return {
        ...base,
        backgroundColor: style.highlight_color,
        color: style.text_color,
        padding: "0.12em 0.3em",
        borderRadius: "0.1em",
      };
    case "color_swap":
      return { ...base, color: style.highlight_color };
    case "underline":
      return {
        ...base,
        textDecoration: `underline ${style.highlight_color}`,
        textUnderlineOffset: "0.15em",
        textDecorationThickness: "0.1em",
      };
    case "box_outline":
      return {
        ...base,
        boxShadow: `inset 0 0 0 0.08em ${style.highlight_color}`,
        borderRadius: "0.1em",
        padding: "0.05em 0.15em",
      };
    case "glow":
      return {
        ...base,
        textShadow: `0 0 10px ${style.highlight_color}, 0 0 20px ${style.highlight_color}`,
      };
    case "none":
    default:
      return base;
  }
}

