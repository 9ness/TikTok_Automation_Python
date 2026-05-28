"use client";

import { useRef, useState } from "react";
import {
  CheckCircle2,
  Download,
  FileVideo,
  Loader2,
  ShieldOff,
  Trash2,
  Upload,
  X,
  XCircle,
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
import { ApiError } from "@/lib/api";
import {
  type WatermarkRemoverResponse,
  type WatermarkType,
  useRemoveWatermark,
  watermarkRemoverFileUrl,
} from "@/lib/queries/watermarkRemover";
import { cn } from "@/lib/utils";

interface QueueItem {
  id: string;
  file: File;
  status: "pending" | "processing" | "done" | "failed";
  result?: WatermarkRemoverResponse;
  error?: string;
}

const WATERMARK_OPTIONS: { value: WatermarkType; label: string; note: string }[] = [
  {
    value: "auto",
    label: "Auto · cubre ambos",
    note: "Aplica delogo sobre las zonas de Veo Flow y Gemini Chat simultáneamente — seguro si no sabes el origen.",
  },
  {
    value: "veo_flow",
    label: "Veo Flow",
    note: "Texto 'Veo' abajo-derecha (vídeos descargados desde labs.google.com/flow).",
  },
  {
    value: "gemini_chat",
    label: "Gemini Chat",
    note: "Estrella sparkle abajo-derecha (vídeos generados desde gemini.google.com chat).",
  },
];

export default function WatermarkRemoverPage() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [watermarkType, setWatermarkType] = useState<WatermarkType>("auto");
  const [running, setRunning] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const remove = useRemoveWatermark();

  const totalPending = items.filter((i) => i.status === "pending").length;
  const totalDone = items.filter((i) => i.status === "done").length;
  const totalFailed = items.filter((i) => i.status === "failed").length;

  function addFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const newItems: QueueItem[] = [];
    for (const file of Array.from(files)) {
      const ext = file.name.toLowerCase().split(".").pop() ?? "";
      if (!["mp4", "mov", "mkv", "webm"].includes(ext)) {
        toast.error(`Formato no soportado: ${file.name}`);
        continue;
      }
      newItems.push({
        id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        file,
        status: "pending",
      });
    }
    if (newItems.length > 0) {
      setItems((prev) => [...prev, ...newItems]);
    }
  }

  function removeItem(id: string) {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }

  function clearAll() {
    setItems([]);
  }

  async function processOne(item: QueueItem): Promise<void> {
    setItems((prev) =>
      prev.map((i) =>
        i.id === item.id ? { ...i, status: "processing" } : i,
      ),
    );
    try {
      const result = await remove.mutateAsync({
        file: item.file,
        watermark_type: watermarkType,
      });
      setItems((prev) =>
        prev.map((i) =>
          i.id === item.id ? { ...i, status: "done", result } : i,
        ),
      );
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      setItems((prev) =>
        prev.map((i) =>
          i.id === item.id ? { ...i, status: "failed", error: msg } : i,
        ),
      );
    }
  }

  async function processAll() {
    if (running) return;
    setRunning(true);
    const pending = items.filter((i) => i.status === "pending");
    // Procesa en paralelo de hasta 3 simultáneos para no saturar el server
    const concurrency = 3;
    const queue = [...pending];
    const workers: Promise<void>[] = [];
    for (let i = 0; i < concurrency; i++) {
      workers.push(
        (async () => {
          while (queue.length > 0) {
            const item = queue.shift();
            if (!item) break;
            await processOne(item);
          }
        })(),
      );
    }
    await Promise.all(workers);
    setRunning(false);
    toast.success(`Procesados ${pending.length} vídeo(s)`);
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-4 px-3 py-4 sm:px-6 sm:py-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
            <ShieldOff className="h-5 w-5 text-amber-500 sm:h-6 sm:w-6" />
            Quitar marca de agua
          </h1>
          <p className="text-xs text-muted-foreground sm:text-sm">
            Vídeos Veo 3 / Gemini · ffmpeg `delogo` · coste $0
          </p>
        </div>
      </div>

      {/* Selector tipo marca */}
      <Card>
        <CardContent className="space-y-2 p-3 sm:p-4">
          <Label className="text-xs sm:text-sm">Tipo de marca de agua</Label>
          <Select
            value={watermarkType}
            onValueChange={(v) => setWatermarkType(v as WatermarkType)}
            disabled={running}
          >
            <SelectTrigger className="h-10 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WATERMARK_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  <div className="flex flex-col">
                    <span className="font-medium">{opt.label}</span>
                    <span className="text-[10px] text-muted-foreground sm:text-xs">
                      {opt.note}
                    </span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {/* Drop zone / file picker */}
      <Card>
        <CardContent className="p-3 sm:p-4">
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              addFiles(e.dataTransfer.files);
            }}
            className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-amber-500/40 bg-amber-500/5 px-4 py-8 transition-colors hover:bg-amber-500/10 sm:py-12"
          >
            <Upload className="h-8 w-8 text-amber-500 sm:h-10 sm:w-10" />
            <p className="text-center text-xs font-medium sm:text-sm">
              Toca o arrastra vídeos aquí
            </p>
            <p className="text-center text-[10px] text-muted-foreground sm:text-xs">
              .mp4 / .mov / .mkv / .webm — máx 200 MB cada uno
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm"
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Action bar */}
      {items.length > 0 && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm">
            <span className="rounded bg-muted px-2 py-1 font-medium">
              {items.length} vídeos
            </span>
            {totalPending > 0 && (
              <span className="rounded bg-amber-500/15 px-2 py-1 text-amber-700 dark:text-amber-300">
                {totalPending} pendientes
              </span>
            )}
            {totalDone > 0 && (
              <span className="rounded bg-emerald-500/15 px-2 py-1 text-emerald-700 dark:text-emerald-300">
                {totalDone} hechos
              </span>
            )}
            {totalFailed > 0 && (
              <span className="rounded bg-red-500/15 px-2 py-1 text-red-700 dark:text-red-300">
                {totalFailed} fallos
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={clearAll}
              disabled={running}
              className="h-9 flex-1 text-xs sm:h-8 sm:flex-none"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Limpiar
            </Button>
            <Button
              size="sm"
              onClick={processAll}
              disabled={running || totalPending === 0}
              className="h-9 flex-1 gap-1 bg-amber-600 text-xs hover:bg-amber-700 sm:h-8 sm:flex-none"
            >
              {running ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Procesando…
                </>
              ) : (
                <>
                  <ShieldOff className="h-3.5 w-3.5" />
                  Procesar {totalPending}
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Lista de vídeos */}
      <div className="space-y-2">
        {items.map((item) => (
          <Card key={item.id}>
            <CardContent className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:gap-3 sm:p-4">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <FileVideo className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium sm:text-sm">
                    {item.file.name}
                  </p>
                  <p className="text-[10px] text-muted-foreground sm:text-xs">
                    {(item.file.size / 1024 / 1024).toFixed(2)} MB
                    {item.result &&
                      ` → ${(item.result.output_size_bytes / 1024 / 1024).toFixed(2)} MB · ${item.result.processing_seconds}s`}
                  </p>
                  {item.error && (
                    <p className="text-[10px] text-red-600 dark:text-red-400 sm:text-xs">
                      {item.error}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {item.status === "pending" && (
                  <span className="rounded bg-muted px-2 py-0.5 text-[10px] text-muted-foreground sm:text-xs">
                    En espera
                  </span>
                )}
                {item.status === "processing" && (
                  <span className="flex items-center gap-1 rounded bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-700 dark:text-amber-300 sm:text-xs">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Procesando
                  </span>
                )}
                {item.status === "done" && (
                  <span className="flex items-center gap-1 rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-700 dark:text-emerald-300 sm:text-xs">
                    <CheckCircle2 className="h-3 w-3" />
                    Listo
                  </span>
                )}
                {item.status === "failed" && (
                  <span className="flex items-center gap-1 rounded bg-red-500/15 px-2 py-0.5 text-[10px] text-red-700 dark:text-red-300 sm:text-xs">
                    <XCircle className="h-3 w-3" />
                    Falló
                  </span>
                )}

                {item.status === "done" && item.result && (
                  <a
                    href={watermarkRemoverFileUrl(item.result.output_path)}
                    download={item.result.output_filename}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1 text-xs"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Descargar
                    </Button>
                  </a>
                )}

                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-muted-foreground hover:text-red-500"
                  onClick={() => removeItem(item.id)}
                  disabled={item.status === "processing"}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {items.length === 0 && (
        <p className="py-8 text-center text-xs text-muted-foreground sm:text-sm">
          Añade vídeos arriba para empezar.
        </p>
      )}

      <Card className="bg-muted/30">
        <CardContent className="space-y-1 p-3 text-[11px] text-muted-foreground sm:p-4 sm:text-xs">
          <p>
            <strong>Coste:</strong> $0 — todo se procesa con ffmpeg en el VPS.
          </p>
          <p>
            <strong>Drive:</strong> v1 entrega URL de descarga directa. La v2
            permitirá enviarlos a la carpeta `videos/sin_marca/` de un producto.
          </p>
          <p>
            <strong>Limpieza:</strong> archivos en el server se borran tras 24h.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
