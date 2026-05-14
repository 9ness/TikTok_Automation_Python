"use client";

import {
  CheckCircle2,
  ChevronRight,
  Loader2,
  Sparkles,
  Upload,
  Video,
  Wand2,
  X,
} from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useEditorAutoTools,
  useEditorUsers,
  useEnqueueEditorAuto,
} from "@/lib/queries/editor-auto";
import type { EditorAutoEnqueueResponse } from "@/lib/types/editor-auto";
import { cn } from "@/lib/utils";

const ACCEPTED_EXTS = [".mp4", ".mov", ".mkv", ".webm", ".avi"];
const ACCEPTED_MIME =
  "video/mp4,video/quicktime,video/x-matroska,video/webm,video/avi";
const SCRIPTED_TOOL_ID = "silence_cutter_scripted";

export default function EditorAutoGeneratePage() {
  const users = useEditorUsers();
  const tools = useEditorAutoTools();
  const enqueue = useEnqueueEditorAuto();

  const [userId, setUserId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [script, setScript] = useState<string>("");
  const [lastJob, setLastJob] = useState<EditorAutoEnqueueResponse | null>(null);

  // Mapeo tool_id → metadata (display_name) en cliente para mostrar
  // nombres human-friendly en vez de los slugs técnicos.
  const toolsById = useMemo(() => {
    const map: Record<string, { display_name: string; description: string }> = {};
    for (const t of tools.data ?? []) {
      map[t.tool_id] = {
        display_name: t.display_name,
        description: t.description,
      };
    }
    return map;
  }, [tools.data]);

  const selectedUser = (users.data ?? []).find((u) => u.id === userId);
  const enabledSteps = selectedUser
    ? selectedUser.tool_flow.filter((s) => s.enabled)
    : [];
  const needsScript = enabledSteps.some((s) => s.tool_id === SCRIPTED_TOOL_ID);
  const scriptOk = !needsScript || script.trim().length > 0;
  const ready = Boolean(userId && file && enabledSteps.length > 0 && scriptOk);

  const handleSubmit = async () => {
    if (!userId || !file) return;
    const res = await enqueue.mutateAsync({
      userId,
      file,
      script: needsScript ? script : undefined,
    });
    setLastJob(res);
    setFile(null);
    setScript("");
  };

  return (
    <div className="space-y-4 p-3 sm:space-y-6 sm:p-6">
      <header className="space-y-1">
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">
          Generar — Editor Auto
        </h1>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Sube un vídeo y selecciona un usuario. Se aplicará su flujo de
          herramientas (ya reordenado por el orchestrator) y el resultado se
          copiará a <code className="rounded bg-muted px-1">salida/</code>.
        </p>
      </header>

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm sm:text-base">
              <Wand2 className="h-4 w-4 text-brand-cyan" />
              1. Configuración
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="ea-user">Usuario</Label>
              <select
                id="ea-user"
                className="w-full rounded-md border bg-background p-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-cyan/40"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                disabled={users.isLoading}
              >
                <option value="">— selecciona un usuario —</option>
                {(users.data ?? []).map((u) => {
                  const count = u.tool_flow.filter((s) => s.enabled).length;
                  return (
                    <option key={u.id} value={u.id}>
                      {u.display_name || u.name} ·{" "}
                      {count} herramienta{count === 1 ? "" : "s"}
                    </option>
                  );
                })}
              </select>
            </div>

            {selectedUser && (
              <FlowPreview
                steps={enabledSteps}
                toolsById={toolsById}
                loadingTools={tools.isLoading}
              />
            )}

            <div className="space-y-1.5">
              <Label>Vídeo input</Label>
              <DropZone file={file} onFileChange={setFile} />
            </div>

            {needsScript && (
              <div className="space-y-1.5">
                <Label htmlFor="ea-script" className="flex items-center gap-1.5">
                  Guión de referencia
                  <span className="rounded bg-brand-violet/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-brand-violet">
                    obligatorio
                  </span>
                </Label>
                <Textarea
                  id="ea-script"
                  value={script}
                  onChange={(e) => setScript(e.target.value)}
                  placeholder="Pega aquí lo que el speaker debía decir. Se usará como ground truth para cortar fillers/repeticiones."
                  rows={6}
                  className="resize-y text-sm"
                />
                <p className="text-[11px] text-muted-foreground">
                  El cortador con guión alinea el transcript con este texto y
                  corta cualquier palabra fuera del guión.
                </p>
              </div>
            )}

            <Button
              className="w-full bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90"
              size="lg"
              onClick={handleSubmit}
              disabled={!ready || enqueue.isPending}
            >
              {enqueue.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-4 w-4" />
              )}
              Encolar generación
            </Button>
            {enqueue.isError && (
              <p className="text-xs text-destructive">
                {(enqueue.error as Error).message}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm sm:text-base">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              2. Resultado
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {lastJob ? (
              <ResultCard job={lastJob} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Aún no se ha encolado ningún job en esta sesión.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preview del flujo de herramientas con nombres descriptivos + iconos
// ---------------------------------------------------------------------------
function FlowPreview({
  steps,
  toolsById,
  loadingTools,
}: {
  steps: { tool_id: string }[];
  toolsById: Record<string, { display_name: string; description: string }>;
  loadingTools: boolean;
}) {
  if (steps.length === 0) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
        ⚠️ Este usuario no tiene herramientas habilitadas. Ve a{" "}
        <strong>Usuarios</strong> y configura el flujo antes de generar.
      </div>
    );
  }
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        <Wand2 className="h-3 w-3" />
        Flujo configurado
      </div>
      <ol className="space-y-1.5">
        {steps.map((s, i) => {
          const meta = toolsById[s.tool_id];
          return (
            <li
              key={s.tool_id}
              className="flex items-center gap-2 text-sm"
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-cyan/20 text-[10px] font-bold text-brand-cyan">
                {i + 1}
              </span>
              <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">
                {loadingTools && !meta ? (
                  <span className="inline-flex items-center gap-1 text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {s.tool_id}
                  </span>
                ) : (
                  <>
                    <span className="font-medium">
                      {meta?.display_name ?? s.tool_id}
                    </span>
                    <code className="ml-2 hidden text-[10px] text-muted-foreground sm:inline">
                      {s.tool_id}
                    </code>
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DropZone con estilo de marca — sustituye el input file nativo verde
// ---------------------------------------------------------------------------
function DropZone({
  file,
  onFileChange,
}: {
  file: File | null;
  onFileChange: (f: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const openPicker = () => inputRef.current?.click();

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const f = e.dataTransfer.files?.[0];
      if (f) onFileChange(f);
    },
    [onFileChange],
  );

  if (file) {
    return (
      <div className="flex items-center gap-3 rounded-md border bg-card p-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-brand-cyan/20 to-brand-violet/20">
          <Video className="h-5 w-5 text-brand-cyan" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {(file.size / 1024 / 1024).toFixed(1)} MB
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onFileChange(null)}
          className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
          aria-label="Quitar archivo"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={openPicker}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={onDrop}
      className={cn(
        "flex w-full flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed bg-card/30 px-4 py-6 transition-colors hover:bg-card/60 sm:py-8",
        isDragging
          ? "border-brand-cyan bg-brand-cyan/5"
          : "border-muted-foreground/30",
      )}
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-brand-cyan/20 to-brand-violet/20 sm:h-12 sm:w-12">
        <Upload className="h-5 w-5 text-brand-cyan sm:h-6 sm:w-6" />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium">
          Haz click o arrastra un vídeo aquí
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {ACCEPTED_EXTS.join(" · ").toUpperCase()} · máx 500 MB
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_MIME}
        onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
        className="hidden"
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Card de resultado tras encolar
// ---------------------------------------------------------------------------
function ResultCard({ job }: { job: EditorAutoEnqueueResponse }) {
  return (
    <>
      <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm">
        <div className="font-medium text-emerald-600 dark:text-emerald-400">
          Job encolado ✓
        </div>
        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <div>
            <span className="text-muted-foreground">Job ID</span>
            <p className="truncate font-mono">{job.job_id}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Posición</span>
            <p>
              <Badge variant="outline" className="mt-0.5">
                #{job.position_in_queue + 1}
              </Badge>
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">Usuario</span>
            <p className="truncate font-mono">{job.user_name}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Herramientas</span>
            <p>{job.tool_count}</p>
          </div>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Sigue el progreso desde el icono de cola en la esquina superior derecha.
        El MP4 final aparecerá en{" "}
        <code className="break-all rounded bg-muted px-1">
          TIKTOK_EDITOR/Usuarios/{job.user_name}/salida/
        </code>{" "}
        cuando termine.
      </p>
    </>
  );
}
