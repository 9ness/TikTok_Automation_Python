"use client";

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
import { useArrowStickers } from "@/lib/queries/editor-auto";
import type { CtaArrowOverlay, HookBoxOverlay, OverlaysConfig } from "@/lib/types/generation";

export const DEFAULT_OVERLAYS: OverlaysConfig = {
  hook_box: {
    enabled: false,
    text: "",
    animation: "swipe_left",
    duration: 5.0,
    y_position_pct: 0.40,
    text_color: "#0B0B0B",
    box_color: "#FFFFFF",
    shadow_color: "#1E01C4",
    font_scale: 0.018,
  },
  cta_arrow: {
    enabled: false,
    sticker_file: "",
    position_x_pct: 50,
    position_y_pct: 78,
    scale_width_pct: 25,
    rotation_deg: 0,
    flip_horizontal: false,
    flip_vertical: false,
    duration_seconds: 3.5,
    fallback_last_seconds: 4.0,
  },
};

interface Props {
  value: OverlaysConfig;
  onChange: (v: OverlaysConfig) => void;
}

export function OverlaysPanel({ value, onChange }: Props) {
  const stickers = useArrowStickers();
  const arrowFiles = stickers.data?.files ?? [];

  function patchHook(patch: Partial<HookBoxOverlay>) {
    onChange({ ...value, hook_box: { ...value.hook_box, ...patch } });
  }
  function patchCta(patch: Partial<CtaArrowOverlay>) {
    onChange({ ...value, cta_arrow: { ...value.cta_arrow, ...patch } });
  }

  return (
    <div className="space-y-4">
      {/* Hook box */}
      <div className="space-y-2 rounded-md border p-3">
        <label className="flex cursor-pointer items-start justify-between gap-2">
          <div>
            <p className="text-sm font-medium">🎣 Hook box (texto al inicio)</p>
            <p className="text-xs text-muted-foreground">
              Caja con titular tipo "noticia" sobreimpresa los primeros segundos.
              Si dejas el texto vacío usa el hook que genere la IA.
            </p>
          </div>
          <Switch
            checked={value.hook_box.enabled}
            onCheckedChange={(v) => patchHook({ enabled: v })}
          />
        </label>

        {value.hook_box.enabled && (
          <div className="space-y-3 border-t pt-3">
            <div className="space-y-1">
              <Label className="text-xs">Texto del hook (vacío = auto-generado)</Label>
              <Input
                value={value.hook_box.text ?? ""}
                onChange={(e) => patchHook({ text: e.target.value })}
                placeholder="POV: nunca volverás a comprar esto…"
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">Animación</Label>
                <Select
                  value={value.hook_box.animation ?? "swipe_left"}
                  onValueChange={(v) => patchHook({ animation: v })}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="swipe_left">Swipe izquierda</SelectItem>
                    <SelectItem value="news_flash">News flash</SelectItem>
                    <SelectItem value="slide_in_out">Slide in/out</SelectItem>
                    <SelectItem value="fade">Fade</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Duración (s): {(value.hook_box.duration ?? 5).toFixed(1)}</Label>
                <input
                  type="range"
                  min="2"
                  max="10"
                  step="0.5"
                  value={value.hook_box.duration ?? 5}
                  onChange={(e) => patchHook({ duration: Number(e.target.value) })}
                  className="w-full"
                />
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              <ColorField
                label="Texto"
                value={value.hook_box.text_color ?? "#0B0B0B"}
                onChange={(v) => patchHook({ text_color: v })}
              />
              <ColorField
                label="Fondo"
                value={value.hook_box.box_color ?? "#FFFFFF"}
                onChange={(v) => patchHook({ box_color: v })}
              />
              <ColorField
                label="Sombra"
                value={value.hook_box.shadow_color ?? "#1E01C4"}
                onChange={(v) => patchHook({ shadow_color: v })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">
                Posición Y: {Math.round((value.hook_box.y_position_pct ?? 0.4) * 100)}%
              </Label>
              <input
                type="range"
                min="0.15"
                max="0.80"
                step="0.01"
                value={value.hook_box.y_position_pct ?? 0.4}
                onChange={(e) => patchHook({ y_position_pct: Number(e.target.value) })}
                className="w-full"
              />
            </div>
          </div>
        )}
      </div>

      {/* CTA flecha */}
      <div className="space-y-2 rounded-md border p-3">
        <label className="flex cursor-pointer items-start justify-between gap-2">
          <div>
            <p className="text-sm font-medium">➡️ CTA flecha (al final)</p>
            <p className="text-xs text-muted-foreground">
              Sticker animado de flecha apuntando al carrito/perfil. Aparece en
              los últimos segundos del vídeo.
            </p>
          </div>
          <Switch
            checked={value.cta_arrow.enabled}
            onCheckedChange={(v) => patchCta({ enabled: v })}
          />
        </label>

        {value.cta_arrow.enabled && (
          <div className="space-y-3 border-t pt-3">
            <div className="space-y-1">
              <Label className="text-xs">Sticker</Label>
              <Select
                value={value.cta_arrow.sticker_file ?? ""}
                onValueChange={(v) => patchCta({ sticker_file: v })}
              >
                <SelectTrigger className="h-9">
                  <SelectValue
                    placeholder={
                      stickers.isLoading
                        ? "Cargando…"
                        : arrowFiles.length === 0
                          ? "Sin stickers en Assets/flechas/"
                          : "Elige sticker"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {arrowFiles.map((f) => (
                    <SelectItem key={f.filename} value={f.filename}>
                      {f.filename}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">
                  Posición X: {Math.round(value.cta_arrow.position_x_pct ?? 50)}%
                </Label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={value.cta_arrow.position_x_pct ?? 50}
                  onChange={(e) => patchCta({ position_x_pct: Number(e.target.value) })}
                  className="w-full"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">
                  Posición Y: {Math.round(value.cta_arrow.position_y_pct ?? 78)}%
                </Label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={value.cta_arrow.position_y_pct ?? 78}
                  onChange={(e) => patchCta({ position_y_pct: Number(e.target.value) })}
                  className="w-full"
                />
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">
                  Tamaño: {Math.round(value.cta_arrow.scale_width_pct ?? 25)}% ancho
                </Label>
                <input
                  type="range"
                  min="10"
                  max="80"
                  step="1"
                  value={value.cta_arrow.scale_width_pct ?? 25}
                  onChange={(e) => patchCta({ scale_width_pct: Number(e.target.value) })}
                  className="w-full"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">
                  Duración: {(value.cta_arrow.duration_seconds ?? 3.5).toFixed(1)}s
                </Label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  step="0.5"
                  value={value.cta_arrow.duration_seconds ?? 3.5}
                  onChange={(e) => patchCta({ duration_seconds: Number(e.target.value) })}
                  className="w-full"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">
                Aparece a {(value.cta_arrow.fallback_last_seconds ?? 4).toFixed(1)}s del final
              </Label>
              <input
                type="range"
                min="1"
                max="15"
                step="0.5"
                value={value.cta_arrow.fallback_last_seconds ?? 4}
                onChange={(e) =>
                  patchCta({ fallback_last_seconds: Number(e.target.value) })
                }
                className="w-full"
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex cursor-pointer items-center gap-2 text-xs">
                <Switch
                  checked={value.cta_arrow.flip_horizontal ?? false}
                  onCheckedChange={(v) => patchCta({ flip_horizontal: v })}
                />
                Flip horizontal
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-xs">
                <Switch
                  checked={value.cta_arrow.flip_vertical ?? false}
                  onCheckedChange={(v) => patchCta({ flip_vertical: v })}
                />
                Flip vertical
              </label>
            </div>
          </div>
        )}
      </div>
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
      <Label className="text-xs">{label}</Label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-12 rounded border bg-transparent"
        />
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 font-mono text-xs"
        />
      </div>
    </div>
  );
}
