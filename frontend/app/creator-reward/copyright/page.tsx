"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { VideoUploader } from "@/components/creator-reward/copyright/VideoUploader";
import { Button } from "@/components/ui/button";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { FontSelector } from "@/components/ui/font-selector";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { useEnqueueCopyright } from "@/lib/queries/creator-reward/copyright";
import { useFontByPath, useFontFamily } from "@/lib/queries/fonts";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { CleanModeValue } from "@/lib/types/creator-reward";
import { cn } from "@/lib/utils";

const HOOK_POSITIONS: { value: number; label: string }[] = [
  { value: 0.20, label: "Superior (Seguridad TikTok)" },
  { value: 0.45, label: "Centro (Enfrentamiento)" },
  { value: 0.75, label: "Inferior (Subtítulos)" },
];

// Solo 2 colores predefinidos — matches Streamlit (Amarillo GTA / Blanco Clásico).
const HOOK_COLORS: { value: string; label: string }[] = [
  { value: "#FDD002", label: "Amarillo GTA" },
  { value: "#FFFFFF", label: "Blanco Clásico" },
];

export default function CopyrightPage() {
  const enqueue = useEnqueueCopyright();
  const openQueue = useDrawerStore((s) => s.openQueue);

  const [file, setFile] = useState<File | null>(null);
  const [cleanMode, setCleanMode] = useState<CleanModeValue>("Subtítulos Virales");
  const [hookYPct, setHookYPct] = useState<number>(0.20);
  const [hookColor, setHookColor] = useState<string>("#FDD002");
  const [upscale1080p, setUpscale1080p] = useState<boolean>(false);
  const [fontPath, setFontPath] = useState<string>("");

  // El hook (gancho IA en inglés) se renderiza solo en modo Camuflaje. En
  // modo Subtítulos Virales, los controles de color afectan al color de los
  // subs nuevos (no se aplica position porque siguen la trayectoria del
  // texto original detectado).
  const isCamuflaje = cleanMode === "Camuflaje Geométrico (Sin Subtítulos)";
  // Dos modos "limpiar" que NO añaden ningún texto:
  //  - "Solo Limpiar"     → tapa subs originales (blur) + anti-copy.
  //  - "Limpiar Metadata" → NO toca subs (deja todo visible) + anti-copy.
  // En ambos ocultamos los controles de texto (posición, color, fuente).
  const isCleanMaskSubs = cleanMode === "Solo Limpiar (Sin Subtítulos)";
  const isCleanMeta = cleanMode === "Limpiar Metadata (Sin Tocar Subtítulos)";
  const isCleanOnly = isCleanMaskSubs || isCleanMeta;
  const showHookConfig = !isCleanOnly;

  // Carga la fuente real elegida (bundled vía @font-face, system vía nombre).
  const selectedFont = useFontByPath(fontPath);
  const previewFontFamily = useFontFamily(selectedFont);

  // Preview URL del MP4 local (Object URL). Se revoca al cambiar de archivo.
  const previewUrl = useMemo(
    () => (file ? URL.createObjectURL(file) : null),
    [file],
  );
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  async function submit() {
    if (!file) return;
    try {
      const res = await enqueue.mutateAsync({
        file,
        clean_mode: cleanMode,
        hook_y_pct: hookYPct,
        hook_color: hookColor,
        upscale_1080p: upscale1080p,
        font_path: fontPath || null,
      });
      toast.success(`Encolado · job ${res.job_id.slice(0, 8)}`);
      openQueue();
      setFile(null);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al encolar.");
    }
  }

  return (
    <div className="container mx-auto space-y-4 p-6 md:p-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Quitar Copy</h1>
        <p className="text-sm text-muted-foreground">
          Sube un vídeo, oculta los subtítulos originales y reemplaza por unos virales.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <div className="min-w-0 space-y-4">
          <VideoUploader
            file={file}
            onChange={setFile}
            onError={(msg) => toast.error(msg)}
          />

          <CollapsibleCard
            title="Configuración"
            subtitle={
              cleanMode === "Subtítulos Virales"
                ? `${cleanMode} · ${HOOK_POSITIONS.find((p) => p.value === hookYPct)?.label.split(" ")[0]} · ${HOOK_COLORS.find((c) => c.value === hookColor)?.label}`
                : cleanMode
            }
            defaultOpen
          >
            <div className="space-y-3">
              <div className="space-y-1">
                <Label className="text-xs">Modo de limpieza</Label>
                <Select
                  value={cleanMode}
                  onValueChange={(v) => setCleanMode(v as CleanModeValue)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Subtítulos Virales">
                      Subtítulos Virales
                    </SelectItem>
                    <SelectItem value="Camuflaje Geométrico (Sin Subtítulos)">
                      Camuflaje Geométrico (sin subtítulos)
                    </SelectItem>
                    <SelectItem value="Solo Limpiar (Sin Subtítulos)">
                      Solo Limpiar (tapa subs originales, sin texto)
                    </SelectItem>
                    <SelectItem value="Limpiar Metadata (Sin Tocar Subtítulos)">
                      Limpiar Metadata (no toca subs, sin texto)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {showHookConfig && isCamuflaje && (
                <div className="space-y-1">
                  <Label className="text-xs">Posición del hook</Label>
                  <Select
                    value={String(hookYPct)}
                    onValueChange={(v) => setHookYPct(Number(v))}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOOK_POSITIONS.map((p) => (
                        <SelectItem key={p.value} value={String(p.value)}>
                          {p.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {showHookConfig && (
                <div className="space-y-1">
                  <Label className="text-xs">
                    {isCamuflaje ? "Color del hook" : "Color de los subtítulos"}
                  </Label>
                  <div className="grid grid-cols-2 gap-2">
                    {HOOK_COLORS.map((c) => (
                      <button
                        key={c.value}
                        type="button"
                        onClick={() => setHookColor(c.value)}
                        className={cn(
                          "flex items-center gap-2 rounded-md border p-2 text-sm transition-colors",
                          hookColor === c.value
                            ? "border-primary bg-primary/10"
                            : "border-input hover:border-primary/50",
                        )}
                      >
                        <span
                          className="h-5 w-5 rounded border"
                          style={{ backgroundColor: c.value }}
                        />
                        <span className="truncate">{c.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {!isCleanOnly && (
                <div className="space-y-1">
                  <Label className="text-xs">Fuente del texto</Label>
                  <FontSelector value={fontPath} onChange={setFontPath} />
                </div>
              )}

              {isCleanMaskSubs && (
                <p className="rounded-md border border-input bg-muted/40 p-2 text-xs text-muted-foreground">
                  🧼 Tapa los subtítulos originales (si los hay) + zoom +
                  limpieza de metadatos. NO añade texto nuevo.
                </p>
              )}

              {isCleanMeta && (
                <p className="rounded-md border border-input bg-muted/40 p-2 text-xs text-muted-foreground">
                  🧹 NO toca los subtítulos (deja el vídeo igual). Solo aplica el
                  anti-copy: zoom dinámico, micro-cambios y limpieza de metadatos.
                  Ideal para un vídeo normal que solo quieres &ldquo;despegar&rdquo; del copyright.
                </p>
              )}

              <label className="flex cursor-pointer items-start gap-2 rounded-md border border-input p-2 text-sm transition-colors hover:border-primary/50">
                <input
                  type="checkbox"
                  checked={upscale1080p}
                  onChange={(e) => setUpscale1080p(e.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-primary"
                />
                <div className="min-w-0 space-y-0.5">
                  <div className="font-medium">Upscale a 1080p (Lanczos)</div>
                  <p className="text-xs text-muted-foreground">
                    Solo aplica si el vídeo es menor que 1080 de ancho. Cambia
                    los hashes de píxel → ayuda a evadir detección de copyright.
                    Añade ~5-15s al render. Gratis (sin API).
                  </p>
                </div>
              </label>
            </div>
          </CollapsibleCard>
        </div>

        {/* Preview sticky derecha */}
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
                  onLoadedMetadata={(e) => {
                    (e.currentTarget as HTMLVideoElement).volume = 0.15;
                  }}
                  className="w-full"
                  style={{ aspectRatio: "9 / 16", display: "block" }}
                />
                {/* Overlay aproximado del hook/subs — sirve para visualizar
                    posición y color antes de encolar. Posicionado en % sobre
                    la altura del contenedor (mismo cálculo que el backend:
                    int(H * hook_y_pct)). En modo Subs el color afecta a los
                    nuevos subs (placeholder cerca del 78%, zona típica). */}
                <div
                  className={cn(
                    "pointer-events-none absolute inset-x-0 flex justify-center",
                    isCleanOnly && "hidden",
                  )}
                  style={{
                    top: `${(isCamuflaje ? hookYPct : 0.78) * 100}%`,
                    transform: "translateY(-50%)",
                  }}
                >
                  <div
                    style={{
                      fontFamily: previewFontFamily,
                      // Sin fontWeight explícito si la fuente es bundled
                      // (el TTF ya define el peso). Para system mantenemos
                      // 900 que es lo que esperan Impact/Arial Black/etc.
                      fontWeight: selectedFont?.source === "bundled" ? "normal" : 900,
                      fontSynthesis: "none",
                      // Tamaño proporcional al ancho del contenedor (9:16 →
                      // 1cqi = 1% del ancho). 8cqi a 320px ≈ 25px.
                      fontSize: "8cqi",
                      letterSpacing: "0.01em",
                      color: hookColor,
                      // Stroke + sombra em-based para que escalen con el
                      // tamaño del texto y no dominen la forma del glyph
                      // (antes era `WebkitTextStroke: 2px` fijo, que con
                      // fuentes estrechas tipo Anton rellenaba los huecos
                      // y la previsualización parecía Impact).
                      WebkitTextStroke: "0.06em black",
                      textShadow: "0 0.06em 0.12em rgba(0,0,0,0.6)",
                      padding: "0 6%",
                      textAlign: "center",
                      lineHeight: 1.05,
                    }}
                  >
                    {isCamuflaje ? "GANCHO IA" : "SUBTÍTULO VIRAL"}
                  </div>
                </div>
                {upscale1080p && (
                  <div className="pointer-events-none absolute right-2 top-2 rounded bg-primary/80 px-2 py-0.5 text-[10px] font-semibold text-primary-foreground">
                    1080p
                  </div>
                )}
              </div>
            ) : (
              <div
                className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed bg-muted text-muted-foreground"
                style={{ aspectRatio: "9 / 16" }}
              >
                <p className="text-xs">Sube un vídeo para previsualizarlo</p>
              </div>
            )}
          </div>
          <Button
            onClick={submit}
            disabled={!file || enqueue.isPending}
            size="lg"
            className="w-full"
          >
            {enqueue.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Procesar y encolar
          </Button>
        </div>
      </div>
    </div>
  );
}
