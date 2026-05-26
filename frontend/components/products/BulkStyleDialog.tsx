"use client";

import { useMemo, useRef, useState } from "react";
import { Eye, EyeOff, Loader2, Paintbrush, Subtitles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FontSelector } from "@/components/ui/font-selector";
import { useFontByPath, useFontFamily } from "@/lib/queries/fonts";
import { useBulkApplyPresetStyle } from "@/lib/queries/products";
import type {
  Product,
  SubtitleStyle,
  TextOverlayStyle,
} from "@/lib/types/product";
import { cn } from "@/lib/utils";

const OVERLAY_ANIMATIONS = [
  "none",
  "fade_in",
  "slide_up",
  "slide_down",
  "pop",
  "typing",
  "shake",
  "bounce",
] as const;

const OVERLAY_BACKGROUNDS = [
  "none",
  "black_bar",
  "white_bar",
  "blur",
] as const;

const SUBS_ANIMATIONS = [
  "none",
  "fade_in",
  "pop",
  "shake",
  "bounce",
] as const;

const SUBS_HIGHLIGHT_MODES = [
  { value: "pill", label: "Pill (banda color)" },
  { value: "color_swap", label: "Cambio color" },
  { value: "underline", label: "Subrayado" },
  { value: "box_outline", label: "Borde caja" },
  { value: "glow", label: "Glow / brillo" },
  { value: "none", label: "Sin destacar (palabra a palabra plano)" },
] as const;

const SCOPES = [
  { value: "all", label: "Todos los presets" },
  { value: "music", label: "Solo música (sin voz)" },
  { value: "scripted", label: "Solo scripted (con voz)" },
  { value: "viral_replica", label: "Solo réplicas virales" },
] as const;

type Scope = (typeof SCOPES)[number]["value"];

/** Pinta la cantidad de presets en cada scope para que el user sepa
 *  cuántos va a afectar antes de aplicar. */
function countByScope(product: Product, scope: Scope): number {
  const presets = product.video_presets ?? [];
  if (scope === "all") return presets.length;
  if (scope === "music") return presets.filter((p) => p.kind === "music").length;
  if (scope === "scripted") return presets.filter((p) => p.kind === "scripted").length;
  return presets.filter((p) => p.source === "viral_replica").length;
}

/** Toma como template el estilo del primer preset (o defaults). El user
 *  edita estos valores y al pulsar 'Aplicar' se mandan al backend para
 *  aplicar a todos los presets del scope. */
function pickInitialOverlayStyle(product: Product): TextOverlayStyle {
  const first = product.video_presets?.[0]?.text_overlay_style;
  const base = first ?? {
    font: "",
    size_px: 56,
    color: "#FFFFFF",
    stroke_color: "#000000",
    stroke_width: 6,
    position: "top_center",
    animation: "fade_in",
    uppercase: true,
    background: "none",
    duration_s: 4.0,
  };
  return { ...base, position_y_pct: base.position_y_pct ?? 12.0 };
}

function pickInitialSubtitleStyle(product: Product): SubtitleStyle {
  const first =
    product.video_presets?.find((p) => p.subtitle_style?.enabled)
      ?.subtitle_style ?? product.video_presets?.[0]?.subtitle_style;
  const base = first ?? {
    enabled: true,
    font: "",
    size_px: 42,
    color: "#FFFFFF",
    stroke_color: "#000000",
    stroke_width: 5,
    position: "bottom_center",
    highlight_color: "#FACC15",
    max_words_per_line: 3,
    uppercase: false,
    animation: "fade_in",
    margin_x_pct: 8.0,
  };
  return {
    ...base,
    position_y_pct: base.position_y_pct ?? 75.0,
    highlight_mode: base.highlight_mode ?? "pill",
    margin_x_pct: base.margin_x_pct ?? 8.0,
  };
}

export function BulkStyleDialog({
  product,
  open,
  onOpenChange,
}: {
  product: Product;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [scope, setScope] = useState<Scope>("all");
  const [tab, setTab] = useState<"hook" | "subs">("hook");
  const [overlay, setOverlay] = useState<TextOverlayStyle>(() =>
    pickInitialOverlayStyle(product),
  );
  const [subs, setSubs] = useState<SubtitleStyle>(() =>
    pickInitialSubtitleStyle(product),
  );
  const bulk = useBulkApplyPresetStyle(product.id);

  const affectedCount = useMemo(() => countByScope(product, scope), [product, scope]);

  async function apply(): Promise<void> {
    if (affectedCount === 0) {
      toast.error("Ningún preset coincide con el scope elegido.");
      return;
    }
    // Construimos el patch sólo del tab activo — evita pisar el otro.
    // 'position' se filtra server-side igualmente; aquí no lo enviamos.
    const payload: {
      text_overlay_style?: Record<string, unknown>;
      subtitle_style?: Record<string, unknown>;
      scope: Scope;
    } = { scope };
    if (tab === "hook") {
      const { position: _pos, ...rest } = overlay;
      payload.text_overlay_style = rest;
    } else {
      const { position: _pos, enabled: _en, ...rest } = subs;
      payload.subtitle_style = rest;
    }
    try {
      const r = await bulk.mutateAsync(payload);
      toast.success(
        `${r.updated_count} preset(s) actualizados${r.skipped_count > 0 ? ` · ${r.skipped_count} omitidos` : ""}.`,
      );
      onOpenChange(false);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Error al aplicar estilo masivo.",
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-2rem)] max-h-[92vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Paintbrush className="h-5 w-5 text-emerald-500" />
            Estilo visual masivo
          </DialogTitle>
          <DialogDescription>
            Aplica colores, fuentes y animaciones a TODOS los presets en
            1 click. La <strong>posición no se toca</strong> — cada preset
            mantiene la suya. Previsualiza en 9:16 con zonas seguras antes
            de aplicar.
          </DialogDescription>
        </DialogHeader>

        {/* Scope selector */}
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-2 text-xs">
          <span className="font-medium">Aplicar a:</span>
          <Select value={scope} onValueChange={(v) => setScope(v as Scope)}>
            <SelectTrigger className="h-8 w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCOPES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span
            className={cn(
              "rounded px-2 py-0.5 text-[11px] font-semibold",
              affectedCount > 0
                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                : "bg-amber-500/15 text-amber-700 dark:text-amber-300",
            )}
          >
            {affectedCount} preset{affectedCount === 1 ? "" : "s"} afectado{affectedCount === 1 ? "" : "s"}
          </span>
        </div>

        <Tabs value={tab} onValueChange={(v) => setTab(v as "hook" | "subs")}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="hook" className="gap-1.5">
              <Paintbrush className="h-3.5 w-3.5" />
              Hook (overlay)
            </TabsTrigger>
            <TabsTrigger value="subs" className="gap-1.5">
              <Subtitles className="h-3.5 w-3.5" />
              Subtítulos
            </TabsTrigger>
          </TabsList>

          <TabsContent value="hook" className="mt-3">
            <div className="grid gap-4 md:grid-cols-2">
              <HookForm value={overlay} onChange={setOverlay} />
              <HookPreview
                style={overlay}
                onYChange={(y) => setOverlay({ ...overlay, position_y_pct: y })}
              />
            </div>
          </TabsContent>

          <TabsContent value="subs" className="mt-3">
            <div className="grid gap-4 md:grid-cols-2">
              <SubsForm value={subs} onChange={setSubs} />
              <SubsPreview
                style={subs}
                onYChange={(y) => setSubs({ ...subs, position_y_pct: y })}
              />
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={apply}
            disabled={bulk.isPending || affectedCount === 0}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {bulk.isPending ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Paintbrush className="mr-1 h-4 w-4" />
            )}
            Aplicar a {affectedCount} preset{affectedCount === 1 ? "" : "s"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================
// FORMS
// =============================================================

function HookForm({
  value,
  onChange,
}: {
  value: TextOverlayStyle;
  onChange: (v: TextOverlayStyle) => void;
}) {
  function set<K extends keyof TextOverlayStyle>(
    key: K,
    v: TextOverlayStyle[K],
  ): void {
    onChange({ ...value, [key]: v });
  }
  // Combos rápidos de paleta + fondo. 1 click aplica color, stroke
  // y background a la vez — los más usados para vídeos TikTok.
  const COMBOS = [
    {
      label: "⚪ Blanco/negro",
      color: "#FFFFFF",
      stroke_color: "#000000",
      stroke_width: 6,
      background: "none",
    },
    {
      label: "⬜ Fondo blanco · texto negro",
      color: "#000000",
      stroke_color: "#FFFFFF",
      stroke_width: 0,
      background: "white_bar",
    },
    {
      label: "⬛ Fondo negro · texto blanco",
      color: "#FFFFFF",
      stroke_color: "#000000",
      stroke_width: 0,
      background: "black_bar",
    },
    {
      label: "🟡 Amarillo/negro",
      color: "#FACC15",
      stroke_color: "#000000",
      stroke_width: 8,
      background: "none",
    },
  ];
  return (
    <div className="space-y-3 rounded-md border bg-card p-3 text-xs">
      <p className="font-semibold text-emerald-700 dark:text-emerald-300">
        Estilo del Hook box (texto en pantalla)
      </p>
      <div>
        <Label className="text-[10px]">Combos rápidos</Label>
        <div className="mt-1 flex flex-wrap gap-1">
          {COMBOS.map((c) => (
            <button
              key={c.label}
              type="button"
              onClick={() =>
                onChange({
                  ...value,
                  color: c.color,
                  stroke_color: c.stroke_color,
                  stroke_width: c.stroke_width,
                  background: c.background,
                })
              }
              className="rounded border border-muted px-1.5 py-0.5 text-[10px] hover:bg-muted"
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
      <div>
        <Label className="text-[10px]">Fuente</Label>
        <FontSelector
          value={value.font}
          onChange={(p) => set("font", p)}
          className="mt-1"
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-[10px]">Tamaño (px @1080p)</Label>
          <Input
            type="number"
            min={20}
            max={160}
            value={value.size_px}
            onChange={(e) => set("size_px", parseInt(e.target.value) || 56)}
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Color texto</Label>
          <Input
            type="color"
            value={value.color}
            onChange={(e) => set("color", e.target.value)}
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Color contorno</Label>
          <Input
            type="color"
            value={value.stroke_color}
            onChange={(e) => set("stroke_color", e.target.value)}
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Grosor contorno</Label>
          <Input
            type="number"
            min={0}
            max={20}
            value={value.stroke_width}
            onChange={(e) =>
              set("stroke_width", parseInt(e.target.value) || 0)
            }
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Animación</Label>
          <Select
            value={value.animation}
            onValueChange={(v) => set("animation", v)}
          >
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {OVERLAY_ANIMATIONS.map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-[10px]">Fondo</Label>
          <Select
            value={value.background}
            onValueChange={(v) => set("background", v)}
          >
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {OVERLAY_BACKGROUNDS.map((b) => (
                <SelectItem key={b} value={b}>
                  {b}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="col-span-2">
          <Label className="text-[10px]">Duración en pantalla (s)</Label>
          <Input
            type="number"
            step={0.5}
            min={1}
            max={15}
            value={value.duration_s}
            onChange={(e) =>
              set("duration_s", parseFloat(e.target.value) || 4)
            }
            className="h-8"
          />
        </div>
        <div className="col-span-2 rounded border border-cyan-500/30 bg-cyan-500/5 p-2">
          <Label className="text-[10px]">
            Altura exacta Y (% desde arriba): {(value.position_y_pct ?? 12).toFixed(1)}%
          </Label>
          <input
            type="range"
            min={0}
            max={100}
            step={0.5}
            value={value.position_y_pct ?? 12}
            onChange={(e) => set("position_y_pct", parseFloat(e.target.value))}
            className="mt-1 w-full accent-cyan-500"
          />
          <p className="mt-0.5 text-[9px] text-muted-foreground">
            También puedes arrastrar vertical sobre la previsualización.
          </p>
        </div>
        <label className="col-span-2 flex cursor-pointer items-center gap-2 rounded border p-1.5">
          <input
            type="checkbox"
            checked={value.uppercase}
            onChange={(e) => set("uppercase", e.target.checked)}
            className="h-3.5 w-3.5"
          />
          <span>UPPERCASE</span>
        </label>
      </div>
    </div>
  );
}

function SubsForm({
  value,
  onChange,
}: {
  value: SubtitleStyle;
  onChange: (v: SubtitleStyle) => void;
}) {
  function set<K extends keyof SubtitleStyle>(
    key: K,
    v: SubtitleStyle[K],
  ): void {
    onChange({ ...value, [key]: v });
  }
  return (
    <div className="space-y-3 rounded-md border bg-card p-3 text-xs">
      <p className="font-semibold text-violet-700 dark:text-violet-300">
        Estilo de los subtítulos karaoke
      </p>
      <div>
        <Label className="text-[10px]">Fuente</Label>
        <FontSelector
          value={value.font}
          onChange={(p) => set("font", p)}
          className="mt-1"
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-[10px]">Tamaño (px @1080p)</Label>
          <Input
            type="number"
            min={20}
            max={120}
            value={value.size_px}
            onChange={(e) => set("size_px", parseInt(e.target.value) || 42)}
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Margen lateral (%)</Label>
          <Input
            type="number"
            min={0}
            max={30}
            step={0.5}
            value={value.margin_x_pct}
            onChange={(e) =>
              set("margin_x_pct", parseFloat(e.target.value) || 8)
            }
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Color texto</Label>
          <Input
            type="color"
            value={value.color}
            onChange={(e) => set("color", e.target.value)}
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Color contorno</Label>
          <Input
            type="color"
            value={value.stroke_color}
            onChange={(e) => set("stroke_color", e.target.value)}
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Grosor contorno</Label>
          <Input
            type="number"
            min={0}
            max={20}
            value={value.stroke_width}
            onChange={(e) =>
              set("stroke_width", parseInt(e.target.value) || 0)
            }
            className="h-8"
          />
        </div>
        <div className="col-span-2">
          <Label className="text-[10px]">Modo karaoke</Label>
          <Select
            value={value.highlight_mode ?? "pill"}
            onValueChange={(v) => set("highlight_mode", v)}
          >
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SUBS_HIGHLIGHT_MODES.map((m) => (
                <SelectItem key={m.value} value={m.value}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className={cn(value.highlight_mode === "none" && "opacity-40")}>
          <Label className="text-[10px]">Color palabra activa</Label>
          <Input
            type="color"
            value={value.highlight_color}
            onChange={(e) => set("highlight_color", e.target.value)}
            className="h-8"
            disabled={value.highlight_mode === "none"}
          />
        </div>
        <div>
          <Label className="text-[10px]">Palabras por línea</Label>
          <Input
            type="number"
            min={1}
            max={6}
            value={value.max_words_per_line}
            onChange={(e) =>
              set("max_words_per_line", parseInt(e.target.value) || 3)
            }
            className="h-8"
          />
        </div>
        <div>
          <Label className="text-[10px]">Animación</Label>
          <Select
            value={value.animation}
            onValueChange={(v) => set("animation", v)}
          >
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SUBS_ANIMATIONS.map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="col-span-2 rounded border border-cyan-500/30 bg-cyan-500/5 p-2">
          <Label className="text-[10px]">
            Altura exacta Y (% desde arriba): {(value.position_y_pct ?? 75).toFixed(1)}%
          </Label>
          <input
            type="range"
            min={0}
            max={100}
            step={0.5}
            value={value.position_y_pct ?? 75}
            onChange={(e) => set("position_y_pct", parseFloat(e.target.value))}
            className="mt-1 w-full accent-cyan-500"
          />
          <p className="mt-0.5 text-[9px] text-muted-foreground">
            También puedes arrastrar vertical sobre la previsualización.
          </p>
        </div>
        <label className="col-span-2 flex cursor-pointer items-center gap-2 rounded border p-1.5">
          <input
            type="checkbox"
            checked={value.uppercase}
            onChange={(e) => set("uppercase", e.target.checked)}
            className="h-3.5 w-3.5"
          />
          <span>UPPERCASE</span>
        </label>
      </div>
      <p className="text-[10px] text-muted-foreground">
        El slot nombrado (top/bottom/middle) NO se toca — sólo la Y exacta
        sí se aplica masivamente. `enabled` se respeta — los presets sin
        subs siguen sin subs.
      </p>
    </div>
  );
}

// =============================================================
// PREVIEWS 9:16 (hook + subs)
// =============================================================

function PhoneFrame({
  showSafeZones,
  onToggleSafeZones,
  onYChange,
  children,
}: {
  showSafeZones: boolean;
  onToggleSafeZones: () => void;
  onYChange?: (y: number) => void;
  children: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef(false);
  function updateY(clientY: number): void {
    if (!onYChange || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const ratio = (clientY - rect.top) / rect.height;
    const clamped = Math.max(0, Math.min(1, ratio));
    onYChange(Math.round(clamped * 1000) / 10); // % con 1 decimal
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Previsualización 9:16
        </p>
        <Button
          size="sm"
          variant="ghost"
          onClick={onToggleSafeZones}
          className="h-6 gap-1 text-[10px]"
        >
          {showSafeZones ? (
            <Eye className="h-3 w-3" />
          ) : (
            <EyeOff className="h-3 w-3" />
          )}
          Zonas seguras
        </Button>
      </div>
      <div
        ref={containerRef}
        onPointerDown={(e) => {
          if (!onYChange) return;
          dragRef.current = true;
          (e.target as Element).setPointerCapture(e.pointerId);
          updateY(e.clientY);
        }}
        onPointerMove={(e) => {
          if (!dragRef.current) return;
          updateY(e.clientY);
        }}
        onPointerUp={(e) => {
          dragRef.current = false;
          try {
            (e.target as Element).releasePointerCapture(e.pointerId);
          } catch {
            /* noop */
          }
        }}
        className={cn(
          "relative mx-auto overflow-hidden rounded-lg border bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950",
          onYChange && "cursor-ns-resize touch-none select-none",
        )}
        style={{ aspectRatio: "9 / 16", maxWidth: "260px", containerType: "size" }}
      >
        <div
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, rgba(255,255,255,0.06), transparent 50%), radial-gradient(circle at 70% 80%, rgba(34,211,238,0.08), transparent 50%)",
          }}
        />
        {showSafeZones && <SafeZonesOverlay />}
        {children}
      </div>
      <p className="text-center text-[9px] text-muted-foreground">
        {onYChange ? "Arrastra vertical para mover · " : ""}
        Render aproximado · proporciones reales del vídeo final
      </p>
    </div>
  );
}

function SafeZonesOverlay() {
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[12%] border-b border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute left-1 top-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI top
        </span>
      </div>
      <div className="pointer-events-none absolute bottom-[18%] right-0 top-[15%] w-[12%] border-l border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute right-1 top-1 rotate-90 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI lat.
        </span>
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[18%] border-t border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute bottom-1 left-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI bottom
        </span>
      </div>
    </>
  );
}

function buildStroke(color: string, widthPx: number): string {
  if (widthPx <= 0) return "none";
  const em = widthPx / 80;
  const dirs: [number, number][] = [
    [-1, -1], [0, -1], [1, -1],
    [-1, 0], [1, 0],
    [-1, 1], [0, 1], [1, 1],
  ];
  return dirs
    .map(
      ([dx, dy]) =>
        `${(dx * em).toFixed(3)}em ${(dy * em).toFixed(3)}em 0 ${color}`,
    )
    .join(", ");
}

function HookPreview({
  style,
  onYChange,
}: {
  style: TextOverlayStyle;
  onYChange?: (y: number) => void;
}) {
  const [showSafe, setShowSafe] = useState(true);
  const selectedFont = useFontByPath(style.font);
  const fontFamily = useFontFamily(selectedFont);
  const fontSizeCqi = (style.size_px / 1920) * 100 * (16 / 9);
  const text = style.uppercase ? "TU GANCHO AQUÍ" : "Tu gancho aquí";
  const yPct = style.position_y_pct ?? 12;
  const bgClass: Record<string, React.CSSProperties> = {
    none: {},
    black_bar: { backgroundColor: "rgba(0,0,0,0.8)", padding: "0.3em 0.5em" },
    white_bar: { backgroundColor: "rgba(255,255,255,0.95)", padding: "0.3em 0.5em" },
    blur: { backdropFilter: "blur(8px)", padding: "0.3em 0.5em" },
  };
  return (
    <PhoneFrame
      showSafeZones={showSafe}
      onToggleSafeZones={() => setShowSafe((v) => !v)}
      onYChange={onYChange}
    >
      {/* Línea Y indicator */}
      <div
        className="pointer-events-none absolute inset-x-0 h-px bg-cyan-400/60"
        style={{ top: `${yPct}%` }}
      />
      <span
        className="pointer-events-none absolute left-1 z-10 rounded bg-cyan-500/80 px-1 text-[8px] font-medium text-black"
        style={{ top: `calc(${yPct}% - 7px)` }}
      >
        Y={yPct.toFixed(1)}%
      </span>
      <div
        className="pointer-events-none absolute flex justify-center"
        style={{
          left: "50%",
          top: `${yPct}%`,
          transform: "translate(-50%, 0)",
          width: "86%",
        }}
      >
        <span
          style={{
            fontSize: `${fontSizeCqi}cqi`,
            color: style.color,
            fontFamily,
            fontWeight: selectedFont?.source === "bundled" ? "normal" : 900,
            fontSynthesis: "none",
            textShadow: buildStroke(style.stroke_color, style.stroke_width),
            textAlign: "center",
            lineHeight: 1.1,
            ...bgClass[style.background],
          }}
        >
          {text}
        </span>
      </div>
    </PhoneFrame>
  );
}

function SubsPreview({
  style,
  onYChange,
}: {
  style: SubtitleStyle;
  onYChange?: (y: number) => void;
}) {
  const [showSafe, setShowSafe] = useState(true);
  const selectedFont = useFontByPath(style.font);
  const fontFamily = useFontFamily(selectedFont);
  const fontSizeCqi = (style.size_px / 1920) * 100 * (16 / 9);
  const words = ["compra", "ahora", "y", "ahorra", "10€"];
  const visible = words.slice(0, Math.min(style.max_words_per_line, words.length));
  const activeIdx = Math.min(2, visible.length - 1);
  const marginXPct = style.margin_x_pct ?? 8;
  const maxWidthPct = 100 - marginXPct * 2;
  const yPct = style.position_y_pct ?? 75;
  const mode = style.highlight_mode ?? "pill";

  function highlightStyle(active: boolean): React.CSSProperties {
    if (!active || mode === "none") {
      return { color: style.color, padding: "0 0.05em" };
    }
    const base: React.CSSProperties = { color: style.color, padding: "0 0.05em" };
    switch (mode) {
      case "pill":
        return {
          ...base,
          backgroundColor: style.highlight_color,
          padding: "0.1em 0.25em",
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
      default:
        return base;
    }
  }

  return (
    <PhoneFrame
      showSafeZones={showSafe}
      onToggleSafeZones={() => setShowSafe((v) => !v)}
      onYChange={onYChange}
    >
      <div
        className="pointer-events-none absolute inset-x-0 h-px bg-cyan-400/60"
        style={{ top: `${yPct}%` }}
      />
      <span
        className="pointer-events-none absolute left-1 z-10 rounded bg-cyan-500/80 px-1 text-[8px] font-medium text-black"
        style={{ top: `calc(${yPct}% - 7px)` }}
      >
        Y={yPct.toFixed(1)}%
      </span>
      <div
        className="pointer-events-none absolute flex flex-wrap items-center justify-center gap-[0.2em] text-center"
        style={{
          left: "50%",
          top: `${yPct}%`,
          transform: "translate(-50%, -50%)",
          width: `${maxWidthPct}%`,
          fontSize: `${fontSizeCqi}cqi`,
          fontFamily,
          fontWeight: selectedFont?.source === "bundled" ? "normal" : 900,
          fontSynthesis: "none",
          color: style.color,
          textShadow: buildStroke(style.stroke_color, style.stroke_width),
          lineHeight: 1.05,
        }}
      >
        {visible.map((w, i) => {
          const renderW = style.uppercase ? w.toUpperCase() : w;
          return (
            <span key={i} style={highlightStyle(i === activeIdx)}>
              {renderW}
            </span>
          );
        })}
      </div>
    </PhoneFrame>
  );
}
