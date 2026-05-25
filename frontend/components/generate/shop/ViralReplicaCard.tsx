"use client";

import { useState } from "react";
import { Copy, Loader2, Upload, Wand2 } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  type ReplicateViralResponse,
  type ShopPresetKind,
  useReplicateViral,
  useSaveShopPreset,
} from "@/lib/queries/shopPresets";
import { useSaveViralVideoPreset } from "@/lib/queries/products";

interface Props {
  userId: string;
  productId: string;
  hideTitle?: boolean;
}

const PRESETS_MODEL: { label: string; value: string; note: string }[] = [
  { label: "Flash 3.5 · recomendado (~$0.018)", value: "gemini-3.5-flash", note: "más preciso con transiciones/overlays — default" },
  { label: "Flash 2.5 · barato (~$0.004)", value: "gemini-2.5-flash", note: "suficiente para clasificación básica" },
  { label: "Pro 2.5 · razonamiento (~$0.017)", value: "gemini-2.5-pro", note: "raramente necesario" },
];

export function ViralReplicaCard({ userId, productId, hideTitle }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [targetKind, setTargetKind] = useState<ShopPresetKind>("auto_video");
  const [model, setModel] = useState<string>("gemini-3.5-flash");
  const [customModel, setCustomModel] = useState<string>("");
  const [result, setResult] = useState<ReplicateViralResponse | null>(null);
  const [presetName, setPresetName] = useState<string>("");

  const replicate = useReplicateViral();
  const save = useSaveShopPreset(userId, productId, targetKind);
  const saveAsVideoPreset = useSaveViralVideoPreset(productId);

  function pickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
  }

  async function analyze() {
    if (!file) {
      toast.error("Sube un vídeo primero.");
      return;
    }
    try {
      const effectiveModel = customModel.trim() || model;
      const res = await replicate.mutateAsync({
        file,
        user_id: userId,
        product_id: productId,
        target_kind: targetKind,
        // Implícitamente true: el usuario está dentro del contexto user×product,
        // así que cualquier vídeo que suba es para ese producto.
        same_product: true,
        gemini_model: effectiveModel,
      });
      setResult(res);
      // Sugerencia de nombre: priorizamos el name que ya generó Gemini
      // ("Réplica · Hook Dolor 30s"), que es legible. Si no existe
      // (modos legacy auto_video/nano_banana sin video_preset), caemos
      // al stem del filename como fallback.
      const geminiName = (res.video_preset as { name?: string } | null)?.name;
      if (geminiName && geminiName.trim()) {
        setPresetName(geminiName.trim());
      } else {
        const stem = file.name.replace(/\.[^.]+$/, "").slice(0, 40);
        setPresetName(`viral_${stem}`);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error analizando el vídeo.");
    }
  }

  async function savePreset() {
    if (!result || !presetName.trim()) {
      toast.error("Elige un nombre para el preset.");
      return;
    }
    // Para auto_video / veo3 + si el backend devolvió `video_preset` (formato
    // nuevo con prompts Seedance/Veo3, fotos, overlays), lo guardamos como
    // VideoPreset en el producto — aparece en el grid de presets junto a
    // los autogen. Para nano_banana (o si no hay video_preset) caemos al
    // sistema legacy de configuraciones guardadas.
    const useNewFormat =
      (targetKind === "auto_video" || targetKind === "veo3") &&
      result.video_preset !== null &&
      result.video_preset !== undefined;
    try {
      if (useNewFormat) {
        const payload = {
          ...(result.video_preset as Record<string, unknown>),
          name: presetName.trim(),
        };
        await saveAsVideoPreset.mutateAsync(payload);
        toast.success(
          `Preset '${presetName.trim()}' añadido a los presets del producto. ` +
            `Ya puedes usarlo en /tiktok-shop/generate.`,
        );
      } else {
        await save.mutateAsync({
          name: presetName.trim(),
          config: result.config,
        });
        toast.success(
          `Preset '${presetName.trim()}' guardado en modo ${targetKind}.`,
        );
      }
      setResult(null);
      setFile(null);
      setPresetName("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error guardando preset.");
    }
  }

  return (
    <>
      <Card>
        <CardContent className="space-y-3 p-4 sm:p-5">
          {!hideTitle && (
            <div>
              <p className="text-lg font-semibold">🎯 Replicar viral</p>
              <p className="text-xs text-muted-foreground">
                Sube un vídeo que funciona y la IA detecta la "receta" (hook, tier,
                estrategia, overlays). Se guarda como preset reutilizable.
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label className="text-xs">Vídeo viral (.mp4, máx 500 MB)</Label>
            <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed bg-muted/30 p-3 hover:bg-muted/50">
              <Upload className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate text-xs">
                {file ? file.name : "Click para seleccionar vídeo…"}
              </span>
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/x-matroska,video/webm"
                onChange={pickFile}
                className="hidden"
              />
            </label>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Modo objetivo del preset</Label>
            <Select value={targetKind} onValueChange={(v) => setTargetKind(v as ShopPresetKind)}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="auto_video">🎬 Auto vídeo</SelectItem>
                <SelectItem value="veo3">🟣 Veo 3 prompt</SelectItem>
                <SelectItem value="nano_banana">🍌 Nano Banana prompt</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 rounded-md border border-purple-500/30 bg-purple-500/5 p-3">
            <Label className="text-xs">Modelo Gemini</Label>
            <Select value={model} onValueChange={setModel} disabled={Boolean(customModel.trim())}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PRESETS_MODEL.map((m) => (
                  <SelectItem key={m.value} value={m.value}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              value={customModel}
              onChange={(e) => setCustomModel(e.target.value)}
              placeholder="O escribe un model ID custom (ej. gemini-3.1-flash-lite-preview)"
              className="h-8 font-mono text-xs"
            />
            <p className="text-[10px] text-muted-foreground">
              Coste estimado por vídeo: ver columna entre paréntesis. Whisper es local (gratis).
            </p>
          </div>

          <Button onClick={analyze} disabled={!file || replicate.isPending} className="w-full">
            {replicate.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Wand2 className="h-4 w-4" />
            )}
            {replicate.isPending ? "Analizando vídeo (10-30s)…" : "Analizar y detectar preset"}
          </Button>
        </CardContent>
      </Card>

      <Dialog open={result !== null} onOpenChange={(o) => !o && setResult(null)}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>🎯 Receta detectada</DialogTitle>
            <DialogDescription>
              La IA extrajo estos parámetros del vídeo. Revisa, ponle nombre y
              guarda como preset reutilizable en el modo {targetKind}.
            </DialogDescription>
          </DialogHeader>

          {result && (
            <div className="space-y-3">
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <p className="mb-2 font-semibold uppercase tracking-wider text-muted-foreground">
                  Detección
                </p>
                <DetectionGrid detected={result.detected} />
              </div>

              {/* Si target es auto_video / veo3 → mostramos el VideoPreset
                  completo que se va a persistir (con prompts + fotos). */}
              {(targetKind === "auto_video" || targetKind === "veo3") &&
              result.video_preset ? (
                <VideoPresetPreview
                  videoPreset={result.video_preset}
                  productId={productId}
                />
              ) : (
                <div className="rounded-md border bg-muted/30 p-3 text-xs">
                  <p className="mb-2 font-semibold uppercase tracking-wider text-muted-foreground">
                    Config preset (lo que se va a guardar)
                  </p>
                  <pre className="overflow-auto whitespace-pre-wrap break-words text-[10px]">
                    {JSON.stringify(result.config, null, 2)}
                  </pre>
                </div>
              )}

              <div className="flex items-center justify-between rounded-md border border-emerald-500/30 bg-emerald-500/5 p-2 text-xs">
                <span>Coste real del análisis</span>
                <span className="font-mono font-medium">
                  ${result.cost_breakdown.total_usd.toFixed(4)} · {result.cost_breakdown.gemini_model}
                </span>
              </div>

              <div className="space-y-1 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-2">
                <Label className="text-xs font-semibold">
                  ✏️ Nombre del preset (editable)
                </Label>
                <Input
                  value={presetName}
                  onChange={(e) => setPresetName(e.target.value)}
                  onFocus={(e) => e.currentTarget.select()}
                  placeholder="ej. Curviva · pezoneras vestido 30s"
                  className="font-medium"
                />
                <p className="text-[10px] text-muted-foreground">
                  Sugerencia auto-generada por Gemini — click para
                  reescribirlo a tu gusto. Se guardará así en /tiktok-shop/generate.
                </p>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setResult(null)}>
              Cerrar
            </Button>
            <Button onClick={savePreset} disabled={!presetName.trim() || save.isPending}>
              {save.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wand2 className="h-4 w-4" />
              )}
              Guardar como preset
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function VideoPresetPreview({
  videoPreset,
  productId,
}: {
  videoPreset: Record<string, unknown>;
  productId: string;
}) {
  const vp = videoPreset as {
    name?: string;
    kind?: string;
    angle?: string;
    style?: string;
    duration_s?: number;
    compatible_tiers?: string[];
    text_overlay?: string;
    voice_script?: string;
    seedance_prompt?: string;
    veo3_prompt?: string;
    veo3_prompt_segments?: string[];
    veo3_photo_filenames?: string[];
  };
  const photos = vp.veo3_photo_filenames ?? [];
  const segments = vp.veo3_prompt_segments ?? [];
  const hasSegments = segments.length > 0;
  async function copyText(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copiado al portapapeles.`);
    } catch {
      toast.error("No se pudo copiar (revisa permisos del navegador).");
    }
  }
  return (
    <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs">
      <p className="mb-2 font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
        🎯 VideoPreset completo (se guarda en el producto)
      </p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <div className="flex justify-between border-b border-dashed py-0.5">
          <span className="text-muted-foreground">Kind</span>
          <strong>
            {vp.kind === "music" ? "🎵 Música (sin voz)" : "🎤 Scripted"}
          </strong>
        </div>
        <div className="flex justify-between border-b border-dashed py-0.5">
          <span className="text-muted-foreground">Ángulo</span>
          <strong>{vp.angle || "—"}</strong>
        </div>
        <div className="flex justify-between border-b border-dashed py-0.5">
          <span className="text-muted-foreground">Estilo</span>
          <strong>{vp.style}</strong>
        </div>
        <div className="flex justify-between border-b border-dashed py-0.5">
          <span className="text-muted-foreground">Duración</span>
          <strong>{vp.duration_s}s</strong>
        </div>
        <div className="col-span-full flex justify-between border-b border-dashed py-0.5">
          <span className="text-muted-foreground">Tiers compatibles</span>
          <strong>{(vp.compatible_tiers ?? []).join(" · ")}</strong>
        </div>
      </div>

      {vp.text_overlay && (
        <p className="mt-2 rounded bg-muted/50 p-1.5 text-[11px] italic">
          Hook en pantalla: &ldquo;{vp.text_overlay}&rdquo;
        </p>
      )}
      {vp.voice_script && (
        <div className="mt-1.5">
          <p className="text-[10px] text-muted-foreground">Guion adaptado:</p>
          <p className="rounded bg-muted/30 p-1.5 text-[10px]">{vp.voice_script}</p>
        </div>
      )}
      {vp.seedance_prompt && (
        <div className="mt-1.5">
          <p className="text-[10px] text-muted-foreground">
            Seedance prompt (Std/Adv/Pro):
          </p>
          <p className="rounded bg-muted/30 p-1.5 font-mono text-[10px]">
            {vp.seedance_prompt}
          </p>
        </div>
      )}
      {hasSegments ? (
        <div className="mt-2 space-y-1.5 rounded border border-purple-500/30 bg-purple-500/5 p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-purple-700 dark:text-purple-300">
            🟣 Veo 3 prompt · {segments.length} segmentos para Flow Gemini
          </p>
          <p className="text-[10px] text-muted-foreground">
            Pega cada uno en orden en Flow Gemini — cada clip dura ~8-10s
            y mantiene continuidad con el anterior. Total ≈ {vp.duration_s ?? segments.length * 10}s.
          </p>
          {segments.map((seg, i) => (
            <div
              key={i}
              className="rounded bg-muted/30 p-1.5"
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] font-semibold text-purple-700 dark:text-purple-300">
                  Segmento {i + 1} / {segments.length}
                </span>
                <button
                  type="button"
                  onClick={() => copyText(seg, `Segmento ${i + 1}`)}
                  className="flex items-center gap-1 rounded bg-purple-500/20 px-1.5 py-0.5 text-[9px] font-medium text-purple-700 hover:bg-purple-500/30 dark:text-purple-300"
                >
                  <Copy className="h-2.5 w-2.5" />
                  Copiar
                </button>
              </div>
              <p className="whitespace-pre-wrap font-mono text-[10px] leading-snug">
                {seg}
              </p>
            </div>
          ))}
        </div>
      ) : (
        vp.veo3_prompt && (
          <div className="mt-1.5">
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-muted-foreground">
                Veo 3 prompt (clip único ~8-10s):
              </p>
              <button
                type="button"
                onClick={() => copyText(vp.veo3_prompt ?? "", "Veo 3 prompt")}
                className="flex items-center gap-1 rounded bg-muted/50 px-1.5 py-0.5 text-[9px] font-medium hover:bg-muted"
              >
                <Copy className="h-2.5 w-2.5" />
                Copiar
              </button>
            </div>
            <p className="rounded bg-muted/30 p-1.5 font-mono text-[10px]">
              {vp.veo3_prompt}
            </p>
          </div>
        )
      )}
      {photos.length > 0 && (
        <div className="mt-1.5 rounded border border-violet-500/30 bg-violet-500/5 p-1.5">
          <p className="text-[10px] text-violet-700 dark:text-violet-300">
            📎 Fotos elegidas para Veo 3 ({photos.length}):
          </p>
          <ul className="ml-3 list-disc text-[10px]">
            {photos.map((fn) => (
              <li key={fn}>{fn}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-2 text-[10px] italic text-muted-foreground">
        Al guardar, este preset aparecerá en /tiktok-shop/generate (tab
        Auto vídeo / Veo 3) listo para encolar — formato idéntico a los
        autogenerados.
      </p>
    </div>
  );
}

function DetectionGrid({ detected }: { detected: Record<string, unknown> }) {
  const fields: { key: string; label: string }[] = [
    { key: "hook_category", label: "Hook categoría" },
    { key: "hook_text", label: "Hook texto" },
    { key: "target_audience", label: "Audiencia" },
    { key: "tier_recommendation", label: "Tier recomendado" },
    { key: "strategy_recommendation", label: "Estrategia" },
    { key: "duration_seconds_recommendation", label: "Duración" },
    { key: "camera_style", label: "Estilo cámara" },
    { key: "n_distinct_shots", label: "Nº shots" },
    { key: "human_presence", label: "Humano en cámara" },
    { key: "has_text_hook_at_start", label: "Hook text inicio" },
    { key: "has_cta_arrow_at_end", label: "CTA flecha final" },
    { key: "shoppable_signals", label: "Shoppable" },
  ];
  return (
    <div className="grid gap-x-3 gap-y-1 sm:grid-cols-2">
      {fields.map((f) => {
        const v = detected[f.key];
        if (v === undefined || v === null || v === "") return null;
        let display: string;
        if (typeof v === "boolean") display = v ? "Sí" : "No";
        else if (Array.isArray(v)) display = v.join(", ");
        else display = String(v);
        return (
          <div key={f.key} className="flex items-start justify-between gap-2 border-b border-dashed py-0.5">
            <span className="text-muted-foreground">{f.label}</span>
            <span className="text-right font-medium">{display}</span>
          </div>
        );
      })}
      {Array.isArray(detected.color_palette) && (
        <div className="col-span-full flex items-center gap-2 pt-1">
          <span className="text-muted-foreground">Paleta:</span>
          {(detected.color_palette as string[]).slice(0, 6).map((c, i) => (
            <span
              key={i}
              className="inline-block h-4 w-4 rounded border"
              style={{ backgroundColor: c }}
              title={c}
            />
          ))}
        </div>
      )}
      {typeof detected.notes === "string" && detected.notes && (
        <div className="col-span-full mt-2 rounded bg-muted/50 p-2 text-[11px] italic">
          "{detected.notes}"
        </div>
      )}
    </div>
  );
}
