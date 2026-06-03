"use client";

import {
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Save,
  Scissors,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  useManualRender,
  useOutputEditProject,
  userFilePreviewUrl,
} from "@/lib/queries/editor-auto";
import type { EditWord } from "@/lib/types/editor-auto";
import { cn } from "@/lib/utils";

/** Una unidad de la línea de tiempo: una palabra o un hueco (silencio). */
interface Unit {
  kind: "word" | "gap";
  label: string;
  start: number;
  end: number;
  keep: boolean;
}

const _GAP_MIN_SHOW = 0.25; // huecos menores no se muestran como chip (ruido)
const _MIN_KEEP = 0.1;

function _overlapKeptRatio(
  a: number,
  b: number,
  keeps: [number, number][],
): number {
  const dur = Math.max(1e-6, b - a);
  let inside = 0;
  for (const [ks, ke] of keeps) {
    if (ke <= a) continue;
    if (ks >= b) break;
    inside += Math.min(b, ke) - Math.max(a, ks);
  }
  return inside / dur;
}

/** Construye las unidades (palabras + huecos) cubriendo [0, duration]. La
 *  decisión inicial keep/cut se hereda de los tramos que conservó el algoritmo. */
function buildUnits(
  words: EditWord[],
  duration: number,
  keeps: [number, number][],
): Unit[] {
  const units: Unit[] = [];
  const ordered = [...words].sort((x, y) => x.start - y.start);
  let cursor = 0;
  const push = (kind: "word" | "gap", label: string, s: number, e: number) => {
    if (e - s <= 0.001) return;
    units.push({ kind, label, start: s, end: e, keep: _overlapKeptRatio(s, e, keeps) >= 0.5 });
  };
  for (const w of ordered) {
    if (w.start > cursor) push("gap", `⏸ ${(w.start - cursor).toFixed(1)}s`, cursor, w.start);
    push("word", w.word || "·", w.start, w.end);
    cursor = Math.max(cursor, w.end);
  }
  if (duration > cursor) push("gap", `⏸ ${(duration - cursor).toFixed(1)}s`, cursor, duration);
  return units;
}

/** Tramos a CONSERVAR = unión de unidades keep contiguas. */
function mergeKept(units: Unit[]): [number, number][] {
  const out: [number, number][] = [];
  for (const u of units) {
    if (!u.keep) continue;
    const last = out[out.length - 1];
    if (last && u.start - last[1] < 0.02) last[1] = u.end;
    else out.push([u.start, u.end]);
  }
  return out.filter(([s, e]) => e - s >= _MIN_KEEP);
}

function fmt(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export function ManualEditor({
  userId,
  filename,
  onClose,
}: {
  userId: string;
  filename: string;
  onClose: () => void;
}) {
  const proj = useOutputEditProject(userId, filename);
  const render = useManualRender(userId);
  const videoRef = useRef<HTMLVideoElement>(null);

  const [units, setUnits] = useState<Unit[]>([]);
  const [previewing, setPreviewing] = useState(false);

  useEffect(() => {
    if (proj.data) {
      setUnits(
        buildUnits(
          proj.data.words ?? [],
          proj.data.video_duration_s ?? 0,
          (proj.data.keep_intervals ?? []) as [number, number][],
        ),
      );
    }
  }, [proj.data]);

  const duration = proj.data?.video_duration_s ?? 0;
  const original = proj.data?.original_filename ?? null;
  const keepIntervals = useMemo(() => mergeKept(units), [units]);
  const keptDur = useMemo(
    () => keepIntervals.reduce((a, [s, e]) => a + (e - s), 0),
    [keepIntervals],
  );

  const videoUrl = original
    ? userFilePreviewUrl(userId, "recuperacion", original)
    : null;

  // Preview: al reproducir, saltar los tramos cortados.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !previewing) return;
    const onTime = () => {
      const t = v.currentTime;
      const inKept = keepIntervals.some(([s, e]) => t >= s - 0.05 && t < e);
      if (inKept) return;
      const next = keepIntervals.find(([s]) => s > t);
      if (next) v.currentTime = next[0];
      else {
        v.pause();
        setPreviewing(false);
      }
    };
    v.addEventListener("timeupdate", onTime);
    return () => v.removeEventListener("timeupdate", onTime);
  }, [previewing, keepIntervals]);

  function toggle(i: number) {
    setUnits((u) => u.map((x, j) => (j === i ? { ...x, keep: !x.keep } : x)));
  }
  function resetToAlgo() {
    if (proj.data) {
      setUnits(
        buildUnits(
          proj.data.words ?? [],
          proj.data.video_duration_s ?? 0,
          (proj.data.keep_intervals ?? []) as [number, number][],
        ),
      );
    }
  }

  function startPreview() {
    const v = videoRef.current;
    const first = keepIntervals[0];
    if (!v || !first) return;
    v.currentTime = first[0];
    void v.play();
    setPreviewing(true);
  }

  async function doRender() {
    if (keepIntervals.length === 0) {
      toast.error("No queda nada que conservar.");
      return;
    }
    try {
      await render.mutateAsync({ filename, keep_intervals: keepIntervals });
      toast.success(
        "Renderizando el retoque — al terminar reemplaza el vídeo de salida (mismo nombre). Míralo en la Cola.",
      );
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al renderizar");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2">
        <Scissors className="h-4 w-4 text-brand-cyan" />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">
          Retoque · {filename}
        </span>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose} aria-label="Cerrar">
          <X className="h-5 w-5" />
        </Button>
      </div>

      {proj.isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : !proj.data?.has_project ? (
        <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-muted-foreground">
          Este vídeo no tiene proyecto editable (se generó antes de activar el
          retoque manual). Vuelve a generarlo desde entrada para poder retocarlo.
        </div>
      ) : !videoUrl ? (
        <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-muted-foreground">
          No encuentro el vídeo original en recuperación (necesario para
          re-renderizar). No lo borres de recuperación.
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          {/* Player */}
          <div className="mx-auto w-full max-w-md bg-black">
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video
              ref={videoRef}
              src={videoUrl}
              controls
              playsInline
              className="mx-auto block max-h-[42vh] w-full"
            />
          </div>

          <div className="space-y-4 p-3 sm:p-4">
            {/* Línea de tiempo */}
            <div>
              <p className="mb-1 text-[11px] text-muted-foreground">
                Línea de tiempo — verde = se queda · rojo = se quita (toca para cambiar)
              </p>
              <div className="flex h-9 w-full overflow-hidden rounded-md border">
                {units.map((u, i) => (
                  <button
                    key={i}
                    type="button"
                    title={`${u.kind === "gap" ? "Silencio" : u.label} · ${fmt(u.start)}–${fmt(u.end)}`}
                    onClick={() => toggle(i)}
                    style={{ flexGrow: Math.max(0.02, u.end - u.start) }}
                    className={cn(
                      "h-full min-w-[2px] border-r border-background/30 transition-colors",
                      u.keep
                        ? "bg-emerald-500/70 hover:bg-emerald-500"
                        : "bg-rose-500/40 hover:bg-rose-500/70",
                      u.kind === "gap" && "opacity-70",
                    )}
                  />
                ))}
              </div>
            </div>

            {/* Transcripción */}
            <div>
              <p className="mb-1.5 text-[11px] text-muted-foreground">
                Transcripción — toca una palabra o silencio para quitarlo/restaurarlo
              </p>
              <div className="flex flex-wrap gap-1.5">
                {units.map((u, i) =>
                  u.kind === "word" ? (
                    <button
                      key={i}
                      type="button"
                      onClick={() => toggle(i)}
                      className={cn(
                        "rounded px-1.5 py-1 text-sm transition-colors",
                        u.keep
                          ? "bg-accent/50 hover:bg-accent"
                          : "bg-rose-500/15 text-rose-500 line-through hover:bg-rose-500/25",
                      )}
                    >
                      {u.label}
                    </button>
                  ) : u.end - u.start >= _GAP_MIN_SHOW ? (
                    <button
                      key={i}
                      type="button"
                      onClick={() => toggle(i)}
                      title="Silencio"
                      className={cn(
                        "rounded px-1.5 py-1 text-[10px] font-medium transition-colors",
                        u.keep
                          ? "bg-amber-500/15 text-amber-600 hover:bg-amber-500/25 dark:text-amber-400"
                          : "bg-rose-500/15 text-rose-500 line-through hover:bg-rose-500/25",
                      )}
                    >
                      {u.label}
                    </button>
                  ) : null,
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer acciones */}
      {proj.data?.has_project && videoUrl && (
        <div className="shrink-0 space-y-2 border-t bg-card/40 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              Quedan <strong className="text-foreground">{fmt(keptDur)}</strong> de {fmt(duration)}
              {" · "}
              {units.filter((u) => u.kind === "word" && !u.keep).length} palabra(s) fuera
            </span>
            <button
              type="button"
              onClick={resetToAlgo}
              className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="h-3 w-3" /> Reset
            </button>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              onClick={previewing ? () => { videoRef.current?.pause(); setPreviewing(false); } : startPreview}
            >
              {previewing ? <Pause className="mr-1 h-4 w-4" /> : <Play className="mr-1 h-4 w-4" />}
              {previewing ? "Parar" : "Previsualizar corte"}
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  size="sm"
                  className="flex-1 bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90"
                  disabled={render.isPending || keepIntervals.length === 0}
                >
                  {render.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-1 h-4 w-4" />
                  )}
                  Renderizar y reemplazar
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent className="w-[calc(100vw-2rem)] max-w-md">
                <AlertDialogHeader>
                  <AlertDialogTitle>¿Renderizar y reemplazar el vídeo de salida?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Se re-renderiza con tus cortes (subtítulos y flecha se rehacen
                    alineados) y se REEMPLAZA «{filename}» en salida con el mismo
                    nombre. El original de recuperación no se toca. Tarda 1-2 min.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction onClick={doRender}>Renderizar</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      )}
    </div>
  );
}
