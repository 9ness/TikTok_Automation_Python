"use client";

import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Mic,
  Music,
  Pencil,
  Save,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FontSelector } from "@/components/ui/font-selector";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useFontByPath, useFontFamily } from "@/lib/queries/fonts";
import {
  useDeleteAllVideoPresets,
  useDeleteVideoPreset,
  useGeneratePresets,
  useUpdateVideoPreset,
} from "@/lib/queries/products";
import { useVoices } from "@/lib/queries/voices";
import { TabHint } from "./TabHint";

const TEXT_POSITIONS = [
  "top_center", "top_left", "top_right",
  "middle_center", "middle_left", "middle_right",
  "bottom_center", "bottom_left", "bottom_right",
];
const TEXT_ANIMATIONS = [
  "none", "fade_in", "slide_up", "slide_down", "pop", "typing",
  "shake", "bounce",
];
const TEXT_BACKGROUNDS = ["none", "black_bar", "blur"];
const VOICE_TONES = ["energetic", "calm", "persuasive", "serious", "playful"];
import type {
  Product,
  VideoPreset,
  VideoPresetUpdateInput,
} from "@/lib/types/product";
import { cn } from "@/lib/utils";

const TIER_EMOJI: Record<string, string> = {
  standard: "🟢",
  advanced: "🟡",
  pro: "🔴",
  veo3_prompt_only: "🟣",
  nano_banana_prompt_only: "🍌",
};
const TIER_NAME: Record<string, string> = {
  standard: "Standard",
  advanced: "Advanced",
  pro: "Pro",
  veo3_prompt_only: "Veo 3",
  nano_banana_prompt_only: "Nano Banana",
};
const ALL_TIERS_ORDER = ["standard", "advanced", "pro", "veo3_prompt_only"];

const STYLE_LABEL: Record<string, { label: string; cls: string; help: string }> = {
  voiceover: {
    label: "Voiceover",
    cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
    help:
      "Voz en off sobre planos del producto · ninguna persona habla en cámara · funciona en todos los tiers",
  },
  creator_pov: {
    label: "Creator POV",
    cls: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
    help:
      "Persona habla a cámara con lip-sync · solo Pro (con foto de persona) y Veo 3 (nativo)",
  },
};

export function PresetsManager({ product }: { product: Product }) {
  const generate = useGeneratePresets(product.id);
  const deleteAll = useDeleteAllVideoPresets(product.id);
  const presets = product.video_presets ?? [];
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);

  async function confirmDeleteAll() {
    try {
      const r = await deleteAll.mutateAsync({});
      toast.success(`${r.deleted_count} preset(s) eliminados`);
      setDeleteAllOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al borrar");
    }
  }

  const manualCount = presets.filter((p) => p.source === "manual").length;

  // ─── Filtros ───
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<"all" | "music" | "scripted">("all");
  const [tierFilter, setTierFilter] = useState<string>("all");
  const [styleFilter, setStyleFilter] = useState<"all" | "voiceover" | "creator_pov">("all");
  const [sortBy, setSortBy] = useState<"new" | "old" | "angle" | "duration">("new");

  // Aplica filtros + ordena
  const filtered = useMemo(() => {
    let list = presets;
    if (kindFilter !== "all") list = list.filter((p) => p.kind === kindFilter);
    if (tierFilter !== "all") {
      list = list.filter((p) => p.compatible_tiers.includes(tierFilter));
    }
    if (styleFilter !== "all") {
      list = list.filter((p) => p.style === styleFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.angle.toLowerCase().includes(q) ||
          p.text_overlay.toLowerCase().includes(q) ||
          p.voice_script.toLowerCase().includes(q) ||
          p.title.toLowerCase().includes(q),
      );
    }
    const sorted = [...list];
    sorted.sort((a, b) => {
      if (sortBy === "new") return b.created_at.localeCompare(a.created_at);
      if (sortBy === "old") return a.created_at.localeCompare(b.created_at);
      if (sortBy === "angle") return (a.angle || "zzz").localeCompare(b.angle || "zzz");
      if (sortBy === "duration") return a.duration_s - b.duration_s;
      return 0;
    });
    return sorted;
  }, [presets, search, kindFilter, tierFilter, styleFilter, sortBy]);

  const musicPresets = presets.filter((p) => p.kind === "music");
  const scriptedPresets = presets.filter((p) => p.kind === "scripted");
  const filteredMusic = filtered.filter((p) => p.kind === "music");
  const filteredScripted = filtered.filter((p) => p.kind === "scripted");

  async function handleGenerate(
    kind: "music" | "scripted" | "both",
    replace = true,                      // por defecto reemplaza — evita duplicados
  ) {
    try {
      const r = await generate.mutateAsync({
        kind,
        n_music: 8,
        n_scripted: 12,
        replace_existing: replace,
      });
      const parts: string[] = [];
      if (r.created_count > 0) {
        parts.push(
          `${r.created_count} preset(s) ${replace ? "regenerados" : "añadidos"}`,
        );
      } else {
        parts.push("Sin presets nuevos");
      }
      if (r.warnings.length > 0) {
        parts.push(`⚠️ ${r.warnings[0]}`);
      }
      toast.success(parts.join(" · "));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Generación falló");
    }
  }

  return (
    <div className="space-y-6">
      {/* CTA de generación */}
      <Card>
        <CardContent className="space-y-3 p-3 sm:p-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-emerald-500" />
              <h3 className="text-sm font-semibold">
                Generar presets con Gemini
              </h3>
            </div>
            <p className="text-xs text-muted-foreground">
              Crea blueprints precocinados para el generador. Cada preset
              trae prompts ya listos para los 4 tiers (Standard / Advanced /
              Pro / Veo 3). En <code>/tiktok-shop/generate</code> bastará con
              elegirlo y encolar — todo el script, hook, CTA y prompts
              vendrán rellenos.
            </p>
          </div>
          {/* Botón principal grande — full-width en mobile */}
          <Button
            onClick={() => handleGenerate("both", true)}
            disabled={generate.isPending}
            className="w-full bg-emerald-600 hover:bg-emerald-700 sm:w-auto"
          >
            {generate.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            {presets.length > 0
              ? "Regenerar todos (8 + 12)"
              : "Generar todos (8 música + 12 scripted)"}
          </Button>

          {/* Secundarios — grid 2 cols mobile, fila desktop */}
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleGenerate("music", true)}
              disabled={generate.isPending}
            >
              <Music className="h-3.5 w-3.5" />
              <span className="ml-1.5 text-xs">
                {musicPresets.length > 0 ? "Música" : "Solo música"}
              </span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleGenerate("scripted", true)}
              disabled={generate.isPending}
            >
              <Mic className="h-3.5 w-3.5" />
              <span className="ml-1.5 text-xs">
                {scriptedPresets.length > 0 ? "Scripted" : "Solo scripted"}
              </span>
            </Button>
            {presets.length > 0 && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleGenerate("both", false)}
                  disabled={generate.isPending}
                  className="text-muted-foreground hover:bg-muted"
                  title="Acumula 20 más sin borrar (experimental)"
                >
                  <span className="text-xs">+ Acumular</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDeleteAllOpen(true)}
                  disabled={deleteAll.isPending || generate.isPending}
                  className="text-rose-600 hover:bg-rose-500/10 hover:text-rose-700"
                >
                  {deleteAll.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                  <span className="ml-1.5 text-xs">Borrar todos</span>
                </Button>
              </>
            )}
          </div>
          <p className="text-[10px] text-muted-foreground">
            Por defecto <strong>reemplaza</strong> los autogenerados (los manuales
            no se tocan). &ldquo;Acumular&rdquo; los suma sin borrar. &ldquo;Borrar
            todos&rdquo; vacía la lista completa.
          </p>
        </CardContent>
      </Card>

      {/* Barra de filtros + búsqueda */}
      {presets.length > 0 && (
        <Card>
          <CardContent className="space-y-2 p-2 sm:p-3">
            {/* Búsqueda full-width */}
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Input
                placeholder="Buscar nombre, ángulo, texto…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-8 flex-1 text-xs"
              />
              {search && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setSearch("")}
                  className="h-7 w-7 shrink-0"
                  aria-label="Limpiar"
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                className="h-7 shrink-0 rounded border border-input bg-background px-1 text-[10px]"
                aria-label="Ordenar"
              >
                <option value="new">⬇ Nuevos</option>
                <option value="old">⬆ Antiguos</option>
                <option value="angle">A-Z</option>
                <option value="duration">⏱</option>
              </select>
            </div>

            {/* Tipo: 3 chips siempre visibles */}
            <div className="flex flex-wrap gap-1 text-[10px]">
              <FilterChip
                label="Todos"
                active={kindFilter === "all"}
                onClick={() => setKindFilter("all")}
                count={presets.length}
              />
              <FilterChip
                label="🎵 Música"
                active={kindFilter === "music"}
                onClick={() => setKindFilter("music")}
                count={musicPresets.length}
              />
              <FilterChip
                label="🎤 Scripted"
                active={kindFilter === "scripted"}
                onClick={() => setKindFilter("scripted")}
                count={scriptedPresets.length}
              />
            </div>

            {/* Tiers */}
            <div className="flex flex-wrap gap-1 text-[10px]">
              <span className="self-center text-muted-foreground">Tier:</span>
              <FilterChip
                label="🟢"
                active={tierFilter === "standard"}
                onClick={() =>
                  setTierFilter(tierFilter === "standard" ? "all" : "standard")
                }
              />
              <FilterChip
                label="🟡"
                active={tierFilter === "advanced"}
                onClick={() =>
                  setTierFilter(tierFilter === "advanced" ? "all" : "advanced")
                }
              />
              <FilterChip
                label="🔴"
                active={tierFilter === "pro"}
                onClick={() =>
                  setTierFilter(tierFilter === "pro" ? "all" : "pro")
                }
              />
              <FilterChip
                label="🟣"
                active={tierFilter === "veo3_prompt_only"}
                onClick={() =>
                  setTierFilter(
                    tierFilter === "veo3_prompt_only" ? "all" : "veo3_prompt_only",
                  )
                }
              />
              {kindFilter !== "music" && (
                <>
                  <span className="ml-2 self-center text-muted-foreground">
                    Estilo:
                  </span>
                  <FilterChip
                    label="Voiceover"
                    active={styleFilter === "voiceover"}
                    onClick={() =>
                      setStyleFilter(
                        styleFilter === "voiceover" ? "all" : "voiceover",
                      )
                    }
                  />
                  <FilterChip
                    label="Creator POV"
                    active={styleFilter === "creator_pov"}
                    onClick={() =>
                      setStyleFilter(
                        styleFilter === "creator_pov" ? "all" : "creator_pov",
                      )
                    }
                  />
                </>
              )}
            </div>

            {filtered.length !== presets.length && (
              <p className="text-[10px] text-muted-foreground">
                Mostrando {filtered.length} de {presets.length} presets.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Música */}
      {(kindFilter === "all" || kindFilter === "music") && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Music className="h-4 w-4 text-sky-500" />
            <h3 className="text-sm font-semibold">
              Presets musicales · {filteredMusic.length}
              {filteredMusic.length !== musicPresets.length && (
                <span className="text-muted-foreground">
                  {" "}/ {musicPresets.length}
                </span>
              )}
            </h3>
            <span className="hidden text-[10px] text-muted-foreground sm:inline">
              Sin voz · 8-15s · texto en pantalla + música
            </span>
          </div>
          {musicPresets.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Aún no hay presets musicales. Pulsa <strong>Solo música</strong>{" "}
              arriba.
            </p>
          ) : filteredMusic.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Ninguno coincide con los filtros actuales.
            </p>
          ) : (
            <div className="grid gap-2 sm:gap-3 lg:grid-cols-2">
              {filteredMusic.map((p) => (
                <PresetCard
                  key={p.id}
                  product={product}
                  preset={p}
                  isEditing={editingId === p.id}
                  onEdit={() => setEditingId(p.id)}
                  onCancelEdit={() => setEditingId(null)}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Scripted */}
      {(kindFilter === "all" || kindFilter === "scripted") && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Mic className="h-4 w-4 text-violet-500" />
            <h3 className="text-sm font-semibold">
              Presets scripted · {filteredScripted.length}
              {filteredScripted.length !== scriptedPresets.length && (
                <span className="text-muted-foreground">
                  {" "}/ {scriptedPresets.length}
                </span>
              )}
            </h3>
            <span className="hidden text-[10px] text-muted-foreground sm:inline">
              Con voz · creator-style · ángulos de venta
            </span>
          </div>
          {scriptedPresets.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Aún no hay presets scripted. Pulsa <strong>Solo scripted</strong>{" "}
              arriba.
            </p>
          ) : filteredScripted.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Ninguno coincide con los filtros actuales.
            </p>
          ) : (
            <div className="grid gap-2 sm:gap-3 lg:grid-cols-2">
              {filteredScripted.map((p) => (
                <PresetCard
                  key={p.id}
                  product={product}
                  preset={p}
                  isEditing={editingId === p.id}
                  onEdit={() => setEditingId(p.id)}
                  onCancelEdit={() => setEditingId(null)}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* AlertDialog "Borrar todos" — estilo del proyecto */}
      <AlertDialog open={deleteAllOpen} onOpenChange={setDeleteAllOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              ¿Borrar los {presets.length} presets del producto?
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              <span className="block">
                Se eliminarán <strong>todos</strong> los presets del catálogo:{" "}
                {presets.filter((p) => p.source !== "manual").length}{" "}
                autogenerados y{" "}
                <strong>
                  {manualCount} manual{manualCount === 1 ? "" : "es"}
                </strong>
                {manualCount > 0 ? " (incluidos los tuyos)" : ""}.
              </span>
              <span className="block">
                Después podrás <strong>regenerar</strong> nuevos con Gemini, pero
                los actuales (incluidas ediciones a mano) se pierden.{" "}
                <strong className="text-destructive">
                  Esta acción no se puede deshacer.
                </strong>
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteAll.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteAll}
              disabled={deleteAll.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteAll.isPending ? (
                <>
                  <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                  Borrando…
                </>
              ) : (
                <>
                  <Trash2 className="mr-2 h-3 w-3" />
                  Sí, borrar todos
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
  count,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-2 py-0.5 transition-colors",
        active
          ? "border-emerald-500 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
          : "border-muted hover:bg-accent/40",
      )}
    >
      {label}
      {count !== undefined && (
        <span className="ml-1 opacity-60">({count})</span>
      )}
    </button>
  );
}

// ===========================================================================
// PresetCard
// ===========================================================================
function PresetCard({
  product,
  preset,
  isEditing,
  onEdit,
  onCancelEdit,
}: {
  product: Product;
  preset: VideoPreset;
  isEditing: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
}) {
  const deleteMut = useDeleteVideoPreset(product.id);
  const updateMut = useUpdateVideoPreset(product.id);
  const [open, setOpen] = useState(false);

  // Estado local mientras se edita
  const [draft, setDraft] = useState<VideoPresetUpdateInput>(() => ({
    name: preset.name,
    angle: preset.angle,
    shot_style: preset.shot_style,
    strategy: preset.strategy,
    duration_s: preset.duration_s,
    text_overlay: preset.text_overlay,
    text_overlay_style: { ...preset.text_overlay_style },
    subtitle_style: { ...preset.subtitle_style },
    cta_arrow_style: { ...preset.cta_arrow_style },
    music_mood: preset.music_mood,
    voice_id: preset.voice_id,
    voice_tone: preset.voice_tone,
    title: preset.title,
    voice_script: preset.voice_script,
    hooks_alternatives: preset.hooks_alternatives,
    cta: preset.cta,
    oratory_tips: preset.oratory_tips,
    keywords: preset.keywords,
    seedance_prompt: preset.seedance_prompt,
    veo3_prompt: preset.veo3_prompt,
    notes: preset.notes,
  }));

  // Lista de voces para el selector (solo en presets scripted)
  const voicesQuery = useVoices({ language: "es" });
  const overlayStyle = draft.text_overlay_style ?? preset.text_overlay_style;
  const subStyle = draft.subtitle_style ?? preset.subtitle_style;
  const arrowStyle = draft.cta_arrow_style ?? preset.cta_arrow_style;
  function setOverlay(patch: Partial<typeof overlayStyle>) {
    setDraft((d) => ({
      ...d,
      text_overlay_style: { ...(d.text_overlay_style ?? preset.text_overlay_style), ...patch },
    }));
  }
  function setSub(patch: Partial<typeof subStyle>) {
    setDraft((d) => ({
      ...d,
      subtitle_style: { ...(d.subtitle_style ?? preset.subtitle_style), ...patch },
    }));
  }
  function setArrow(patch: Partial<typeof arrowStyle>) {
    setDraft((d) => ({
      ...d,
      cta_arrow_style: {
        ...(d.cta_arrow_style ?? preset.cta_arrow_style),
        ...patch,
      },
    }));
  }

  // Fuentes — cargar @font-face para el preview real
  const overlayFontEntry = useFontByPath(overlayStyle.font);
  const overlayFontFamily = useFontFamily(overlayFontEntry);
  const subFontEntry = useFontByPath(subStyle.font);
  const subFontFamily = useFontFamily(subFontEntry);

  async function handleSave() {
    try {
      await updateMut.mutateAsync({ presetId: preset.id, patch: draft });
      toast.success("Preset actualizado");
      onCancelEdit();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Guardar falló");
    }
  }

  async function handleDelete() {
    if (!confirm(`¿Eliminar preset "${preset.name}"?`)) return;
    try {
      await deleteMut.mutateAsync(preset.id);
      toast.success("Preset eliminado");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Eliminar falló");
    }
  }

  if (isEditing) {
    return (
      <Card className="border-emerald-500/40">
        <CardContent className="space-y-3 p-3 text-xs">
          <div className="flex items-center justify-between">
            <strong className="text-sm">Editando preset</strong>
            <Button variant="ghost" size="icon" onClick={onCancelEdit}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>

          <Field label="Nombre">
            <Input
              value={draft.name ?? ""}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Ángulo">
              <Input
                value={draft.angle ?? ""}
                onChange={(e) => setDraft({ ...draft, angle: e.target.value })}
              />
            </Field>
            <Field label="Duración (s)">
              <Input
                type="number"
                min={5}
                max={60}
                value={draft.duration_s ?? 0}
                onChange={(e) =>
                  setDraft({ ...draft, duration_s: parseInt(e.target.value, 10) })
                }
              />
            </Field>
          </div>
          <Field label="Texto en pantalla">
            <Input
              value={draft.text_overlay ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, text_overlay: e.target.value })
              }
            />
          </Field>
          {preset.kind === "scripted" && (
            <>
              <Field label="Título">
                <Input
                  value={draft.title ?? ""}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                />
              </Field>
              <Field label="Guion para voz">
                <Textarea
                  rows={5}
                  value={draft.voice_script ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, voice_script: e.target.value })
                  }
                />
              </Field>
              <Field label="Hooks alternativos (1 por línea)">
                <Textarea
                  rows={3}
                  value={(draft.hooks_alternatives ?? []).join("\n")}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      hooks_alternatives: e.target.value
                        .split("\n")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Field>
              <Field label="CTA">
                <Input
                  value={draft.cta ?? ""}
                  onChange={(e) => setDraft({ ...draft, cta: e.target.value })}
                />
              </Field>
              <Field label="Oratory tips">
                <Textarea
                  rows={2}
                  value={draft.oratory_tips ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, oratory_tips: e.target.value })
                  }
                />
              </Field>
              <Field label="Keywords (coma)">
                <Input
                  value={(draft.keywords ?? []).join(", ")}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      keywords: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Field>
            </>
          )}
          <Field label="Music mood">
            <Input
              value={draft.music_mood ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, music_mood: e.target.value })
              }
            />
          </Field>

          {/* Estilo de planos (single vs multi-shot) */}
          <div className="space-y-2 rounded-md border border-cyan-500/30 bg-cyan-500/5 p-2">
            <strong className="text-[11px] text-cyan-700 dark:text-cyan-300">
              🎬 Estilo de planos del vídeo
            </strong>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Estilo">
                <select
                  value={draft.shot_style ?? "auto"}
                  onChange={(e) =>
                    setDraft({ ...draft, shot_style: e.target.value })
                  }
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                >
                  <option value="auto">Auto (según duración)</option>
                  <option value="single_shot">Single shot — 1 plano continuo</option>
                  <option value="multi_shot">Multi shot — cortes (3-4 clips)</option>
                </select>
              </Field>
              <Field label="Movimiento cámara">
                <select
                  value={draft.strategy ?? "dynamic"}
                  onChange={(e) =>
                    setDraft({ ...draft, strategy: e.target.value })
                  }
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                >
                  <option value="cinematic">Cinematic — lento, continuo</option>
                  <option value="dynamic">Dynamic — variado, cortes</option>
                </select>
              </Field>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Single shot = Seedance genera 1 vídeo de {preset.duration_s}s
              de una toma. Multi shot = 2-4 clips encadenados (mín 4s
              por clip). Desde 8s ambas opciones son válidas — depende
              del feel del vídeo.
              {preset.duration_s < 8 &&
                " ⚠️ Con duración <8s solo cabe single shot (mín. clip Seedance = 4s)."}
              {preset.style === "creator_pov" &&
                " · Creator POV requiere single_shot (lip-sync continuo)."}
            </p>
          </div>

          {/* Voz — solo aplicable a presets scripted */}
          {preset.kind === "scripted" && (
            <div className="space-y-2 rounded-md border border-violet-500/30 bg-violet-500/5 p-2">
              <strong className="text-[11px] text-violet-700 dark:text-violet-300">
                🎤 Voz (TTS narración)
              </strong>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Voice ID (MiniMax / clonada)">
                  <select
                    value={draft.voice_id ?? ""}
                    onChange={(e) =>
                      setDraft({ ...draft, voice_id: e.target.value || null })
                    }
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                  >
                    <option value="">— sin override (default producto) —</option>
                    {(voicesQuery.data?.items ?? []).map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name || v.id}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Tono">
                  <select
                    value={draft.voice_tone ?? "energetic"}
                    onChange={(e) =>
                      setDraft({ ...draft, voice_tone: e.target.value })
                    }
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                  >
                    {VOICE_TONES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
            </div>
          )}

          {/* Estilo del texto overlay */}
          <div className="space-y-2 rounded-md border border-sky-500/30 bg-sky-500/5 p-2">
            <strong className="text-[11px] text-sky-700 dark:text-sky-300">
              🎨 Estilo del gancho en pantalla
            </strong>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Posición">
                <select
                  value={overlayStyle.position}
                  onChange={(e) => setOverlay({ position: e.target.value })}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                >
                  {TEXT_POSITIONS.map((p) => (
                    <option key={p} value={p}>
                      {p.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Animación">
                <select
                  value={overlayStyle.animation}
                  onChange={(e) => setOverlay({ animation: e.target.value })}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                >
                  {TEXT_ANIMATIONS.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Fuente">
                <FontSelector
                  value={overlayStyle.font}
                  onChange={(p) => setOverlay({ font: p })}
                  allowUpload={false}
                />
              </Field>
              <Field label="Tamaño (px)">
                <Input
                  type="number"
                  min={12}
                  max={200}
                  value={overlayStyle.size_px}
                  onChange={(e) =>
                    setOverlay({ size_px: parseInt(e.target.value, 10) })
                  }
                />
              </Field>
              <Field label="Color texto">
                <div className="flex gap-1">
                  <input
                    type="color"
                    value={overlayStyle.color}
                    onChange={(e) => setOverlay({ color: e.target.value })}
                    className="h-9 w-12 cursor-pointer rounded border border-input bg-transparent"
                  />
                  <Input
                    value={overlayStyle.color}
                    onChange={(e) => setOverlay({ color: e.target.value })}
                    className="flex-1 font-mono"
                  />
                </div>
              </Field>
              <Field label="Color contorno">
                <div className="flex gap-1">
                  <input
                    type="color"
                    value={overlayStyle.stroke_color}
                    onChange={(e) =>
                      setOverlay({ stroke_color: e.target.value })
                    }
                    className="h-9 w-12 cursor-pointer rounded border border-input bg-transparent"
                  />
                  <Input
                    value={overlayStyle.stroke_color}
                    onChange={(e) =>
                      setOverlay({ stroke_color: e.target.value })
                    }
                    className="flex-1 font-mono"
                  />
                </div>
              </Field>
              <Field label="Fondo">
                <select
                  value={overlayStyle.background}
                  onChange={(e) => setOverlay({ background: e.target.value })}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                >
                  {TEXT_BACKGROUNDS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Mayúsculas">
                <label className="flex h-9 items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={overlayStyle.uppercase}
                    onChange={(e) =>
                      setOverlay({ uppercase: e.target.checked })
                    }
                    className="h-4 w-4"
                  />
                  uppercase
                </label>
              </Field>
              <Field label="Duración en pantalla (s)">
                <Input
                  type="number"
                  step="0.5"
                  min={0.5}
                  max={30}
                  value={overlayStyle.duration_s}
                  onChange={(e) =>
                    setOverlay({
                      duration_s: parseFloat(e.target.value) || 4,
                    })
                  }
                />
              </Field>
            </div>

            {/* Mini preview con la fuente REAL del registry */}
            <div className="mt-2 flex h-16 items-center justify-center rounded bg-gradient-to-br from-slate-800 to-slate-700 px-3">
              <span
                style={{
                  fontFamily: overlayFontFamily,
                  fontSize: `${Math.min(overlayStyle.size_px / 3, 28)}px`,
                  color: overlayStyle.color,
                  WebkitTextStroke: `${overlayStyle.stroke_width / 3}px ${overlayStyle.stroke_color}`,
                  textTransform: overlayStyle.uppercase ? "uppercase" : "none",
                  backgroundColor:
                    overlayStyle.background === "black_bar"
                      ? "rgba(0,0,0,0.7)"
                      : "transparent",
                  padding:
                    overlayStyle.background === "black_bar"
                      ? "2px 8px"
                      : "0",
                  fontWeight: "bold",
                }}
              >
                {preset.text_overlay || "Texto en pantalla"}
              </span>
            </div>
          </div>

          {/* Flecha animada que apunta al carrito de TikTok Shop (el
              naranjita que aparece abajo en la app). El sticker es un
              .mov con la flecha — negra o roja, NO naranja. */}
          <div className="space-y-2 rounded-md border border-fuchsia-500/30 bg-fuchsia-500/5 p-2">
            <div className="flex items-center justify-between">
              <strong className="text-[11px] text-fuchsia-700 dark:text-fuchsia-300">
                ➤ Flecha hacia el carrito de TikTok
              </strong>
              <label className="flex items-center gap-1.5 text-[11px]">
                <input
                  type="checkbox"
                  checked={arrowStyle.enabled}
                  onChange={(e) => setArrow({ enabled: e.target.checked })}
                  className="h-3.5 w-3.5"
                />
                Activa
              </label>
            </div>
            {arrowStyle.enabled && (
              <div className="grid grid-cols-2 gap-2">
                <Field label="Sticker de flecha">
                  <select
                    value={arrowStyle.sticker_file}
                    onChange={(e) =>
                      setArrow({ sticker_file: e.target.value })
                    }
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                  >
                    <option value="flecha_negra.mov">⬛ Negra (sutil)</option>
                    <option value="flecha_roja.mov">🟥 Roja (llama atención)</option>
                  </select>
                </Field>
                <Field label="Duración final (s)">
                  <Input
                    type="number"
                    step="0.5"
                    min={0.5}
                    max={10}
                    value={arrowStyle.duration_seconds}
                    onChange={(e) =>
                      setArrow({
                        duration_seconds: parseFloat(e.target.value) || 4,
                      })
                    }
                  />
                </Field>
                <Field label="Posición X (%)">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={arrowStyle.position_x_pct}
                    onChange={(e) =>
                      setArrow({
                        position_x_pct: parseFloat(e.target.value) || 50,
                      })
                    }
                  />
                </Field>
                <Field label="Posición Y (%)">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={arrowStyle.position_y_pct}
                    onChange={(e) =>
                      setArrow({
                        position_y_pct: parseFloat(e.target.value) || 75,
                      })
                    }
                  />
                </Field>
                <Field label="Escala ancho (%)">
                  <Input
                    type="number"
                    min={5}
                    max={60}
                    value={arrowStyle.scale_width_pct}
                    onChange={(e) =>
                      setArrow({
                        scale_width_pct: parseFloat(e.target.value) || 25,
                      })
                    }
                  />
                </Field>
                <Field label="Rotación (°)">
                  <Input
                    type="number"
                    min={-180}
                    max={180}
                    value={arrowStyle.rotation_deg}
                    onChange={(e) =>
                      setArrow({
                        rotation_deg: parseInt(e.target.value, 10) || 0,
                      })
                    }
                  />
                </Field>
                <div className="col-span-2 flex gap-3 text-[11px]">
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={arrowStyle.flip_horizontal}
                      onChange={(e) =>
                        setArrow({ flip_horizontal: e.target.checked })
                      }
                      className="h-3.5 w-3.5"
                    />
                    Flip horizontal
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={arrowStyle.flip_vertical}
                      onChange={(e) =>
                        setArrow({ flip_vertical: e.target.checked })
                      }
                      className="h-3.5 w-3.5"
                    />
                    Flip vertical
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={arrowStyle.show_at_end}
                      onChange={(e) =>
                        setArrow({ show_at_end: e.target.checked })
                      }
                      className="h-3.5 w-3.5"
                    />
                    Mostrar al final
                  </label>
                </div>
                <p className="col-span-2 text-[10px] text-muted-foreground">
                  Sticker animado .mov que aparece en los últimos{" "}
                  {arrowStyle.duration_seconds}s del vídeo apuntando hacia
                  abajo (donde TikTok muestra el botón naranja del carrito
                  para comprar). La flecha en sí es negra o roja, no naranja.
                </p>
              </div>
            )}
          </div>

          {/* Subtítulos karaoke — solo aplica si hay voz (scripted) */}
          {preset.kind === "scripted" && (
            <div className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-2">
              <div className="flex items-center justify-between">
                <strong className="text-[11px] text-amber-700 dark:text-amber-300">
                  💬 Subtítulos karaoke
                </strong>
                <label className="flex items-center gap-1.5 text-[11px]">
                  <input
                    type="checkbox"
                    checked={subStyle.enabled}
                    onChange={(e) => setSub({ enabled: e.target.checked })}
                    className="h-3.5 w-3.5"
                  />
                  Activos
                </label>
              </div>
              {subStyle.enabled && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Fuente">
                      <FontSelector
                        value={subStyle.font}
                        onChange={(p) => setSub({ font: p })}
                        allowUpload={false}
                      />
                    </Field>
                    <Field label="Posición">
                      <select
                        value={subStyle.position}
                        onChange={(e) => setSub({ position: e.target.value })}
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                      >
                        {TEXT_POSITIONS.map((p) => (
                          <option key={p} value={p}>
                            {p.replace("_", " ")}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Tamaño (px)">
                      <Input
                        type="number"
                        min={20}
                        max={120}
                        value={subStyle.size_px}
                        onChange={(e) =>
                          setSub({ size_px: parseInt(e.target.value, 10) })
                        }
                      />
                    </Field>
                    <Field label="Máx palabras / línea">
                      <Input
                        type="number"
                        min={1}
                        max={8}
                        value={subStyle.max_words_per_line}
                        onChange={(e) =>
                          setSub({
                            max_words_per_line: parseInt(e.target.value, 10),
                          })
                        }
                      />
                    </Field>
                    <Field label="Color texto">
                      <div className="flex gap-1">
                        <input
                          type="color"
                          value={subStyle.color}
                          onChange={(e) => setSub({ color: e.target.value })}
                          className="h-9 w-12 cursor-pointer rounded border border-input bg-transparent"
                        />
                        <Input
                          value={subStyle.color}
                          onChange={(e) => setSub({ color: e.target.value })}
                          className="flex-1 font-mono"
                        />
                      </div>
                    </Field>
                    <Field label="Palabra activa (karaoke)">
                      <div className="flex gap-1">
                        <input
                          type="color"
                          value={subStyle.highlight_color}
                          onChange={(e) =>
                            setSub({ highlight_color: e.target.value })
                          }
                          className="h-9 w-12 cursor-pointer rounded border border-input bg-transparent"
                        />
                        <Input
                          value={subStyle.highlight_color}
                          onChange={(e) =>
                            setSub({ highlight_color: e.target.value })
                          }
                          className="flex-1 font-mono"
                        />
                      </div>
                    </Field>
                    <Field label="Color contorno">
                      <div className="flex gap-1">
                        <input
                          type="color"
                          value={subStyle.stroke_color}
                          onChange={(e) =>
                            setSub({ stroke_color: e.target.value })
                          }
                          className="h-9 w-12 cursor-pointer rounded border border-input bg-transparent"
                        />
                        <Input
                          value={subStyle.stroke_color}
                          onChange={(e) =>
                            setSub({ stroke_color: e.target.value })
                          }
                          className="flex-1 font-mono"
                        />
                      </div>
                    </Field>
                    <Field label="Mayúsculas">
                      <label className="flex h-9 items-center gap-2 text-xs">
                        <input
                          type="checkbox"
                          checked={subStyle.uppercase}
                          onChange={(e) =>
                            setSub({ uppercase: e.target.checked })
                          }
                          className="h-4 w-4"
                        />
                        uppercase
                      </label>
                    </Field>
                  </div>
                  {/* Preview subs karaoke (palabra activa resaltada) */}
                  <div className="flex h-14 items-center justify-center rounded bg-gradient-to-br from-slate-800 to-slate-700 px-3">
                    <span
                      style={{
                        fontFamily: subFontFamily,
                        fontSize: `${Math.min(subStyle.size_px / 3, 26)}px`,
                        color: subStyle.color,
                        WebkitTextStroke: `${subStyle.stroke_width / 3}px ${subStyle.stroke_color}`,
                        textTransform: subStyle.uppercase ? "uppercase" : "none",
                        fontWeight: "bold",
                      }}
                    >
                      Mira{" "}
                      <span style={{ color: subStyle.highlight_color }}>
                        esto
                      </span>{" "}
                      ahora
                    </span>
                  </div>
                </>
              )}
            </div>
          )}

          <Field label="Seedance prompt (Standard / Advanced)">
            <Textarea
              rows={2}
              value={draft.seedance_prompt ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, seedance_prompt: e.target.value })
              }
            />
          </Field>
          <Field label="Veo 3 prompt">
            <Textarea
              rows={3}
              value={draft.veo3_prompt ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, veo3_prompt: e.target.value })
              }
            />
          </Field>

          <div className="flex gap-2 pt-2">
            <Button
              onClick={handleSave}
              disabled={updateMut.isPending}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700"
            >
              {updateMut.isPending ? (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              ) : (
                <Save className="mr-2 h-3 w-3" />
              )}
              Guardar
            </Button>
            <Button variant="ghost" onClick={onCancelEdit}>
              Cancelar
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card
      className={cn(
        "transition-colors",
        preset.kind === "music"
          ? "border-sky-500/30 hover:border-sky-500/60"
          : "border-violet-500/30 hover:border-violet-500/60",
      )}
    >
      <CardContent className="space-y-2 p-3 text-xs">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              {preset.kind === "music" ? (
                <Music className="h-3.5 w-3.5 shrink-0 text-sky-500" />
              ) : (
                <Mic className="h-3.5 w-3.5 shrink-0 text-violet-500" />
              )}
              <strong className="truncate text-sm">{preset.name}</strong>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              {preset.angle && (
                <Badge variant="secondary" className="text-[10px]">
                  {preset.angle}
                </Badge>
              )}
              {(() => {
                const meta = STYLE_LABEL[preset.style];
                if (!meta) return null;
                return (
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-medium",
                      meta.cls,
                    )}
                    title={meta.help}
                  >
                    {meta.label}
                  </span>
                );
              })()}
              <span className="text-[10px] text-muted-foreground">
                {preset.duration_s}s
              </span>
              <span
                className="text-[10px] text-cyan-700 dark:text-cyan-300"
                title={
                  preset.shot_style === "single_shot"
                    ? "1 plano continuo"
                    : preset.shot_style === "multi_shot"
                      ? "Cortes / cambios de plano"
                      : "Auto según duración"
                }
              >
                · {preset.shot_style === "single_shot"
                  ? "1 plano"
                  : preset.shot_style === "multi_shot"
                    ? "multi-plano"
                    : "auto-plano"}
              </span>
              {preset.music_mood && (
                <span className="text-[10px] text-muted-foreground">
                  · {preset.music_mood}
                </span>
              )}
            </div>
            {/* Línea de compatibilidad con los 4 tiers — tachado los no
                compatibles + tooltip explicando por qué. */}
            <div
              className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]"
              title={
                preset.style === "creator_pov"
                  ? "Creator POV requiere persona hablando → solo Pro y Veo 3"
                  : preset.duration_s > 10
                    ? "Duración > 10s → Veo 3 no aplica (límite nativo)"
                    : "Compatible con todos los tiers"
              }
            >
              {ALL_TIERS_ORDER.map((t) => {
                const ok = preset.compatible_tiers.includes(t);
                return (
                  <span
                    key={t}
                    className={cn(
                      "rounded px-1 py-0.5",
                      ok
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground/40 line-through",
                    )}
                  >
                    {TIER_EMOJI[t]} {TIER_NAME[t]}
                  </span>
                );
              })}
            </div>
          </div>
          <div className="flex shrink-0 gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={onEdit}
              className="h-6 w-6"
            >
              <Pencil className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDelete}
              disabled={deleteMut.isPending}
              className="h-6 w-6"
            >
              <Trash2 className="h-3 w-3 text-destructive" />
            </Button>
          </div>
        </div>

        {/* Resumen visible */}
        {preset.text_overlay && (
          <p className="rounded bg-muted/50 p-1.5 text-[11px] italic">
            “{preset.text_overlay}”
          </p>
        )}
        {preset.kind === "scripted" && preset.voice_script && (
          <p className="line-clamp-2 text-[11px] text-muted-foreground">
            {preset.voice_script}
          </p>
        )}

        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
        >
          {open ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          Detalles completos
        </button>

        {open && (
          <div className="space-y-2 border-t border-muted pt-2 text-[11px]">
            {preset.kind === "scripted" && (
              <>
                {preset.title && (
                  <Detail label="Título" value={preset.title} />
                )}
                {preset.hooks_alternatives.length > 0 && (
                  <div>
                    <span className="text-muted-foreground">
                      Hooks alternativos:
                    </span>
                    <ul className="ml-3 list-disc">
                      {preset.hooks_alternatives.map((h, i) => (
                        <li key={i}>{h}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {preset.voice_script && (
                  <Detail label="Guion" value={preset.voice_script} />
                )}
                {preset.cta && <Detail label="CTA" value={preset.cta} />}
                {preset.oratory_tips && (
                  <Detail label="Oratory tips" value={preset.oratory_tips} />
                )}
                {preset.keywords.length > 0 && (
                  <Detail
                    label="Keywords"
                    value={preset.keywords.join(", ")}
                  />
                )}
              </>
            )}
            {preset.seedance_prompt && (
              <Detail
                label="Seedance prompt (Standard/Advanced)"
                value={preset.seedance_prompt}
                mono
              />
            )}
            {preset.veo3_prompt && (
              <Detail label="Veo 3 prompt" value={preset.veo3_prompt} mono />
            )}
            <p className="pt-1 text-[10px] text-muted-foreground">
              Source:{" "}
              <span className="font-mono">{preset.source}</span>
              {preset.notes && ` · Notas: ${preset.notes}`}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-[11px] text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

function Detail({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <span className="text-muted-foreground">{label}:</span>{" "}
      <span className={mono ? "font-mono text-[10px]" : ""}>{value}</span>
    </div>
  );
}
