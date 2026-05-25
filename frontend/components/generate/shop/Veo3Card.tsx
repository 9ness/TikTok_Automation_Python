"use client";

import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  FlaskConical,
  Layers,
  Loader2,
  Mic,
  Music,
  Sparkles,
  Target,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { useProduct } from "@/lib/queries/products";
import { useGenerateVariants } from "@/lib/queries/products";
import type { VideoPreset } from "@/lib/types/product";
import { cn } from "@/lib/utils";

import { PresetControls } from "./PresetControls";

/** Modos paralelos al AutoVideoCard. Veo 3 no se encola (no hay API) →
 *  todos los modos terminan en un dialog con prompt(s) + fotos a
 *  descargar para que el user los pegue manualmente en Gemini/Flow. */
type GenMode = "single" | "batch" | "variants";

const MODE_META: Record<
  GenMode,
  { label: string; subtitle: string; icon: typeof Target; cls: string }
> = {
  single: {
    label: "1 prompt",
    subtitle: "1 preset → 1 prompt + fotos",
    icon: Target,
    cls: "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  batch: {
    label: "Lote",
    subtitle: "N presets → N prompts",
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

interface Props {
  userId: string;
  username: string;
  productId: string;
  hideTitle?: boolean;
}

interface ResultItem {
  presetId: string;
  name: string;
  veo3_prompt: string;
  /** Para vídeos >10s: N prompts (~8-10s cada uno) que el user pega
   *  secuencialmente en Flow Gemini para encadenar clips. Vacío si
   *  duration_s ≤ 10. */
  veo3_prompt_segments?: string[];
  veo3_photo_filenames: string[];
  duration_s?: number;
  hypothesis?: string;
}

export function Veo3Card({ userId, username, productId, hideTitle }: Props) {
  const product = useProduct(productId);
  const generateVariants = useGenerateVariants(productId);

  const [mode, setMode] = useState<GenMode>("single");
  const [activePresetId, setActivePresetId] = useState<string | null>(null);
  const [batchSelectedIds, setBatchSelectedIds] = useState<Set<string>>(
    new Set(),
  );
  const [variantsN, setVariantsN] = useState(3);
  const [expanded, setExpanded] = useState(false);
  const [selectedSavedName, setSelectedSavedName] = useState<string>("");

  const [results, setResults] = useState<ResultItem[] | null>(null);
  const [resultsTitle, setResultsTitle] = useState<string>("");

  // Toggles de filtrado equivalentes al picker de Auto vídeo:
  // - "Solo exclusivos Veo 3": presets que SOLO corren en veo3_prompt_only
  //   (no en Standard/Advanced/Pro Seedance). Útil para ver lo que
  //   justifica usar Veo 3 vs Seedance.
  // - "Solo réplicas virales": presets generados desde el tab Replicar viral.
  const [showOnlyExclusive, setShowOnlyExclusive] = useState(false);
  const [showOnlyViralReplica, setShowOnlyViralReplica] = useState(false);

  const presets = product.data?.video_presets ?? [];
  // Veo 3 solo lista presets compatibles con `veo3_prompt_only`.
  const compatibleVeo3 = useMemo(() => {
    let list = presets.filter((p) =>
      p.compatible_tiers.includes("veo3_prompt_only"),
    );
    if (showOnlyExclusive) {
      // Excluye presets que también corren en Seedance — deja solo
      // los exclusivos de Veo 3 (típicamente creator_pov + duraciones largas
      // con segments).
      list = list.filter(
        (p) =>
          !p.compatible_tiers.includes("standard") &&
          !p.compatible_tiers.includes("advanced") &&
          !p.compatible_tiers.includes("pro"),
      );
    }
    if (showOnlyViralReplica) {
      list = list.filter((p) => p.source === "viral_replica");
    }
    return list;
  }, [presets, showOnlyExclusive, showOnlyViralReplica]);

  // Total réplicas virales para mostrar contador en el toggle (también
  // sirve para deshabilitar el checkbox si no hay ninguna).
  const viralReplicaCount = useMemo(
    () =>
      presets.filter(
        (p) =>
          p.source === "viral_replica" &&
          p.compatible_tiers.includes("veo3_prompt_only"),
      ).length,
    [presets],
  );

  function toggleBatch(id: string) {
    setBatchSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function setAllBatch(ids: string[]) {
    setBatchSelectedIds(new Set(ids));
  }

  async function handleSubmit() {
    if (mode === "single") {
      if (!activePresetId) {
        toast.error("Elige un preset");
        return;
      }
      const p = compatibleVeo3.find((x) => x.id === activePresetId);
      if (!p) return;
      setResults([
        {
          presetId: p.id,
          name: p.name,
          veo3_prompt: p.veo3_prompt,
          veo3_prompt_segments: p.veo3_prompt_segments ?? [],
          veo3_photo_filenames: p.veo3_photo_filenames ?? [],
          duration_s: p.duration_s,
        },
      ]);
      setResultsTitle("🟣 Prompt Veo 3 listo");
      return;
    }
    if (mode === "batch") {
      if (batchSelectedIds.size === 0) {
        toast.error("Marca al menos 1 preset");
        return;
      }
      const items: ResultItem[] = compatibleVeo3
        .filter((p) => batchSelectedIds.has(p.id))
        .map((p) => ({
          presetId: p.id,
          name: p.name,
          veo3_prompt: p.veo3_prompt,
          veo3_prompt_segments: p.veo3_prompt_segments ?? [],
          veo3_photo_filenames: p.veo3_photo_filenames ?? [],
          duration_s: p.duration_s,
        }));
      setResults(items);
      setResultsTitle(`🟣 ${items.length} prompts Veo 3 listos`);
      return;
    }
    // variants
    if (!activePresetId) {
      toast.error("Elige el preset base");
      return;
    }
    try {
      toast(`Generando ${variantsN} variantes con IA…`);
      const r = await generateVariants.mutateAsync({
        presetId: activePresetId,
        input: {
          count: variantsN,
          dimensions: ["text_overlay", "text_overlay_color", "voice_tone", "cta_arrow"],
        },
      });
      if (r.variants.length === 0) {
        toast.error("Gemini no devolvió variantes. Reintenta.");
        return;
      }
      const items: ResultItem[] = r.variants.map((v, i) => ({
        presetId: v.id,
        name: v.name,
        veo3_prompt: v.veo3_prompt,
        veo3_photo_filenames: v.veo3_photo_filenames ?? [],
        hypothesis: r.meta?.[i]?.hypothesis,
      }));
      setResults(items);
      setResultsTitle(`🟣 ${items.length} variantes A/B Veo 3`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generación variantes falló");
    }
  }

  const hasPresets = compatibleVeo3.length > 0;

  return (
    <>
      <Card>
        <CardContent className="space-y-3 p-4 sm:p-5">
          {!hideTitle && (
            <div>
              <p className="text-lg font-semibold">🟣 Prompt Veo 3</p>
              <p className="text-xs text-muted-foreground">
                Veo 3 no va por API. Eliges presets, copias el prompt y
                descargas las fotos para pegar todo manualmente en
                Gemini chat / Flow.
              </p>
            </div>
          )}

          {/* PASO 1 · Modo */}
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

          {/* PASO 2 · Preset(s) (Veo 3 compat) */}
          <div className="space-y-1.5">
            <Label className="text-xs">
              2 ·{" "}
              {mode === "batch"
                ? "Marca los presets a procesar"
                : mode === "variants"
                  ? "Elige el preset base"
                  : "Elige el preset"}
            </Label>

            {/* Toggles de filtrado (mismos que en Auto vídeo, adaptados a Veo 3) */}
            {presets.length > 0 && (
              <div className="flex flex-wrap items-center gap-3 text-[11px]">
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={showOnlyExclusive}
                    onChange={(e) => setShowOnlyExclusive(e.target.checked)}
                    className="h-3.5 w-3.5 accent-violet-500"
                  />
                  <span title="Muestra solo presets que SOLO corren en Veo 3 (no en Seedance) — típicamente creator_pov UGC o réplicas >10s con segmentos.">
                    Solo exclusivos de Veo 3
                  </span>
                </label>
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={showOnlyViralReplica}
                    onChange={(e) => setShowOnlyViralReplica(e.target.checked)}
                    className="h-3.5 w-3.5 accent-fuchsia-500"
                    disabled={viralReplicaCount === 0}
                  />
                  <span title="Muestra solo presets generados desde 'Replicar viral' (los que clonan UGC de competidores).">
                    🎯 Solo réplicas virales
                    {viralReplicaCount > 0 && (
                      <span className="ml-0.5 text-fuchsia-600 dark:text-fuchsia-400">
                        ({viralReplicaCount})
                      </span>
                    )}
                  </span>
                </label>
              </div>
            )}

            {!hasPresets ? (
              <div className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-3 text-xs">
                {showOnlyViralReplica && viralReplicaCount === 0 ? (
                  <>
                    No hay réplicas virales compatibles con Veo 3 en este
                    producto. Genera una desde el tab{" "}
                    <strong>Replicar viral</strong>.
                  </>
                ) : showOnlyExclusive ? (
                  <>
                    No hay presets <strong>exclusivos</strong> de Veo 3.
                    Todos los presets Veo-compatibles también corren en
                    Seedance. Desmarca &ldquo;Solo exclusivos&rdquo; para verlos.
                  </>
                ) : (
                  <>
                    Este producto no tiene presets compatibles con Veo 3.
                    Ve a la página del producto → tab{" "}
                    <strong>Presets</strong> →{" "}
                    <strong>Regenerar todos</strong>.
                  </>
                )}
              </div>
            ) : (
              <Veo3PresetGrid
                presets={compatibleVeo3}
                multiMode={mode === "batch"}
                activeId={activePresetId}
                selectedIds={batchSelectedIds}
                onPickSingle={(id) => setActivePresetId(id)}
                onToggleBatch={toggleBatch}
                onSelectAll={setAllBatch}
              />
            )}
          </div>

          {/* Variantes: input N */}
          {mode === "variants" && (
            <div className="flex items-center gap-2 rounded-md border border-violet-500/30 bg-violet-500/5 p-2">
              <Label className="text-xs whitespace-nowrap" htmlFor="veo3-variants-n">
                Nº variantes
              </Label>
              <Input
                id="veo3-variants-n"
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
                Gemini genera N variantes A/B del preset (text_overlay,
                color, voice, cta…). Coste ~$0.01 / variante.
              </span>
            </div>
          )}

          {/* Acción principal */}
          <div className="flex flex-wrap items-center gap-2">
            {mode === "single" && (
              <Button
                onClick={handleSubmit}
                disabled={!activePresetId}
                className="flex-1 bg-emerald-600 hover:bg-emerald-700"
              >
                <Sparkles className="mr-1.5 h-4 w-4" />
                Ver prompt + fotos
              </Button>
            )}
            {mode === "batch" && (
              <Button
                onClick={handleSubmit}
                disabled={batchSelectedIds.size === 0}
                className="flex-1 bg-sky-600 hover:bg-sky-700"
              >
                <Layers className="mr-1.5 h-4 w-4" />
                Ver {batchSelectedIds.size}{" "}
                {batchSelectedIds.size === 1 ? "prompt" : "prompts"}
              </Button>
            )}
            {mode === "variants" && (
              <Button
                onClick={handleSubmit}
                disabled={!activePresetId || generateVariants.isPending}
                className="flex-1 bg-violet-600 hover:bg-violet-700"
              >
                {generateVariants.isPending ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <FlaskConical className="mr-1.5 h-4 w-4" />
                )}
                Generar {variantsN} variantes A/B
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => setExpanded((v) => !v)}>
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              <span className="ml-1 hidden sm:inline">
                {expanded ? "Ocultar" : "Avanzado"}
              </span>
            </Button>
          </div>

          {expanded && (
            <div className="space-y-3 border-t pt-3">
              <p className="text-[10px] text-muted-foreground">
                Configuraciones guardadas (legacy). Solo si las usas:
              </p>
              <PresetControls
                userId={userId}
                productId={productId}
                kind="veo3"
                selectedName={selectedSavedName}
                onSelectName={setSelectedSavedName}
                currentConfig={{}}
                onLoadConfig={() => {
                  toast.info(
                    "Las configuraciones guardadas no aplican a Veo 3 nuevo (usa los presets del producto).",
                  );
                }}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dialog con resultados */}
      <Dialog open={results !== null} onOpenChange={(o) => !o && setResults(null)}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{resultsTitle}</DialogTitle>
            <DialogDescription>
              Para cada preset: <strong>copia el prompt</strong> y{" "}
              <strong>descarga las fotos</strong>. Pega ambas cosas en
              Gemini chat / Flow.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {results?.map((r, idx) => (
              <ResultItemCard
                key={r.presetId + idx}
                item={r}
                index={idx}
                productId={productId}
              />
            ))}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setResults(null)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// =============================================================
// Grid mini-cards filtradas a Veo 3
// =============================================================
function Veo3PresetGrid({
  presets,
  multiMode,
  activeId,
  selectedIds,
  onPickSingle,
  onToggleBatch,
  onSelectAll,
}: {
  presets: VideoPreset[];
  multiMode: boolean;
  activeId: string | null;
  selectedIds: Set<string>;
  onPickSingle: (id: string) => void;
  onToggleBatch: (id: string) => void;
  onSelectAll: (ids: string[]) => void;
}) {
  const musicCount = presets.filter((p) => p.kind === "music").length;
  const scriptedCount = presets.filter((p) => p.kind === "scripted").length;
  const selCount = selectedIds.size;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-violet-500" />
          <strong>Presets Veo 3 compat.</strong>
          <span className="text-muted-foreground">
            {presets.length} compat. {musicCount > 0 && `· 🎵 ${musicCount}`}
            {scriptedCount > 0 && ` · 🎤 ${scriptedCount}`}
          </span>
          {multiMode && selCount > 0 && (
            <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-700 dark:text-sky-300">
              {selCount} marcados
            </span>
          )}
        </div>
        {multiMode && (
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => onSelectAll(presets.map((p) => p.id))}
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
          </div>
        )}
      </div>
      <div className="-mx-1 flex gap-2 overflow-x-auto pb-1 sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible md:grid-cols-3">
        {presets.map((p) => {
          const isActive = !multiMode && activeId === p.id;
          const checked = multiMode && selectedIds.has(p.id);
          const Icon = p.kind === "music" ? Music : Mic;
          const accent = p.kind === "music" ? "sky" : "violet";
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => (multiMode ? onToggleBatch(p.id) : onPickSingle(p.id))}
              className={cn(
                "min-w-[220px] shrink-0 rounded-md border-2 p-2 text-left transition-all sm:min-w-0",
                isActive || checked
                  ? p.kind === "music"
                    ? "border-sky-500 bg-sky-500/15"
                    : "border-violet-500 bg-violet-500/15"
                  : `border-${accent}-500/30 bg-${accent}-500/5 hover:border-${accent}-500/60`,
              )}
            >
              <div className="flex items-center gap-1.5">
                {multiMode && (
                  <span
                    className={cn(
                      "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border-2 text-[10px] font-bold leading-none",
                      checked
                        ? p.kind === "music"
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
                    p.kind === "music" ? "text-sky-500" : "text-violet-500",
                  )}
                />
                <strong className="truncate text-[11px]">{p.name}</strong>
                {p.source === "viral_replica" && (
                  <span
                    className="shrink-0 rounded bg-fuchsia-500/15 px-1 py-0 text-[9px] font-medium text-fuchsia-700 dark:text-fuchsia-300"
                    title="Preset generado desde 'Replicar viral'"
                  >
                    🎯
                  </span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1">
                {/* Tipo principal: música (sin voz) vs creator UGC vs voiceover */}
                {p.kind === "music" ? (
                  <span
                    className="rounded bg-sky-500/15 px-1 py-0 text-[9px] text-sky-700 dark:text-sky-300"
                    title="Vídeo sin voz · solo música + texto en pantalla"
                  >
                    🔇 Sin voz
                  </span>
                ) : p.style === "creator_pov" ? (
                  <span
                    className="rounded bg-violet-500/15 px-1 py-0 text-[9px] text-violet-700 dark:text-violet-300"
                    title="Persona hablando a cámara con lip-sync (UGC)"
                  >
                    👤 Creator UGC
                  </span>
                ) : (
                  <span
                    className="rounded bg-violet-500/15 px-1 py-0 text-[9px] text-violet-700 dark:text-violet-300"
                    title="Voz en off sobre planos del producto (sin persona en cámara)"
                  >
                    🎤 Voiceover
                  </span>
                )}
                {/* Shot style: 1 plano continuo vs cortes/multi-toma */}
                <span
                  className="rounded bg-cyan-500/15 px-1 py-0 text-[9px] text-cyan-700 dark:text-cyan-300"
                  title={
                    p.shot_style === "single_shot"
                      ? "1 plano continuo (sin cortes)"
                      : p.shot_style === "multi_shot"
                        ? "Múltiples planos / cortes / cambios"
                        : "Auto — el modelo decide según duración"
                  }
                >
                  {p.shot_style === "single_shot"
                    ? "🎬 1 toma"
                    : p.shot_style === "multi_shot"
                      ? "✂️ Multi-toma"
                      : "🎬 Auto"}
                </span>
                {p.angle && (
                  <span className="rounded bg-muted px-1 py-0 text-[9px]">
                    {p.angle}
                  </span>
                )}
                <span className="text-[9px] text-muted-foreground">
                  {p.duration_s}s
                </span>
                <span
                  className="text-[9px] text-muted-foreground"
                  title="Fotos elegidas por Gemini para adjuntar a Veo 3"
                >
                  · 📎 {p.veo3_photo_filenames?.length ?? 0}
                </span>
              </div>
              {p.text_overlay && (
                <p className="mt-1 line-clamp-2 text-[10px] italic text-muted-foreground">
                  &ldquo;{p.text_overlay}&rdquo;
                </p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// =============================================================
// Card de resultado: prompt + fotos descargables
// =============================================================
function ResultItemCard({
  item,
  index,
  productId,
}: {
  item: ResultItem;
  index: number;
  productId: string;
}) {
  const segments = item.veo3_prompt_segments ?? [];
  const hasSegments = segments.length > 0;

  async function copyText(text: string, label: string) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      toast.success(`${label} copiado`);
    } catch (e) {
      toast.error("No pude copiar");
    }
  }

  async function copyPrompt() {
    return copyText(item.veo3_prompt, "Prompt");
  }

  async function downloadAll() {
    if (item.veo3_photo_filenames.length === 0) return;
    toast.info(`Descargando ${item.veo3_photo_filenames.length} foto(s)…`);
    for (let i = 0; i < item.veo3_photo_filenames.length; i++) {
      const fn = item.veo3_photo_filenames[i];
      if (!fn) continue;
      const url = buildPhotoUrl(productId, fn);
      if (!url) continue;
      await downloadOne(url, fn);
      if (i < item.veo3_photo_filenames.length - 1) {
        await new Promise((r) => setTimeout(r, 250));
      }
    }
    toast.success(`Descargadas ${item.veo3_photo_filenames.length} foto(s)`);
  }

  return (
    <div className="rounded-md border border-violet-500/30 bg-violet-500/5 p-2 text-xs">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <strong className="truncate text-sm">
          #{index + 1} · {item.name}
          {hasSegments && (
            <span className="ml-1 rounded bg-purple-500/15 px-1 py-0 text-[9px] font-medium text-purple-700 dark:text-purple-300">
              {segments.length} segmentos · {item.duration_s}s
            </span>
          )}
        </strong>
        <div className="flex gap-1">
          {!hasSegments && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 gap-1 px-2 text-[10px]"
              onClick={copyPrompt}
            >
              <Copy className="h-3 w-3" />
              Copiar prompt
            </Button>
          )}
          {item.veo3_photo_filenames.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 gap-1 px-2 text-[10px]"
              onClick={downloadAll}
            >
              <Download className="h-3 w-3" />
              Descargar fotos ({item.veo3_photo_filenames.length})
            </Button>
          )}
        </div>
      </div>
      {item.hypothesis && (
        <p className="mb-1 text-[10px] italic text-violet-700 dark:text-violet-300">
          Hipótesis: {item.hypothesis}
        </p>
      )}
      {hasSegments ? (
        <div className="space-y-1.5">
          <p className="text-[10px] text-muted-foreground">
            Pega cada segmento en orden en Flow Gemini — cada clip ~8-10s
            con continuidad del anterior. Total ≈ {item.duration_s}s.
          </p>
          {segments.map((seg, i) => (
            <div
              key={i}
              className="rounded border border-purple-500/30 bg-purple-500/5 p-1.5"
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] font-semibold text-purple-700 dark:text-purple-300">
                  Segmento {i + 1} / {segments.length}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-5 gap-1 px-1.5 text-[9px]"
                  onClick={() => copyText(seg, `Segmento ${i + 1}`)}
                >
                  <Copy className="h-2.5 w-2.5" />
                  Copiar
                </Button>
              </div>
              <Textarea
                readOnly
                value={seg}
                className="min-h-[80px] font-mono text-[10px]"
                onFocus={(e) => e.currentTarget.select()}
              />
            </div>
          ))}
        </div>
      ) : (
        <Textarea
          readOnly
          value={item.veo3_prompt}
          className="min-h-[110px] font-mono text-[10px]"
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
      {item.veo3_photo_filenames.length === 0 ? (
        <div className="mt-1.5 rounded border border-amber-500/40 bg-amber-500/5 p-1.5 text-[10px] text-amber-700 dark:text-amber-300">
          ⚠️ Este preset no tiene fotos asignadas. Probablemente se generó
          antes de añadir esta funcionalidad. Edítalo desde el tab Presets
          del producto y marca fotos, o pulsa &ldquo;Regenerar todos&rdquo;
          para que Gemini elija fotos automáticamente.
        </div>
      ) : (
        <div className="mt-1.5">
          <p className="text-[10px] text-muted-foreground">
            📎 Fotos a adjuntar:
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {item.veo3_photo_filenames.map((fn) => {
              const url = buildPhotoUrl(productId, fn);
              return (
                <div
                  key={fn}
                  className="flex items-center gap-1 rounded border border-violet-500/30 bg-background p-0.5"
                  title={fn}
                >
                  {url && (
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Ver original en pestaña nueva"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={url}
                        alt={fn}
                        className="h-10 w-10 rounded object-cover hover:opacity-80"
                      />
                    </a>
                  )}
                  <span className="max-w-[120px] truncate text-[9px] text-muted-foreground">
                    {fn}
                  </span>
                  {url && (
                    <button
                      type="button"
                      onClick={() => downloadOne(url, fn)}
                      className="ml-0.5 rounded px-1 text-[10px] text-muted-foreground hover:bg-violet-500/20 hover:text-violet-700 dark:hover:text-violet-300"
                      title="Descargar esta foto"
                    >
                      ⬇
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================
// Helpers
// =============================================================
function buildPhotoUrl(productId: string, filename: string): string | null {
  if (!productId || !filename) return null;
  const base =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}/api/v1/products/${productId}/photos/${encodeURIComponent(filename)}/file${qs}`;
}

async function downloadOne(url: string, filename: string): Promise<void> {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (e) {
    toast.error(
      e instanceof Error ? `Descarga falló (${filename})` : `Descarga falló`,
    );
  }
}
