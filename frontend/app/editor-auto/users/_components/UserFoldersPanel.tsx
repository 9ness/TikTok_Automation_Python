"use client";

import {
  ArrowLeft,
  Download,
  FileVideo,
  FolderInput,
  FolderOpen,
  Loader2,
  Play,
  PlayCircle,
  Rocket,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { useState } from "react";

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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  useDeleteUserFile,
  useEditorUser,
  useEnqueueFromEntrada,
  useMoveUserFile,
  useUserFolders,
  userFilePreviewUrl,
} from "@/lib/queries/editor-auto";
import type { FolderFile, FolderName } from "@/lib/types/editor-auto";
import { cn } from "@/lib/utils";

const SCRIPTED_TOOL_ID = "silence_cutter_scripted";

interface FolderMeta {
  id: FolderName;
  label: string;
  description: string;
  Icon: typeof FolderOpen;
  tone: string;
}

const FOLDERS: FolderMeta[] = [
  {
    id: "entrada",
    label: "Entrada",
    description: "Vídeos crudos del cliente. Encólalos para procesar.",
    Icon: FolderInput,
    tone: "text-amber-500",
  },
  {
    id: "cola",
    label: "Cola",
    description: "En procesamiento. No tocar.",
    Icon: Loader2,
    tone: "text-brand-cyan",
  },
  {
    id: "recuperacion",
    label: "Recuperación",
    description: "Originales tras procesado OK (re-editable).",
    Icon: RotateCcw,
    tone: "text-violet-500",
  },
  {
    id: "salida",
    label: "Salida",
    description: "Vídeos terminados que el cliente descarga.",
    Icon: Download,
    tone: "text-emerald-500",
  },
];

export function UserFoldersPanel({ userId }: { userId: string }) {
  const user = useEditorUser(userId);
  const folders = useUserFolders(userId);
  const move = useMoveUserFile(userId);
  const del = useDeleteUserFile(userId);
  const enqueue = useEnqueueFromEntrada(userId);

  const [active, setActive] = useState<FolderName>("entrada");
  const counts = folders.data?.counts ?? {
    entrada: 0,
    cola: 0,
    recuperacion: 0,
    salida: 0,
  };
  const items = folders.data?.folders[active] ?? [];

  const needsScript = (user.data?.tool_flow ?? []).some(
    (s) => s.enabled && s.tool_id === SCRIPTED_TOOL_ID,
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <FolderOpen className="h-4 w-4 text-brand-cyan" />
            Carpetas — {user.data?.display_name ?? "…"}
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={() => folders.refetch()}
            disabled={folders.isFetching}
          >
            {folders.isFetching ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              "Refrescar"
            )}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {folders.data?.user_name &&
            `Drive: TIKTOK_EDITOR/Usuarios/${folders.data.user_name}/`}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Tabs por carpeta */}
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {FOLDERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setActive(f.id)}
              className={cn(
                "flex flex-col items-start gap-0.5 rounded-md border px-2 py-1.5 text-left text-xs transition-colors",
                active === f.id
                  ? "border-brand-cyan/60 bg-brand-cyan/10"
                  : "hover:bg-accent/40",
              )}
            >
              <div className="flex w-full items-center gap-1.5">
                <f.Icon className={cn("h-3.5 w-3.5 shrink-0", f.tone)} />
                <span className="flex-1 font-medium">{f.label}</span>
                <Badge variant="outline" className="px-1.5 text-[10px]">
                  {counts[f.id]}
                </Badge>
              </div>
            </button>
          ))}
        </div>

        {/* Descripción de la carpeta activa */}
        <p className="text-[11px] text-muted-foreground">
          {FOLDERS.find((f) => f.id === active)?.description}
        </p>

        {/* Lista de archivos */}
        {folders.isLoading ? (
          <div className="flex h-24 items-center justify-center">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/20 p-6 text-center text-xs text-muted-foreground">
            {active === "entrada"
              ? "Sin vídeos pendientes. El cliente los deposita aquí desde Drive."
              : `Carpeta ${active} vacía.`}
          </div>
        ) : (
          <ul className="space-y-1.5">
            {items.map((f) => (
              <FileRow
                key={f.filename}
                file={f}
                userId={userId}
                needsScript={needsScript}
                onMove={(dst) =>
                  move.mutate({
                    src_folder: f.folder,
                    dst_folder: dst,
                    filename: f.filename,
                  })
                }
                onDelete={() =>
                  del.mutate({ folder: f.folder, filename: f.filename })
                }
                onEnqueue={(script) =>
                  enqueue.mutate({ filename: f.filename, script })
                }
                disabled={move.isPending || del.isPending || enqueue.isPending}
              />
            ))}
          </ul>
        )}
        {(move.error || del.error || enqueue.error) && (
          <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
            {String(
              (move.error ?? del.error ?? enqueue.error)?.message ?? "Error",
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Una fila de archivo con acciones contextuales según la carpeta
// ---------------------------------------------------------------------------
function FileRow({
  file,
  userId,
  needsScript,
  onMove,
  onDelete,
  onEnqueue,
  disabled,
}: {
  file: FolderFile;
  userId: string;
  needsScript: boolean;
  onMove: (dst: FolderName) => void;
  onDelete: () => void;
  onEnqueue: (script: string) => void;
  disabled: boolean;
}) {
  const [previewOpen, setPreviewOpen] = useState(false);
  return (
    <li className="rounded-md border bg-card/40 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <FileVideo className="h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{file.filename}</p>
          <p className="text-[10px] text-muted-foreground">
            {formatBytes(file.size_bytes)} ·{" "}
            {formatRelative(file.modified_at)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setPreviewOpen((v) => !v)}
          aria-label="Preview"
        >
          {previewOpen ? (
            <PlayCircle className="h-3.5 w-3.5 text-brand-cyan" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
        </Button>

        {file.folder === "entrada" && (
          <EnqueueAction
            filename={file.filename}
            needsScript={needsScript}
            onEnqueue={onEnqueue}
            disabled={disabled}
          />
        )}

        {file.folder === "recuperacion" && (
          <MoveAction
            label="Re-editar"
            icon={ArrowLeft}
            confirmTitle={`¿Mover a entrada para re-editar?`}
            confirmBody={`Devuelve "${file.filename}" a entrada/ — podrás encolarlo de nuevo.`}
            onAction={() => onMove("entrada")}
            disabled={disabled}
          />
        )}

        {file.folder === "salida" && (
          <a
            href={userFilePreviewUrl(userId, file.folder, file.filename)}
            download={file.filename}
            className="inline-flex h-7 items-center gap-1 rounded-md border bg-background px-2 text-xs hover:bg-accent"
            title="Descargar MP4 final"
          >
            <Download className="h-3 w-3" />
            Descargar
          </a>
        )}

        {/* Borrar disponible en TODAS las carpetas (incluso entrada). cola
            queda fuera porque está en procesamiento — borrar mid-process
            rompería el job. */}
        {file.folder !== "cola" && (
          <DeleteAction
            filename={file.filename}
            folder={file.folder}
            onAction={onDelete}
            disabled={disabled}
          />
        )}
      </div>
      {previewOpen && (
        <div className="mt-2 overflow-hidden rounded-md bg-black">
          <video
            src={userFilePreviewUrl(userId, file.folder, file.filename)}
            controls
            className="mx-auto block max-h-[50vh] w-full"
          />
        </div>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Acciones (todas con AlertDialog para confirmación)
// ---------------------------------------------------------------------------
function EnqueueAction({
  filename,
  needsScript,
  onEnqueue,
  disabled,
}: {
  filename: string;
  needsScript: boolean;
  onEnqueue: (script: string) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [script, setScript] = useState("");
  const ready = !needsScript || script.trim().length > 0;
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button
          variant="default"
          size="sm"
          className="h-7 gap-1 bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90"
          disabled={disabled}
        >
          <Rocket className="h-3 w-3" />
          Encolar
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Encolar &ldquo;{filename}&rdquo;?</AlertDialogTitle>
          <AlertDialogDescription>
            Se moverá entrada/ → cola/ y se creará el job con el flow del
            usuario. Tras procesar OK irá a recuperacion/; si falla volverá
            a entrada/.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {needsScript && (
          <div className="space-y-1">
            <p className="text-xs font-medium">
              Guión de referencia (obligatorio — el flow usa
              silence_cutter_scripted)
            </p>
            <Textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              placeholder="Pega aquí lo que el speaker debía decir…"
              rows={6}
              className="text-xs"
            />
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            disabled={!ready}
            onClick={() => {
              onEnqueue(needsScript ? script.trim() : "");
              setScript("");
            }}
          >
            Encolar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function MoveAction({
  label,
  icon: Icon,
  confirmTitle,
  confirmBody,
  onAction,
  disabled,
}: {
  label: string;
  icon: typeof ArrowLeft;
  confirmTitle: string;
  confirmBody: string;
  onAction: () => void;
  disabled: boolean;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1"
          disabled={disabled}
        >
          <Icon className="h-3 w-3" />
          {label}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{confirmTitle}</AlertDialogTitle>
          <AlertDialogDescription>{confirmBody}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={onAction}>Mover</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function DeleteAction({
  filename,
  folder,
  onAction,
  disabled,
}: {
  filename: string;
  folder: FolderName;
  onAction: () => void;
  disabled: boolean;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          disabled={disabled}
          aria-label="Borrar"
        >
          <Trash2 className="h-3.5 w-3.5 text-destructive" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Borrar &ldquo;{filename}&rdquo;?</AlertDialogTitle>
          <AlertDialogDescription>
            Borrado IRREVERSIBLE del archivo en {folder}/. Drive borrará la
            copia local en cuanto sincronice.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive hover:bg-destructive/90"
            onClick={onAction}
          >
            Borrar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatRelative(epoch: number): string {
  if (!epoch) return "—";
  const diffS = Math.floor(Date.now() / 1000 - epoch);
  if (diffS < 60) return "ahora";
  if (diffS < 3600) return `hace ${Math.floor(diffS / 60)} min`;
  if (diffS < 86400) return `hace ${Math.floor(diffS / 3600)} h`;
  return new Date(epoch * 1000).toLocaleDateString();
}
