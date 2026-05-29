"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Copy,
  Loader2,
  MessageSquareText,
  RefreshCw,
  Sparkles,
  Star,
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
  useAddFavoriteHook,
  useDeleteFavoriteHook,
  useFavoriteHooks,
  useGenerateHookVariants,
  useGenerateThemedHooks,
  type FavoriteHook,
  type HookVariant,
} from "@/lib/queries/hooks";
import { useGeneratePresets } from "@/lib/queries/products";
import type { Product, VideoPreset } from "@/lib/types/product";
import { cn } from "@/lib/utils";

function copyToClipboard(text: string) {
  if (typeof window === "undefined") return;
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success("Copiado"))
    .catch(() => toast.error("No se pudo copiar"));
}

/** Generador completo de hooks. Todo en tarjetas colapsables. */
export function HooksGenerator({ product }: { product: Product }) {
  const favoritesQ = useFavoriteHooks(product.id);
  const favoritesList = favoritesQ.data?.items ?? [];
  const favoritesSet = useMemo(
    () => new Set(favoritesList.map((f) => f.text.trim().toLowerCase())),
    [favoritesList],
  );

  return (
    <div className="space-y-3">
      <RegenerateBanner product={product} favoritesCount={favoritesList.length} />

      <FavoritesSection
        product={product}
        favorites={favoritesList}
      />

      <CollapsibleCard
        title="Crear hooks orientados a tema"
        subtitle="Textarea libre + Gemini genera N hooks nuevos"
        icon={Sparkles}
        accent="purple"
        defaultOpen={false}
      >
        <ThemedHooksGenerator product={product} favoritesSet={favoritesSet} />
      </CollapsibleCard>

      <ExistingHooksSection product={product} favoritesSet={favoritesSet} />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Sección Favoritos (top)
   ───────────────────────────────────────────────────────────────── */
function FavoritesSection({
  product,
  favorites,
}: {
  product: Product;
  favorites: FavoriteHook[];
}) {
  if (favorites.length === 0) return null;
  return (
    <CollapsibleCard
      title="Hooks favoritos"
      subtitle="Protegidos contra regeneración · se usan como inspiración al regenerar presets"
      icon={Star}
      accent="amber"
      badge={String(favorites.length)}
      defaultOpen={true}
    >
      <div className="space-y-1.5 p-3 pt-0 sm:p-4 sm:pt-0">
        {favorites.map((f, i) => (
          <div key={i} className="rounded border bg-amber-500/5 p-2">
            {f.notes && (
              <p className="mb-1 text-[10px] italic text-muted-foreground sm:text-[11px]">
                {f.notes}
              </p>
            )}
            <HookRow
              text={f.text}
              meta={f.angle || undefined}
              productId={product.id}
              isFavorite
            />
          </div>
        ))}
      </div>
    </CollapsibleCard>
  );
}

/* ─────────────────────────────────────────────────────────────────
   CollapsibleCard genérica
   ───────────────────────────────────────────────────────────────── */
function CollapsibleCard({
  title,
  subtitle,
  icon: Icon,
  accent,
  badge,
  children,
  defaultOpen = false,
}: {
  title: string;
  subtitle?: string;
  icon: typeof Sparkles;
  accent: "purple" | "amber" | "emerald" | "pink";
  badge?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const accents = {
    purple: {
      border: "border-purple-500/40",
      icon: "text-purple-500",
      activeBg: "bg-purple-500/5",
    },
    amber: {
      border: "border-amber-500/40",
      icon: "text-amber-500",
      activeBg: "bg-amber-500/5",
    },
    emerald: {
      border: "border-emerald-500/40",
      icon: "text-emerald-500",
      activeBg: "bg-emerald-500/5",
    },
    pink: {
      border: "border-pink-500/40",
      icon: "text-pink-500",
      activeBg: "bg-pink-500/5",
    },
  };
  const a = accents[accent];

  return (
    <Card className={cn(a.border, open && a.activeBg)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 p-3 text-left transition-colors hover:bg-muted/40 sm:p-4"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        )}
        <Icon className={cn("h-4 w-4 flex-shrink-0", a.icon)} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <h3 className="text-xs font-semibold sm:text-sm">{title}</h3>
            {badge && (
              <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] uppercase text-muted-foreground sm:text-[10px]">
                {badge}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="truncate text-[10px] text-muted-foreground sm:text-[11px]">
              {subtitle}
            </p>
          )}
        </div>
      </button>
      {open && <CardContent className="space-y-3 pt-0 sm:p-4 sm:pt-0">{children}</CardContent>}
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Banner para regenerar presets cuando hay research_context nuevo
   ───────────────────────────────────────────────────────────────── */
function RegenerateBanner({
  product,
  favoritesCount,
}: {
  product: Product;
  favoritesCount: number;
}) {
  const rc = product.research_context;
  const generateMut = useGeneratePresets(product.id);

  // Solo mostramos el banner si hay research_context Y hay presets antiguos.
  if (!rc || !rc.analyzed_at || (product.video_presets ?? []).length === 0) {
    return null;
  }

  // Detectar si los presets son anteriores al último research
  // (comparamos analyzed_at del research con created_at del último preset).
  const researchTime = new Date(rc.analyzed_at).getTime();
  const presetTimes = (product.video_presets ?? [])
    .map((p) => (p.created_at ? new Date(p.created_at).getTime() : 0))
    .filter((t) => t > 0);
  const newestPreset = presetTimes.length > 0 ? Math.max(...presetTimes) : 0;
  const presetsStale = researchTime > newestPreset;

  if (!presetsStale) return null;

  function onRegenerate() {
    if (
      !window.confirm(
        "Esto regenerará TODOS los presets usando la investigación más reciente. Los presets actuales serán reemplazados. ¿Continuar?",
      )
    ) {
      return;
    }
    generateMut.mutate(
      { kind: "both", n_music: 8, n_scripted: 12, replace_existing: true },
      {
        onSuccess: () => toast.success("Presets regenerados con investigación nueva"),
        onError: (e) => toast.error(`Error: ${e.message}`),
      },
    );
  }

  return (
    <Card className="border-amber-500/40 bg-amber-500/5">
      <CardContent className="flex flex-wrap items-center gap-3 p-3 sm:p-4">
        <AlertTriangle className="h-4 w-4 flex-shrink-0 text-amber-500" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold sm:text-sm">
            Tienes investigación nueva sin aplicar a tus presets
          </p>
          <p className="text-[10px] text-muted-foreground sm:text-xs">
            Los hooks actuales son anteriores al último análisis. Regenera
            para que usen dolores reales + patrones virales detectados.
            {favoritesCount > 0 && (
              <span className="ml-1 font-medium text-amber-700 dark:text-amber-300">
                ⭐ Tus {favoritesCount} favoritos NO se borrarán.
              </span>
            )}
          </p>
        </div>
        <Button
          size="sm"
          onClick={onRegenerate}
          disabled={generateMut.isPending}
          className="h-8 gap-1 bg-amber-600 text-xs hover:bg-amber-700"
        >
          {generateMut.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Regenerando…
            </>
          ) : (
            <>
              <RefreshCw className="h-3.5 w-3.5" />
              Regenerar hooks
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Temáticos (colapsable)
   ───────────────────────────────────────────────────────────────── */
function ThemedHooksGenerator({
  product,
  favoritesSet,
}: {
  product: Product;
  favoritesSet: Set<string>;
}) {
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
    <div className="space-y-3 p-3 pt-0 sm:p-4 sm:pt-0">
      <p className="text-[11px] text-muted-foreground sm:text-xs">
        Escribe el tema/contexto y Gemini genera N hooks nuevos del producto
        orientados a eso.
      </p>
      <Textarea
        value={theme}
        onChange={(e) => setTheme(e.target.value)}
        placeholder="ej. orientados a verano y vacaciones · para regalar a la pareja · dramáticos · para edad >40"
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
                isFavorite={favoritesSet.has(h.text.trim().toLowerCase())}
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
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Existentes — agrupados por kind+angle, todos colapsados
   ───────────────────────────────────────────────────────────────── */
function ExistingHooksSection({
  product,
  favoritesSet,
}: {
  product: Product;
  favoritesSet: Set<string>;
}) {
  const presets: VideoPreset[] = product.video_presets ?? [];
  const [openKey, setOpenKey] = useState<string | null>(null);

  const groups = useMemo(() => {
    const byKey = new Map<string, VideoPreset[]>();
    for (const p of presets) {
      const key = `${p.kind ?? "scripted"}__${p.angle ?? "general"}`;
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key)!.push(p);
    }
    return Array.from(byKey.entries()).map(([key, arr]) => {
      const [kind, angle] = key.split("__");
      return { key, kind, angle, presets: arr };
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

  const activeGroup = groups.find((g) => g.key === openKey);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold sm:text-base">
          <MessageSquareText className="h-4 w-4 text-amber-500" />
          Hooks de tus presets ({presets.length})
        </h2>
        <span className="text-[10px] text-muted-foreground sm:text-xs">
          {groups.length} grupo(s)
        </span>
      </div>

      {/* Grid de tarjetas compactas — 2 cols móvil / 3 sm / 4 lg */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {groups.map((g) => {
          const isOpen = g.key === openKey;
          const isMusic = g.kind === "music";
          const accent = isMusic
            ? "border-pink-500/40 text-pink-500"
            : "border-emerald-500/40 text-emerald-500";
          return (
            <button
              key={g.key}
              type="button"
              onClick={() => setOpenKey(isOpen ? null : g.key)}
              className={cn(
                "flex items-center gap-2 rounded-lg border-2 p-2 text-left transition-colors hover:bg-muted/50 sm:p-3",
                accent,
                isOpen && "bg-muted/50 ring-1 ring-current ring-offset-1",
              )}
            >
              <MessageSquareText className="h-4 w-4 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[10px] font-semibold sm:text-[11px]">
                  {g.kind} · {g.angle}
                </p>
                <p className="text-[9px] text-muted-foreground sm:text-[10px]">
                  {countMainHooks(g.presets)} hook
                  {countMainHooks(g.presets) === 1 ? "" : "s"}
                </p>
              </div>
              {isOpen ? (
                <ChevronDown className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
              )}
            </button>
          );
        })}
      </div>

      {/* Panel expandido full-width — solo del grupo activo */}
      {activeGroup && (
        <Card
          className={
            activeGroup.kind === "music"
              ? "border-pink-500/40"
              : "border-emerald-500/40"
          }
        >
          <CardContent className="space-y-1.5 p-3 sm:p-4">
            <p className="text-xs font-semibold sm:text-sm">
              {activeGroup.kind} · {activeGroup.angle}
              <span className="ml-1.5 font-normal text-muted-foreground">
                ({activeGroup.presets.length} preset
                {activeGroup.presets.length === 1 ? "" : "s"})
              </span>
            </p>
            {activeGroup.presets.map((p) => (
              <PresetHooksBlock
                key={p.id}
                preset={p}
                productId={product.id}
                favoritesSet={favoritesSet}
              />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function countMainHooks(presets: VideoPreset[]): number {
  return presets.reduce((acc, p) => {
    // SOLO contamos el hook principal (text_overlay). hooks_alternatives
    // son variantes pre-generadas que el user no quiere ver — debe pulsar
    // "+variantes" para generarlas on-demand.
    return acc + (p.text_overlay && p.text_overlay.trim() ? 1 : 0);
  }, 0);
}

function PresetHooksBlock({
  preset,
  productId,
  favoritesSet,
}: {
  preset: VideoPreset;
  productId: string;
  favoritesSet: Set<string>;
}) {
  const mainHook = (preset.text_overlay || "").trim();
  if (!mainHook) return null;
  const isFav = favoritesSet.has(mainHook.toLowerCase());

  return (
    <div className="rounded border bg-muted/20 p-2">
      <p className="mb-1 truncate text-[10px] font-semibold text-muted-foreground sm:text-[11px]">
        {preset.name || preset.id?.slice(0, 8)}
      </p>
      <HookRow
        text={mainHook}
        productId={productId}
        isFavorite={isFav}
        sourcePresetId={preset.id}
        sourceAngle={preset.angle}
        sourceKind={preset.kind}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   HookRow genérico con copy + +variantes
   ───────────────────────────────────────────────────────────────── */
function HookRow({
  text,
  meta,
  hint,
  productId,
  isFavorite = false,
  sourcePresetId,
  sourceAngle,
  sourceKind,
}: {
  text: string;
  meta?: string;
  hint?: string;
  productId: string;
  isFavorite?: boolean;
  sourcePresetId?: string;
  sourceAngle?: string;
  sourceKind?: string;
}) {
  const [showVariants, setShowVariants] = useState(false);
  const variantsMut = useGenerateHookVariants();
  const addFav = useAddFavoriteHook();
  const delFav = useDeleteFavoriteHook();
  const [n] = useState(5);

  function onCopy() {
    copyToClipboard(text);
  }
  function onGenerate() {
    variantsMut.mutate({ productId, hook: text, n });
    setShowVariants(true);
  }
  function onToggleFavorite() {
    if (isFavorite) {
      delFav.mutate(
        { productId, text },
        { onSuccess: () => toast.success("Quitado de favoritos") },
      );
    } else {
      addFav.mutate(
        {
          productId,
          text,
          angle: sourceAngle || meta || "",
          kind: sourceKind || "",
          source_preset_id: sourcePresetId,
        },
        { onSuccess: () => toast.success("Guardado en favoritos ⭐") },
      );
    }
  }

  return (
    <div
      className={cn(
        "rounded border p-2 text-[11px] sm:text-xs",
        isFavorite
          ? "border-amber-500/40 bg-amber-500/5"
          : "border-muted bg-card",
      )}
    >
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
            onClick={onToggleFavorite}
            disabled={addFav.isPending || delFav.isPending}
            title={isFavorite ? "Quitar de favoritos" : "Marcar como favorito"}
            className={cn(
              "h-7 w-7 p-0",
              isFavorite
                ? "text-amber-500 hover:text-amber-600"
                : "text-muted-foreground hover:text-amber-500",
            )}
          >
            <Star
              className={cn("h-3.5 w-3.5", isFavorite && "fill-current")}
            />
          </Button>
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
                onClick={() =>
                  addFav.mutate(
                    {
                      productId,
                      text: v.text,
                      angle: variantsMut.data?.angle_detected || "",
                    },
                    { onSuccess: () => toast.success("Guardado en favoritos ⭐") },
                  )
                }
                title="Marcar como favorito"
                className="h-6 w-6 p-0 text-muted-foreground hover:text-amber-500"
              >
                <Star className="h-3 w-3" />
              </Button>
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
