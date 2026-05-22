"use client";

import { useMemo, useState } from "react";
import { Mic, Music, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useProduct } from "@/lib/queries/products";
import type { VideoPreset } from "@/lib/types/product";
import { cn } from "@/lib/utils";

/** Tiers Seedance ordenados de barato → caro. Veo3 va aparte (no es
 *  "más caro" sino otro modelo). Para calcular "exclusivos" del tier
 *  seleccionado, comparamos contra los tiers ESTRICTAMENTE más baratos
 *  dentro de la misma familia. */
const CHEAPER_SEEDANCE: Record<string, string[]> = {
  standard: [],
  advanced: ["standard"],
  pro: ["standard", "advanced"],
  veo3_prompt_only: ["standard", "advanced", "pro"],
};

const STYLE_BADGE: Record<string, { label: string; cls: string }> = {
  voiceover: {
    label: "Voiceover",
    cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  },
  creator_pov: {
    label: "Creator POV",
    cls: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  },
};

/** Lista de VideoPresets del producto, filtrados por tier compatible.
 *
 *  Soporta 2 modos:
 *  - `single` (default): click selecciona y aplica al form.
 *  - `multi`: cada card es un toggle. El form NO se autorrellena (cada
 *    preset se aplicará por separado al encolar el lote desde el caller).
 */
export function VideoPresetsPicker({
  productId,
  tier,
  activePresetId,
  onPick,
  onClear,
  multiMode = false,
  selectedIds,
  onToggleSelect,
  onSelectAll,
}: {
  productId: string;
  /** Tier actualmente seleccionado en el form (filtra presets compatibles). */
  tier: string;
  /** ID del preset activo (single mode — resalta la card). */
  activePresetId: string | null;
  onPick: (preset: VideoPreset) => void;
  onClear: () => void;
  /** Si true → modo multi-select con checkboxes. */
  multiMode?: boolean;
  /** En multi mode: IDs actualmente marcados. */
  selectedIds?: Set<string>;
  /** En multi mode: toggle de 1 preset. */
  onToggleSelect?: (id: string) => void;
  /** En multi mode: marca/desmarca todos los compatibles. */
  onSelectAll?: (ids: string[]) => void;
}) {
  const product = useProduct(productId);
  const presets = product.data?.video_presets ?? [];

  // 2 toggles que el user controla:
  // - "Solo compatibles" (ON por defecto): oculta los presets que no
  //   corren en el tier seleccionado (en vez de mostrarlos apagados).
  // - "Solo exclusivos": muestra solo los presets que requieren ESTE
  //   tier o superior — útil para ver qué creatividades únicas
  //   desbloquea pagar más (p.ej. creator_pov solo en Pro+Veo3).
  const [showOnlyCompatible, setShowOnlyCompatible] = useState(true);
  const [showOnlyExclusive, setShowOnlyExclusive] = useState(false);

  const compatible = useMemo(() => {
    let list = presets;
    if (showOnlyCompatible) {
      list = list.filter((p) => p.compatible_tiers.includes(tier));
    }
    if (showOnlyExclusive) {
      // "Exclusivo del tier X" = compatible con X y NO con ningún tier
      // más barato de su familia. Si el tier no está definido en la
      // tabla, no filtramos (fallback seguro).
      const cheaper = CHEAPER_SEEDANCE[tier] ?? [];
      list = list.filter(
        (p) =>
          p.compatible_tiers.includes(tier) &&
          !cheaper.some((t) => p.compatible_tiers.includes(t)),
      );
    }
    return list;
  }, [presets, tier, showOnlyCompatible, showOnlyExclusive]);

  const incompatibleCount = useMemo(
    () => presets.filter((p) => !p.compatible_tiers.includes(tier)).length,
    [presets, tier],
  );

  const musicCount = compatible.filter((p) => p.kind === "music").length;
  const scriptedCount = compatible.filter((p) => p.kind === "scripted").length;

  if (product.isLoading) {
    return (
      <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        Cargando presets…
      </div>
    );
  }

  if (presets.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-3 text-xs">
        Este producto aún no tiene presets. Ve a la página del producto → tab{" "}
        <strong>Presets</strong> → <strong>Generar todos</strong>.
      </div>
    );
  }

  const selCount = selectedIds?.size ?? 0;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-emerald-500" />
          <strong>Presets del producto</strong>
          <span className="text-muted-foreground">
            {compatible.length}
            {compatible.length !== presets.length && (
              <span className="opacity-70"> / {presets.length}</span>
            )}{" "}
            {musicCount > 0 && `· 🎵 ${musicCount}`}
            {scriptedCount > 0 && ` · 🎤 ${scriptedCount}`}
            {!showOnlyCompatible && incompatibleCount > 0 && (
              <span
                className="ml-1 text-amber-600 dark:text-amber-400"
                title={`${incompatibleCount} no compatibles con el tier seleccionado — aparecen apagados`}
              >
                · {incompatibleCount} ⚠️
              </span>
            )}
          </span>
          {multiMode && selCount > 0 && (
            <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-700 dark:text-sky-300">
              {selCount} marcados
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {multiMode && onSelectAll && (
            <>
              <button
                type="button"
                onClick={() => onSelectAll(compatible.map((p) => p.id))}
                className="rounded border border-muted px-1.5 py-0.5 text-[10px] hover:bg-muted"
              >
                Todos
              </button>
              {selCount > 0 && (
                <button
                  type="button"
                  onClick={() => onSelectAll([])}
                  className="rounded border border-muted px-1.5 py-0.5 text-[10px] hover:bg-muted"
                >
                  Ninguno
                </button>
              )}
            </>
          )}
          {!multiMode && activePresetId && (
            <button
              type="button"
              onClick={onClear}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              ✕ Limpiar
            </button>
          )}
        </div>
      </div>

      {/* Toggles de filtrado: compatibles + exclusivos */}
      <div className="flex flex-wrap items-center gap-3 text-[11px]">
        <label className="flex cursor-pointer items-center gap-1.5">
          <input
            type="checkbox"
            checked={showOnlyCompatible}
            onChange={(e) => setShowOnlyCompatible(e.target.checked)}
            className="h-3.5 w-3.5 accent-emerald-500"
          />
          <span title="Oculta los presets que no funcionan en el tier elegido (en vez de mostrarlos apagados).">
            Solo compatibles con el tier
          </span>
        </label>
        <label className="flex cursor-pointer items-center gap-1.5">
          <input
            type="checkbox"
            checked={showOnlyExclusive}
            onChange={(e) => setShowOnlyExclusive(e.target.checked)}
            className="h-3.5 w-3.5 accent-violet-500"
          />
          <span title="Muestra solo presets que NO funcionan en tiers más baratos — los que justifican pagar este tier (ej. creator_pov solo en Pro/Veo3).">
            Solo exclusivos de este tier
          </span>
        </label>
      </div>

      {/* Mensaje cuando los filtros dejan 0 presets */}
      {compatible.length === 0 && (
        <div className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-3 text-xs">
          {showOnlyExclusive ? (
            <>
              No hay presets <strong>exclusivos</strong> del tier{" "}
              <strong>{tier}</strong>. Todos los presets de este producto
              también funcionan en tiers más baratos. Desmarca
              &ldquo;Solo exclusivos&rdquo; para ver el resto.
            </>
          ) : showOnlyCompatible ? (
            <>
              Ninguno de los {presets.length} presets es compatible con el
              tier <strong>{tier}</strong>. Cambia de tier o desmarca
              &ldquo;Solo compatibles&rdquo;.
            </>
          ) : (
            <>Este producto no tiene presets.</>
          )}
        </div>
      )}

      {/* Grid scroll horizontal en mobile, grid 2 cols sm, 3 cols md */}
      <div className="-mx-1 flex gap-2 overflow-x-auto pb-1 sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible md:grid-cols-3">
        {compatible.map((p) => {
          const checked = selectedIds?.has(p.id) ?? false;
          const isActive = !multiMode && activePresetId === p.id;
          const incompatible = !p.compatible_tiers.includes(tier);
          return (
            <PresetMiniCard
              key={p.id}
              preset={p}
              active={isActive || checked}
              showCheckbox={multiMode}
              checked={checked}
              disabled={incompatible}
              disabledReason={
                incompatible
                  ? `Este preset no es compatible con el tier seleccionado (${tier}). Cambia de tier para usarlo.`
                  : undefined
              }
              onPick={() => {
                if (incompatible) return;
                if (multiMode) {
                  onToggleSelect?.(p.id);
                } else {
                  onPick(p);
                }
              }}
            />
          );
        })}
      </div>
    </div>
  );
}

function PresetMiniCard({
  preset,
  active,
  onPick,
  showCheckbox,
  checked,
  disabled,
  disabledReason,
}: {
  preset: VideoPreset;
  active: boolean;
  onPick: () => void;
  showCheckbox?: boolean;
  checked?: boolean;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const Icon = preset.kind === "music" ? Music : Mic;
  const accent = preset.kind === "music" ? "sky" : "violet";
  // En presets de música, el `style` ("voiceover" heredado) NO significa
  // que lleve voz — confunde al user. Mostramos "Sin voz" en su lugar.
  // En scripted, sí mostramos voiceover vs creator_pov.
  const isMusic = preset.kind === "music";
  const styleMeta = isMusic ? null : STYLE_BADGE[preset.style];

  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled}
      title={disabledReason}
      className={cn(
        "min-w-[220px] shrink-0 rounded-md border-2 p-2 text-left transition-all sm:min-w-0",
        disabled && "cursor-not-allowed opacity-40 grayscale",
        !disabled && active
          ? `border-${accent}-500 bg-${accent}-500/15`
          : !disabled && `border-${accent}-500/30 bg-${accent}-500/5 hover:border-${accent}-500/60`,
        // Workaround: Tailwind necesita las clases literales — uso style fallback
        !disabled && active && preset.kind === "music" && "border-sky-500 bg-sky-500/15",
        !disabled && active && preset.kind === "scripted" && "border-violet-500 bg-violet-500/15",
        disabled && "border-muted",
      )}
    >
      <div className="flex items-center gap-1.5">
        {showCheckbox && (
          <span
            className={cn(
              "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border-2 text-[10px] font-bold leading-none",
              checked
                ? preset.kind === "music"
                  ? "border-sky-500 bg-sky-500 text-white"
                  : "border-violet-500 bg-violet-500 text-white"
                : "border-muted-foreground/40",
            )}
            aria-hidden
          >
            {checked ? "✓" : ""}
          </span>
        )}
        <Icon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            preset.kind === "music" ? "text-sky-500" : "text-violet-500",
          )}
        />
        <strong className="truncate text-[11px]">{preset.name}</strong>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        {preset.angle && (
          <Badge variant="secondary" className="px-1 py-0 text-[9px]">
            {preset.angle}
          </Badge>
        )}
        {isMusic ? (
          <span
            className="rounded bg-sky-500/15 px-1 py-0 text-[9px] text-sky-700 dark:text-sky-300"
            title="Vídeo mudo + texto en pantalla. Añade trending audio al subir a TikTok."
          >
            🔇 Sin voz
          </span>
        ) : (
          styleMeta && (
            <span
              className={cn(
                "rounded px-1 py-0 text-[9px]",
                styleMeta.cls,
              )}
              title={
                preset.style === "creator_pov"
                  ? "Persona hablando a cámara con lip-sync (solo Pro + Veo 3)"
                  : "Voz en off sobre planos del producto"
              }
            >
              🎤 {styleMeta.label}
            </span>
          )
        )}
        <span className="text-[9px] text-muted-foreground">
          {preset.duration_s}s
        </span>
        <TierDots tiers={preset.compatible_tiers} />
      </div>
      {preset.text_overlay && (
        <p className="mt-1 line-clamp-2 text-[10px] italic text-muted-foreground">
          &ldquo;{preset.text_overlay}&rdquo;
        </p>
      )}
    </button>
  );
}

/** Mini fila de bolitas de color por tier en el que el preset es
 *  compatible. Útil para que el user vea de un vistazo en qué modelos
 *  Seedance + Veo 3 puede correr este preset, sin abrir el detalle. */
function TierDots({ tiers }: { tiers: string[] }) {
  const TIER_DOT: Record<string, { cls: string; label: string }> = {
    standard: { cls: "bg-emerald-500", label: "Standard ($0.27/15s)" },
    advanced: { cls: "bg-amber-400", label: "Advanced ($0.71/15s)" },
    pro: { cls: "bg-rose-500", label: "Pro ($1.08/15s)" },
    veo3_prompt_only: { cls: "bg-violet-500", label: "Veo 3 (prompt+fotos)" },
  };
  const ORDER = ["standard", "advanced", "pro", "veo3_prompt_only"];
  const visible = ORDER.filter((t) => tiers.includes(t));
  if (visible.length === 0) return null;
  return (
    <span
      className="ml-0.5 flex items-center gap-0.5"
      title={`Tiers compatibles: ${visible.map((t) => TIER_DOT[t]?.label ?? t).join(" · ")}`}
    >
      {visible.map((t) => (
        <span
          key={t}
          className={cn("h-2 w-2 rounded-full", TIER_DOT[t]?.cls ?? "bg-muted")}
          aria-label={TIER_DOT[t]?.label ?? t}
        />
      ))}
    </span>
  );
}
