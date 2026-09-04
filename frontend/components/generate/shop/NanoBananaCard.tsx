"use client";

import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  FlaskConical,
  Loader2,
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
import { api, ApiError } from "@/lib/api";
import { usePreviewNanoBananaPrompt } from "@/lib/queries/generations";
import { useProduct } from "@/lib/queries/products";
import { cn } from "@/lib/utils";

import { PresetControls } from "./PresetControls";

/** Nano Banana NO usa VideoPresets (es generación de fotos, no vídeo).
 *  Modos consistentes con AutoVideoCard / Veo3Card:
 *  - `single`   → 1 prompt para N ángulos
 *  - `variants` → N prompts en paralelo (reinvoca Gemini N veces con
 *                 misma config, sale prompt textualmente distinto en
 *                 cada uno = mini A/B de versiones).
 *  (`batch` no aplica — no hay multi-select de presets aquí.)
 */
type GenMode = "single" | "variants";

const MODE_META: Record<
  GenMode,
  { label: string; subtitle: string; icon: typeof Target; cls: string }
> = {
  single: {
    label: "1 prompt",
    subtitle: "N ángulos en 1 prompt",
    icon: Target,
    cls: "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  variants: {
    label: "Variantes",
    subtitle: "N prompts distintos (A/B)",
    icon: FlaskConical,
    cls: "border-violet-500 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
};

const USE_CASE_OPTIONS = [
  "packshot",
  "lifestyle",
  "macro",
  "in_hand",
  "outdoor",
  "studio",
];

interface NanoBananaConfig {
  n_angles: number;
  use_cases: string[];
}

const DEFAULT_CONFIG: NanoBananaConfig = {
  n_angles: 5,
  use_cases: ["packshot", "lifestyle", "macro"],
};

interface Props {
  userId: string;
  username: string;
  productId: string;
  hideTitle?: boolean;
}

interface ResultItem {
  prompt: string;
  index: number;
}

export function NanoBananaCard({
  userId,
  username,
  productId,
  hideTitle,
}: Props) {
  const product = useProduct(productId);
  const preview = usePreviewNanoBananaPrompt();

  const [mode, setMode] = useState<GenMode>("single");
  const [config, setConfig] = useState<NanoBananaConfig>(DEFAULT_CONFIG);
  const [variantsN, setVariantsN] = useState(3);
  const [expanded, setExpanded] = useState(false);
  const [selectedSavedName, setSelectedSavedName] = useState<string>("");

  const [results, setResults] = useState<ResultItem[] | null>(null);
  const [resultsTitle, setResultsTitle] = useState<string>("");

  // Source photos del producto — disponibles para descarga junto al prompt.
  const sourcePhotos = useMemo(
    () =>
      (product.data?.photos.source ?? []).filter((p) => !p.deleted),
    [product.data],
  );

  function applyConfig(cfg: Record<string, unknown>) {
    setConfig((prev) => ({ ...prev, ...(cfg as Partial<NanoBananaConfig>) }));
  }

  function toggleUseCase(uc: string) {
    setConfig((c) =>
      c.use_cases.includes(uc)
        ? { ...c, use_cases: c.use_cases.filter((x) => x !== uc) }
        : { ...c, use_cases: [...c.use_cases, uc] },
    );
  }

  async function handleSubmit() {
    if (config.use_cases.length === 0) {
      toast.error("Marca al menos 1 estilo");
      return;
    }
    const count = mode === "variants" ? variantsN : 1;
    try {
      toast(`Generando ${count} prompt(s)…`);
      // Llamadas en paralelo. Gemini con temperature alta devuelve
      // prompts textualmente distintos en cada llamada con la misma
      // config → buen pool de A/B.
      const calls = Array.from({ length: count }).map(() =>
        preview.mutateAsync({
          username,
          product_id: productId,
          n_angles: config.n_angles,
          use_cases: config.use_cases,
        }),
      );
      const responses = await Promise.all(calls);
      setResults(responses.map((r, i) => ({ prompt: r.prompt, index: i })));
      setResultsTitle(
        count === 1
          ? "🍌 Prompt Nano Banana listo"
          : `🍌 ${count} variantes Nano Banana`,
      );
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : "Error generando prompt Nano Banana.",
      );
    }
  }

  return (
    <>
      <Card>
        <CardContent className="space-y-3 p-4 sm:p-5">
          {!hideTitle && (
            <div>
              <p className="text-lg font-semibold">🍌 Prompt Nano Banana</p>
              <p className="text-xs text-muted-foreground">
                Genera prompt(s) para pedirle a Gemini fotos premium del
                producto. Cópialo, pégalo en Gemini chat + las fotos source
                del producto, y sube las generadas en Photos generated.
                Coste ~$0.002 / prompt (Gemini 2.5 Flash).
              </p>
            </div>
          )}

          {/* PASO 1 · Modo */}
          <div className="space-y-1.5">
            <Label className="text-xs">1 · ¿Qué quieres generar?</Label>
            <div className="grid grid-cols-2 gap-1.5">
              {(["single", "variants"] as GenMode[]).map((m) => {
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

          {/* PASO 2 · Config inline (visible siempre) */}
          <div className="space-y-2 rounded-md border border-muted bg-muted/20 p-2">
            <Label className="text-xs">2 · Configuración</Label>
            <div className="flex flex-wrap items-center gap-2">
              <Label className="text-[11px] text-muted-foreground" htmlFor="nb-n-angles">
                Ángulos
              </Label>
              <Input
                id="nb-n-angles"
                type="number"
                min={3}
                max={10}
                value={config.n_angles}
                onChange={(e) =>
                  setConfig((c) => ({
                    ...c,
                    n_angles: Math.max(3, Math.min(10, parseInt(e.target.value) || 5)),
                  }))
                }
                className="h-7 w-16 text-xs"
              />
              {mode === "variants" && (
                <>
                  <Label
                    className="ml-2 text-[11px] text-muted-foreground"
                    htmlFor="nb-variants-n"
                  >
                    Variantes
                  </Label>
                  <Input
                    id="nb-variants-n"
                    type="number"
                    min={2}
                    max={6}
                    value={variantsN}
                    onChange={(e) =>
                      setVariantsN(
                        Math.max(2, Math.min(6, parseInt(e.target.value) || 2)),
                      )
                    }
                    className="h-7 w-16 text-xs"
                  />
                </>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] text-muted-foreground">
                Estilos a pedir
              </Label>
              <div className="flex flex-wrap gap-1">
                {USE_CASE_OPTIONS.map((uc) => {
                  const active = config.use_cases.includes(uc);
                  return (
                    <button
                      key={uc}
                      type="button"
                      onClick={() => toggleUseCase(uc)}
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                        active
                          ? "border-amber-500 bg-amber-500/15 text-amber-700 dark:text-amber-300"
                          : "border-border text-muted-foreground hover:border-muted-foreground/50",
                      )}
                    >
                      {uc}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Acción principal */}
          <div className="flex flex-wrap items-center gap-2">
            {mode === "single" ? (
              <Button
                onClick={handleSubmit}
                disabled={preview.isPending || config.use_cases.length === 0}
                className="flex-1 bg-emerald-600 hover:bg-emerald-700"
              >
                {preview.isPending ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-1.5 h-4 w-4" />
                )}
                Generar prompt
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={preview.isPending || config.use_cases.length === 0}
                className="flex-1 bg-violet-600 hover:bg-violet-700"
              >
                {preview.isPending ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <FlaskConical className="mr-1.5 h-4 w-4" />
                )}
                Generar {variantsN} variantes
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
            <div className="space-y-2 border-t pt-3">
              <p className="text-[10px] text-muted-foreground">
                Configuraciones guardadas (legacy):
              </p>
              <PresetControls
                userId={userId}
                productId={productId}
                kind="nano_banana"
                selectedName={selectedSavedName}
                onSelectName={setSelectedSavedName}
                currentConfig={config as unknown as Record<string, unknown>}
                onLoadConfig={applyConfig}
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
              Para cada prompt: <strong>cópialo</strong> y{" "}
              <strong>descarga las fotos source</strong>. Pega ambas cosas
              en Gemini chat. Sube las imágenes que te devuelva en{" "}
              <strong>Photos generated</strong> del producto.
            </DialogDescription>
          </DialogHeader>

          {/* Botón global para descargar todas las fotos source una sola
              vez (sirven para todos los prompts del lote). */}
          {sourcePhotos.length > 0 && (
            <div className="flex items-center justify-between rounded-md border border-amber-500/30 bg-amber-500/5 p-2">
              <p className="text-xs">
                📎 Fotos source disponibles:{" "}
                <strong>{sourcePhotos.length}</strong>
              </p>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2 text-[11px]"
                onClick={() =>
                  downloadAllSourcePhotos(
                    productId,
                    sourcePhotos.map((p) => p.filename),
                  )
                }
              >
                <Download className="h-3 w-3" />
                Descargar todas las fotos source
              </Button>
            </div>
          )}

          <div className="space-y-3">
            {results?.map((r) => (
              <PromptResultCard key={r.index} item={r} />
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
function PromptResultCard({ item }: { item: ResultItem }) {
  async function copyPrompt() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(item.prompt);
      } else {
        const ta = document.createElement("textarea");
        ta.value = item.prompt;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      toast.success(`Prompt #${item.index + 1} copiado`);
    } catch {
      toast.error("No pude copiar");
    }
  }

  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <strong className="text-sm">Prompt #{item.index + 1}</strong>
        <Button
          size="sm"
          variant="outline"
          className="h-6 gap-1 px-2 text-[10px]"
          onClick={copyPrompt}
        >
          <Copy className="h-3 w-3" />
          Copiar
        </Button>
      </div>
      <Textarea
        readOnly
        value={item.prompt}
        className="min-h-[180px] font-mono text-[10px]"
        onFocus={(e) => e.currentTarget.select()}
      />
    </div>
  );
}

// =============================================================
function buildPhotoUrl(productId: string, filename: string): string | null {
  if (!productId || !filename) return null;
  const base = api.baseUrl;
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}/api/v1/products/${productId}/photos/${encodeURIComponent(filename)}/file${qs}`;
}

async function downloadAllSourcePhotos(
  productId: string,
  filenames: string[],
): Promise<void> {
  if (filenames.length === 0) return;
  toast.info(`Descargando ${filenames.length} foto(s)…`);
  for (let i = 0; i < filenames.length; i++) {
    const fn = filenames[i];
    if (!fn) continue;
    const url = buildPhotoUrl(productId, fn);
    if (!url) continue;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = fn;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (e) {
      toast.error(
        e instanceof Error ? `Descarga falló (${fn})` : "Descarga falló",
      );
    }
    if (i < filenames.length - 1) {
      await new Promise((r) => setTimeout(r, 250));
    }
  }
  toast.success(`Descargadas ${filenames.length} foto(s)`);
}
