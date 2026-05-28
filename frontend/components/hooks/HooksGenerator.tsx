"use client";

import { useMemo, useState } from "react";
import {
  ChevronRight,
  Copy,
  Loader2,
  MessageSquareText,
  Sparkles,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useGenerateHookVariants,
  useGenerateThemedHooks,
  type HookVariant,
} from "@/lib/queries/hooks";
import type { Product, VideoPreset } from "@/lib/types/product";
import { cn } from "@/lib/utils";

function copyToClipboard(text: string) {
  if (typeof window === "undefined") return;
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success("Copiado"))
    .catch(() => toast.error("No se pudo copiar"));
}

/** Generador completo de hooks: temáticos + existentes con variantes.
 *  Requiere que el caller le pase el `product` ya cargado. */
export function HooksGenerator({ product }: { product: Product }) {
  return (
    <div className="space-y-3">
      <ThemedHooksGenerator product={product} />
      <ExistingHooksSection product={product} />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
   Temáticos
   ─────────────────────────────────────────────────────────────── */
function ThemedHooksGenerator({ product }: { product: Product }) {
  const [theme, setTheme] = useState("");
  const [n, setN] = useState<number>(10);
  const mutation = useGenerateThemedHooks();

  function onGenerate() {
    if (!theme.trim()) {
      toast.error("Escribe un tema o contexto");
      return;
    }
    mutation.mutate({ productId: product.id, theme: theme.trim(), n });
  }

  return (
    <Card className="border-purple-500/40">
      <CardContent className="space-y-3 p-3 sm:p-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-purple-500" />
          <h2 className="text-sm font-semibold sm:text-base">
            Crear hooks orientados a un tema
          </h2>
        </div>
        <p className="text-[11px] text-muted-foreground sm:text-xs">
          Escribe el tema/contexto y Gemini genera N hooks nuevos del producto
          orientados a eso. Usa research_context si está disponible para
          afinar.
        </p>
        <Textarea
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          placeholder="ej. orientados a verano y vacaciones · para regalar a la pareja · dramáticos · para edad >40 · antes de ir al gym"
          rows={2}
          maxLength={300}
          className="text-sm"
          disabled={mutation.isPending}
        />
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <Label className="text-[10px] text-muted-foreground sm:text-xs">
              Nº hooks:
            </Label>
            <Select
              value={String(n)}
              onValueChange={(v) => setN(Number(v))}
              disabled={mutation.isPending}
            >
              <SelectTrigger className="h-8 w-20 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[5, 10, 15, 20].map((v) => (
                  <SelectItem key={v} value={String(v)}>
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={onGenerate}
            disabled={mutation.isPending || !theme.trim()}
            className="h-9 gap-1 bg-purple-600 text-xs hover:bg-purple-700 sm:h-8"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Generando…
              </>
            ) : (
              <>
                <Wand2 className="h-3.5 w-3.5" />
                Generar {n}
              </>
            )}
          </Button>
        </div>

        {mutation.data && (
          <div className="space-y-2 pt-2">
            {mutation.data.theme_interpretation && (
              <p className="rounded bg-muted/30 px-2 py-1.5 text-[10px] italic text-muted-foreground sm:text-[11px]">
                Interpretación: {mutation.data.theme_interpretation}
              </p>
            )}
            <div className="space-y-1.5">
              {mutation.data.hooks.map((h, i) => (
                <HookRow
                  key={i}
                  text={h.text}
                  meta={h.angle}
                  hint={h.rationale}
                  productId={product.id}
                />
              ))}
            </div>
          </div>
        )}
        {mutation.error && (
          <p className="text-xs text-red-600 dark:text-red-400">
            Error: {mutation.error.message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/* ───────────────────────────────────────────────────────────────
   Existentes — agrupados por preset
   ─────────────────────────────────────────────────────────────── */
function ExistingHooksSection({ product }: { product: Product }) {
  const presets: VideoPreset[] = product.video_presets ?? [];

  const groups = useMemo(() => {
    const byKey = new Map<string, VideoPreset[]>();
    for (const p of presets) {
      const key = `${p.kind ?? "scripted"}__${p.angle ?? "general"}`;
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key)!.push(p);
    }
    return Array.from(byKey.entries()).map(([key, arr]) => {
      const [kind, angle] = key.split("__");
      return { kind, angle, presets: arr };
    });
  }, [presets]);

  if (presets.length === 0) {
    return (
      <Card className="bg-muted/30">
        <CardContent className="p-4 text-center text-xs text-muted-foreground sm:text-sm">
          Este producto no tiene presets generados. Ve a la pestaña{" "}
          <strong>Presets</strong> del producto para generarlos primero.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold sm:text-base">
          <MessageSquareText className="h-4 w-4 text-amber-500" />
          Hooks de tus presets ({presets.length})
        </h2>
        <span className="text-[10px] text-muted-foreground sm:text-xs">
          {groups.length} grupos
        </span>
      </div>

      {groups.map((g) => (
        <Card key={`${g.kind}-${g.angle}`}>
          <CardContent className="space-y-2 p-3 sm:p-4">
            <div className="flex items-center gap-1.5 text-xs sm:text-sm">
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[9px] font-medium uppercase sm:text-[10px]",
                  g.kind === "music"
                    ? "bg-pink-500/20 text-pink-700 dark:text-pink-300"
                    : "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
                )}
              >
                {g.kind}
              </span>
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-medium uppercase text-amber-700 dark:text-amber-300 sm:text-[10px]">
                {g.angle}
              </span>
              <span className="ml-auto text-[10px] text-muted-foreground sm:text-xs">
                {g.presets.length} preset(s)
              </span>
            </div>

            <div className="space-y-1.5">
              {g.presets.map((p) => (
                <PresetHooksBlock key={p.id} preset={p} productId={product.id} />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function PresetHooksBlock({
  preset,
  productId,
}: {
  preset: VideoPreset;
  productId: string;
}) {
  const hooks: { text: string; label: string }[] = [];
  if (preset.text_overlay && preset.text_overlay.trim()) {
    hooks.push({ text: preset.text_overlay.trim(), label: "principal" });
  }
  for (const h of preset.hooks_alternatives ?? []) {
    if (h && h.trim()) hooks.push({ text: h.trim(), label: "alt" });
  }
  if (preset.title && preset.title.trim()) {
    hooks.push({ text: preset.title.trim(), label: "title" });
  }
  const seen = new Set<string>();
  const dedup = hooks.filter((h) => {
    const key = h.text.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (dedup.length === 0) return null;

  return (
    <div className="rounded border bg-muted/20 p-2">
      <p className="mb-1 truncate text-[10px] font-semibold text-muted-foreground sm:text-[11px]">
        {preset.name || preset.id?.slice(0, 8)}
      </p>
      <div className="space-y-1">
        {dedup.map((h, i) => (
          <HookRow
            key={i}
            text={h.text}
            meta={h.label}
            productId={productId}
          />
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────
   HookRow genérico con copy + +variantes
   ─────────────────────────────────────────────────────────────── */
function HookRow({
  text,
  meta,
  hint,
  productId,
}: {
  text: string;
  meta?: string;
  hint?: string;
  productId: string;
}) {
  const [showVariants, setShowVariants] = useState(false);
  const variantsMut = useGenerateHookVariants();
  const [n] = useState(5);

  function onCopy() {
    copyToClipboard(text);
  }
  function onGenerate() {
    variantsMut.mutate({ productId, hook: text, n });
    setShowVariants(true);
  }

  return (
    <div className="rounded border border-muted bg-card p-2 text-[11px] sm:text-xs">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="break-words font-medium text-foreground">{text}</p>
          {(meta || hint) && (
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {meta && (
                <span className="mr-1 inline-block rounded bg-muted px-1 py-0.5 uppercase">
                  {meta}
                </span>
              )}
              {hint}
            </p>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={onCopy}
            className="h-7 gap-1 px-2 text-[10px]"
          >
            <Copy className="h-3 w-3" />
            Copiar
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onGenerate}
            disabled={variantsMut.isPending}
            className="h-7 gap-1 px-2 text-[10px] text-purple-600 hover:text-purple-700 dark:text-purple-400"
          >
            {variantsMut.isPending && showVariants ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Wand2 className="h-3 w-3" />
            )}
            +{n} variantes
          </Button>
        </div>
      </div>

      {showVariants && variantsMut.data && (
        <div className="mt-2 space-y-1 border-t pt-2">
          <p className="text-[10px] text-muted-foreground">
            Ángulo detectado:{" "}
            <strong>{variantsMut.data.angle_detected}</strong>
          </p>
          {variantsMut.data.variants.map((v: HookVariant, i: number) => (
            <div
              key={i}
              className="flex items-start gap-1.5 rounded bg-muted/30 px-2 py-1"
            >
              <ChevronRight className="mt-0.5 h-3 w-3 flex-shrink-0 text-purple-500" />
              <div className="min-w-0 flex-1">
                <p className="break-words text-[11px] sm:text-xs">{v.text}</p>
                {v.rationale && (
                  <p className="text-[9px] italic text-muted-foreground sm:text-[10px]">
                    {v.rationale}
                  </p>
                )}
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => copyToClipboard(v.text)}
                className="h-6 gap-1 px-1.5 text-[10px]"
              >
                <Copy className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
      {showVariants && variantsMut.error && (
        <p className="mt-1 text-[10px] text-red-600 dark:text-red-400">
          Error: {variantsMut.error.message}
        </p>
      )}
    </div>
  );
}
