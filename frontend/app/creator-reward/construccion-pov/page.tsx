"use client";

import { useEffect, useMemo, useState } from "react";
import { Copy, FileText, FlipHorizontal2, HardHat, Loader2, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { VideoUploader } from "@/components/creator-reward/copyright/VideoUploader";
import { VoicePicker } from "@/components/creator-reward/construccion-pov/VoicePicker";
import { PovPresetManager } from "@/components/creator-reward/construccion-pov/PovPresetManager";
import { SubsAutoStyleEditor } from "@/components/creator-reward/subs-auto/SubsAutoStyleEditor";
import { Button } from "@/components/ui/button";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/lib/api";
import {
  useConstruccionPovPreset,
  useEnqueueConstruccionPov,
  usePovPromptPreview,
} from "@/lib/queries/creator-reward/construccionPov";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useFontByPath, useFontFamily, useFonts } from "@/lib/queries/fonts";
import { useLocalStorageState } from "@/lib/hooks/useLocalStorageState";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { SubsAutoStyleConfig } from "@/lib/types/creator-reward";
import { cn } from "@/lib/utils";

const DEFAULT_STYLE: SubsAutoStyleConfig = {
  font_path: "",
  highlight_mode: "pill",
  highlight_color: "#FDD002",
  text_color: "#FFFFFF",
  stroke_color: "#000000",
  stroke_width: 4,
  case_mode: "UPPERCASE",
  font_scale: 0.085,
  max_words: 3,
  y_position: 0.78,
  pill_enabled: true,
  max_width: 0.85,
  sync_offset: 0,
};

const QUALITY_OPTIONS = [
  "1080p (Lento)",
  "720p (Medio)",
  "480p (Rápido)",
] as const;

const WHISPER_MODELS = ["small", "medium", "large-v3"] as const;

export default function ConstruccionPovPage() {
  const enqueue = useEnqueueConstruccionPov();
  const openQueue = useDrawerStore((s) => s.openQueue);
  const fonts = useFonts();

  const [file, setFile] = useState<File | null>(null);
  const [voiceId, setVoiceId] = useState<string>("");
  const [style, setStyle] = useState<SubsAutoStyleConfig>(DEFAULT_STYLE);
  const [upscale, setUpscale] = useState(true);
  const [saturation, setSaturation] = useState(1.25);
  const [pulseZoom, setPulseZoom] = useState(true);
  const [mirror, setMirror] = useState(false);
  const [whisperModel, setWhisperModel] = useState<string>("small");
  const [quality, setQuality] = useState<string>("1080p (Lento)");
  const [geminiModel, setGeminiModel] = useState<"gemini-2.5-flash" | "gemini-2.5-pro">(
    "gemini-2.5-pro",
  );
  const [manualScript, setManualScript] = useState<string>("");
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  const [videoDuration, setVideoDuration] = useState<number>(60);

  // Snapshot serializable de TODA la config — se persiste como preset.
  // NOTA: NO incluimos `manual_script` aquí porque el guion es per-video
  // y no tiene sentido reusarlo entre proyectos distintos.
  const currentConfig = useMemo(
    () => ({
      voice_id: voiceId,
      style,
      upscale,
      saturation,
      pulse_zoom: pulseZoom,
      mirror,
      whisper_model: whisperModel,
      quality,
      gemini_model: geminiModel,
    }),
    [
      voiceId, style, upscale, saturation, pulseZoom, mirror,
      whisperModel, quality, geminiModel,
    ],
  );

  // Prompt preview — calibrado a la duración real del vídeo subido.
  const promptPreview = usePovPromptPreview(videoDuration, promptModalOpen);

  function probeVideoDuration(f: File) {
    const url = URL.createObjectURL(f);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = url;
    video.onloadedmetadata = () => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        setVideoDuration(Math.round(video.duration));
      }
      URL.revokeObjectURL(url);
    };
    video.onerror = () => URL.revokeObjectURL(url);
  }

  function handleFileChange(f: File | null) {
    setFile(f);
    if (f) probeVideoDuration(f);
  }

  async function copyPrompt() {
    if (!promptPreview.data) return;
    try {
      await navigator.clipboard.writeText(promptPreview.data.system_prompt);
      toast.success("Prompt copiado.");
    } catch {
      toast.error("No se pudo copiar — selecciónalo manualmente.");
    }
  }

  function applyConfig(cfg: Record<string, unknown>) {
    if (typeof cfg.voice_id === "string") setVoiceId(cfg.voice_id);
    if (cfg.style && typeof cfg.style === "object") {
      setStyle((prev) => ({ ...prev, ...(cfg.style as Partial<SubsAutoStyleConfig>) }));
    }
    if (typeof cfg.upscale === "boolean") setUpscale(cfg.upscale);
    if (typeof cfg.saturation === "number") setSaturation(cfg.saturation);
    if (typeof cfg.pulse_zoom === "boolean") setPulseZoom(cfg.pulse_zoom);
    if (typeof cfg.mirror === "boolean") setMirror(cfg.mirror);
    if (typeof cfg.whisper_model === "string") setWhisperModel(cfg.whisper_model);
    if (typeof cfg.quality === "string") setQuality(cfg.quality);
    if (cfg.gemini_model === "gemini-2.5-flash" || cfg.gemini_model === "gemini-2.5-pro") {
      setGeminiModel(cfg.gemini_model);
    }
  }

  // Auto-carga del preset `__default` en la primera visita del navegador.
  // El flag `pov.bootstrapped.v1` evita que sobrescriba ediciones del usuario
  // tras editar y volver — mismo patrón que Presidentes.
  const [bootstrapped, setBootstrapped] = useLocalStorageState(
    "pov.bootstrapped.v1",
    false,
  );
  const defaultPreset = useConstruccionPovPreset(bootstrapped ? null : "__default");
  useEffect(() => {
    if (!bootstrapped && defaultPreset.data) {
      applyConfig(defaultPreset.data.config);
      setBootstrapped(true);
    }
    // Marca como bootstrapped también si el fetch terminó sin __default
    // (404 → query.isError true) para no quedarnos pegados.
    if (!bootstrapped && defaultPreset.isError) {
      setBootstrapped(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrapped, defaultPreset.data, defaultPreset.isError]);

  // Cuando carguen las fuentes, fija una default Impact-style si no hay nada.
  useEffect(() => {
    const list = fonts.data?.items ?? [];
    if (!style.font_path && list.length > 0) {
      const impact = list.find((f) => /impact|anton|bebas/i.test(f.name));
      setStyle((s) => ({ ...s, font_path: (impact ?? list[0])!.path }));
    }
  }, [fonts.data, style.font_path]);

  const selectedFont = useFontByPath(style.font_path);
  const previewFontFamily = useFontFamily(selectedFont);

  const previewUrl = useMemo(
    () => (file ? URL.createObjectURL(file) : null),
    [file],
  );
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  async function submit() {
    if (!file) {
      toast.error("Sube primero un vídeo.");
      return;
    }
    if (!voiceId) {
      toast.error("Elige una voz.");
      return;
    }
    if (!style.font_path) {
      toast.error("Elige una fuente para los subtítulos.");
      return;
    }
    try {
      const res = await enqueue.mutateAsync({
        file,
        voice_id: voiceId,
        font_path: style.font_path,
        highlight_mode: style.highlight_mode,
        highlight_color: style.highlight_color,
        text_color: style.text_color,
        stroke_color: style.stroke_color,
        stroke_width: style.stroke_width,
        case_mode: style.case_mode,
        font_scale: style.font_scale,
        max_words: style.max_words,
        y_position: style.y_position,
        pill_enabled: style.pill_enabled,
        max_width: style.max_width,
        sync_offset: style.sync_offset,
        upscale_1080p: upscale,
        saturation,
        pulse_zoom: pulseZoom,
        mirror,
        whisper_model_size: whisperModel,
        quality_label: quality,
        gemini_model: geminiModel,
        manual_script: manualScript.trim() ? manualScript : null,
      });
      toast.success(`Encolado · job ${res.job_id.slice(0, 8)}`);
      openQueue();
      setFile(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Error al encolar.");
    }
  }

  return (
    <div className="container mx-auto space-y-4 p-4 sm:p-6 md:p-8">
      <header className="flex flex-wrap items-center gap-2">
        <HardHat className="h-6 w-6 shrink-0 text-amber-500" />
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold tracking-tight">Construcción POV</h1>
          <p className="text-sm text-muted-foreground">
            Vídeo input → guion 1ª persona (Gemini) → voz MiniMax EN → anti-copy
            + subs karaoke.
          </p>
        </div>
      </header>

      <CollapsibleCard
        title="Favoritos · presets"
        subtitle="Guarda la config completa (voz + subs + anti-copy). La marcada con ⭐ se autocarga."
        defaultOpen={false}
      >
        <PovPresetManager config={currentConfig} onLoad={applyConfig} />
      </CollapsibleCard>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <div className="min-w-0 space-y-4">
          <VideoUploader
            file={file}
            onChange={handleFileChange}
            onError={(msg) => toast.error(msg)}
          />

          <CollapsibleCard
            title="Guion narrado"
            subtitle={
              manualScript.trim()
                ? `✏️ Manual · ${manualScript.trim().length} chars (Gemini API omitido)`
                : `🤖 Fallback · ${geminiModel.replace("gemini-2.5-", "Gemini ")} (no hay guion pegado)`
            }
            defaultOpen
          >
            <div className="space-y-4">
              {/* MODO PRINCIPAL: Manual desde un Gem (recomendado) */}
              <div
                className={cn(
                  "rounded-md border p-3 transition-colors",
                  manualScript.trim()
                    ? "border-amber-500/60 bg-amber-500/10"
                    : "border-amber-500/30 bg-amber-500/5",
                )}
              >
                <div className="flex items-start gap-2">
                  <FileText className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                  <div className="flex-1 space-y-2">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium flex items-center gap-1.5">
                          Manual desde tu Gem
                          <span className="rounded bg-amber-500/80 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-black">
                            recomendado
                          </span>
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Genera el guion en tu Gem custom (sin restricciones de cuota) y pégalo aquí. Coste Gemini API: $0.
                        </p>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setPromptModalOpen(true)}
                        title="Prompt para pegar como instrucciones del Gem"
                      >
                        <Sparkles className="h-3 w-3" />
                        Ver prompt para mi Gem
                      </Button>
                    </div>
                    <Textarea
                      value={manualScript}
                      onChange={(e) => setManualScript(e.target.value)}
                      placeholder="Pega aquí el guion que te dio tu Gem. Si lo dejas vacío usaremos el fallback automático abajo."
                      className="min-h-[120px] text-sm font-mono"
                      maxLength={5000}
                    />
                    <p className="text-[10px] text-muted-foreground">
                      {manualScript.trim().length > 0
                        ? `✏️ ${manualScript.trim().length} chars · modo manual activo · render solo cuesta MiniMax (~$0.06).`
                        : "Vacío → se usa el fallback automático abajo."}
                    </p>
                  </div>
                </div>
              </div>

              {/* FALLBACK: Auto con Gemini API */}
              <div
                className={cn(
                  "rounded-md border p-3 transition-colors",
                  manualScript.trim()
                    ? "opacity-50"
                    : "border-cyan-500/30 bg-cyan-500/5",
                )}
              >
                <div className="flex items-start gap-2">
                  <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-cyan-500" />
                  <div className="flex-1 space-y-2">
                    <div>
                      <p className="text-sm font-medium">
                        Fallback · Auto con Gemini API
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Si no pegas guion arriba, llamamos a Gemini API. Útil cuando no tienes el Gem a mano.
                      </p>
                    </div>
                    <Select
                      value={geminiModel}
                      onValueChange={(v) =>
                        setGeminiModel(v as "gemini-2.5-flash" | "gemini-2.5-pro")
                      }
                      disabled={Boolean(manualScript.trim())}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gemini-2.5-pro">
                          Pro · ~$0.08 total · respeta longitud
                        </SelectItem>
                        <SelectItem value="gemini-2.5-flash">
                          Flash · ~$0.06 total · puede driftar longitud
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            </div>
          </CollapsibleCard>

          <CollapsibleCard title="Voz narrada" subtitle={voiceId || "sin seleccionar"} defaultOpen>
            <VoicePicker value={voiceId} onChange={setVoiceId} language="en" />
          </CollapsibleCard>

          <CollapsibleCard title="Subtítulos karaoke" defaultOpen>
            <SubsAutoStyleEditor
              style={style}
              onChange={setStyle}
              inputPath=""
              sampleText="I LAY THE WATERPROOF MEMBRANE"
              showSafeZones
            />
          </CollapsibleCard>

          <CollapsibleCard
            title="Anti-copy & render"
            subtitle={`${quality} · sat ${saturation.toFixed(2)}${upscale ? " · 1080p" : ""}${mirror ? " · espejo" : ""}`}
          >
            <div className="space-y-3">
              <label className="flex cursor-pointer items-center justify-between gap-2 rounded-md border p-2 text-sm">
                <span className="space-y-0.5">
                  <span className="block font-medium">Upscale a 1080p (Lanczos)</span>
                  <span className="block text-xs text-muted-foreground">
                    Solo si el vídeo es {"<"} 1080 ancho. Cambia hash píxel.
                  </span>
                </span>
                <Switch checked={upscale} onCheckedChange={setUpscale} />
              </label>

              <label className="flex cursor-pointer items-center justify-between gap-2 rounded-md border p-2 text-sm">
                <span className="space-y-0.5">
                  <span className="block font-medium">Zoom + crop centrado</span>
                  <span className="block text-xs text-muted-foreground">
                    Recorta 8% para variar firma visual.
                  </span>
                </span>
                <Switch checked={pulseZoom} onCheckedChange={setPulseZoom} />
              </label>

              <label className="flex cursor-pointer items-center justify-between gap-2 rounded-md border p-2 text-sm">
                <span className="flex items-start gap-2">
                  <FlipHorizontal2 className="mt-0.5 h-4 w-4 shrink-0 text-cyan-500" />
                  <span className="space-y-0.5">
                    <span className="block font-medium">Modo espejo (volteo horizontal)</span>
                    <span className="block text-xs text-muted-foreground">
                      Voltea el vídeo en X. Útil para diferenciar segundas
                      versiones del mismo clip.
                    </span>
                  </span>
                </span>
                <Switch checked={mirror} onCheckedChange={setMirror} />
              </label>

              <div className="space-y-1">
                <Label className="text-xs">Saturación: {saturation.toFixed(2)}x</Label>
                <input
                  type="range"
                  min="0.8"
                  max="1.6"
                  step="0.05"
                  value={saturation}
                  onChange={(e) => setSaturation(Number(e.target.value))}
                  className="w-full"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs">Calidad render</Label>
                  <Select value={quality} onValueChange={setQuality}>
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {QUALITY_OPTIONS.map((q) => (
                        <SelectItem key={q} value={q}>
                          {q}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Whisper</Label>
                  <Select value={whisperModel} onValueChange={setWhisperModel}>
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {WHISPER_MODELS.map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </CollapsibleCard>
        </div>

        {/* Preview sticky 9:16 con zonas de seguridad */}
        <div className="space-y-3 lg:sticky lg:top-6">
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Preview
            </p>
            {previewUrl ? (
              <div
                className="relative overflow-hidden rounded-md border bg-black"
                style={{ containerType: "inline-size" }}
              >
                <video
                  src={previewUrl}
                  controls
                  preload="metadata"
                  playsInline
                  muted
                  className="w-full"
                  style={{
                    aspectRatio: "9 / 16",
                    display: "block",
                    transform: mirror ? "scaleX(-1)" : undefined,
                  }}
                />
                {/* Zonas de seguridad TikTok (15% arriba, 25% abajo) */}
                <div
                  className="pointer-events-none absolute inset-x-0 top-0 border-b border-dashed border-amber-400/40 bg-amber-400/5"
                  style={{ height: "15%" }}
                />
                <div
                  className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-dashed border-amber-400/40 bg-amber-400/5"
                  style={{ height: "25%" }}
                />
                {/* Línea Y subtítulos */}
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
                {/* Texto de muestra */}
                <div
                  className="pointer-events-none absolute flex justify-center"
                  style={{
                    left: "50%",
                    top: `${style.y_position * 100}%`,
                    transform: "translate(-50%, -50%)",
                    width: `${style.max_width * 100}%`,
                    fontFamily: previewFontFamily,
                    fontWeight: selectedFont?.source === "bundled" ? "normal" : 900,
                    fontSynthesis: "none",
                    fontSize: `${style.font_scale * 100 * (16 / 9)}cqi`,
                    color: style.text_color,
                    WebkitTextStroke: `${style.stroke_width / 80}em ${style.stroke_color}`,
                    letterSpacing: "0.01em",
                    textAlign: "center",
                    lineHeight: 1.05,
                  }}
                >
                  HELLO POV
                </div>
                {upscale && (
                  <div className="pointer-events-none absolute right-2 top-2 rounded bg-primary/80 px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">
                    1080p
                  </div>
                )}
                {mirror && (
                  <div className="pointer-events-none absolute left-2 top-2 flex items-center gap-1 rounded bg-cyan-500/85 px-2 py-0.5 text-[10px] font-semibold text-black">
                    <FlipHorizontal2 className="h-3 w-3" />
                    espejo
                  </div>
                )}
              </div>
            ) : (
              <div
                className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed bg-muted text-muted-foreground"
                style={{ aspectRatio: "9 / 16" }}
              >
                <HardHat className="h-8 w-8 opacity-50" />
                <p className="text-xs">Sube un vídeo para previsualizarlo</p>
              </div>
            )}
            <p className="text-[10px] text-muted-foreground">
              Zonas ámbar = áreas no seguras TikTok (UI/captions). Línea cian =
              posición Y de los subs.
            </p>
          </div>
          <Button
            onClick={submit}
            disabled={!file || !voiceId || enqueue.isPending}
            size="lg"
            className="w-full"
          >
            {enqueue.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Generar y encolar
          </Button>
        </div>
      </div>

      {/* Modal del prompt para Gem custom (saltarse Gemini API) */}
      <Dialog open={promptModalOpen} onOpenChange={setPromptModalOpen}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Prompt para Gem custom de Gemini</DialogTitle>
            <DialogDescription>
              Crea un Gem en{" "}
              <a
                href="https://gemini.google.com/gems/create"
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                gemini.google.com/gems/create
              </a>
              , pega abajo como instrucciones, súbele tu vídeo, copia su
              respuesta y pégala en &quot;Guion manual&quot; para saltarte el
              coste de Gemini API.
              {file
                ? ` Calibrado a tu vídeo (${videoDuration}s).`
                : " Calibrado a 60s por defecto — sube el vídeo para ajustarlo."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {promptPreview.data && (
              <p className="text-xs text-muted-foreground">
                Target: <b>{promptPreview.data.target_chars} chars</b> ·{" "}
                {promptPreview.data.target_seconds}s de narración
              </p>
            )}
            <Textarea
              readOnly
              value={
                promptPreview.isLoading
                  ? "Cargando…"
                  : promptPreview.data?.system_prompt ?? ""
              }
              className="min-h-[300px] font-mono text-xs"
              onFocus={(e) => e.currentTarget.select()}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPromptModalOpen(false)}>
              Cerrar
            </Button>
            <Button onClick={copyPrompt} disabled={!promptPreview.data}>
              <Copy className="h-4 w-4" />
              Copiar prompt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
