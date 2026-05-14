"use client";

import {
  AlertCircle,
  ArrowLeft,
  Download,
  FileText,
  FileVideo,
  FolderInput,
  FolderOpen,
  Info,
  Loader2,
  Mail,
  Play,
  PlayCircle,
  Rocket,
  RotateCcw,
  Share2,
  Trash2,
  UserPlus,
  X,
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
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateUserShare,
  useDeleteUserFile,
  useEditorUser,
  useEnqueueFromEntrada,
  useMoveUserFile,
  useRevokeUserShare,
  useSharingStatus,
  useUserFolders,
  useUserShares,
  userFilePreviewUrl,
} from "@/lib/queries/editor-auto";
import type {
  DriveShare,
  FolderFile,
  FolderName,
} from "@/lib/types/editor-auto";
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

        {/* Sección de sharing con emails concretos (Google Drive) */}
        <SharingSection userId={userId} userName={user.data?.name ?? ""} />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sección "Personas con acceso" — comparte entrada+salida con un email
// ---------------------------------------------------------------------------
function SharingSection({
  userId,
  userName,
}: {
  userId: string;
  userName: string;
}) {
  const status = useSharingStatus();
  const shares = useUserShares(userId);
  const create = useCreateUserShare(userId);
  const revoke = useRevokeUserShare(userId);

  const [email, setEmail] = useState("");
  const [showAll, setShowAll] = useState(false);

  // Drive devuelve los mismos perms en `entrada` y `salida` (si compartiste
  // ambas con el mismo email). Agrupamos por email para no duplicar visualmente.
  const grouped = groupSharesByEmail(shares.data?.shares);
  const visible = showAll ? grouped : grouped.slice(0, 4);

  if (status.isLoading) {
    return (
      <div className="rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
        <Loader2 className="mr-2 inline h-3 w-3 animate-spin" />
        Comprobando configuración de sharing…
      </div>
    );
  }

  if (!status.data?.configured) {
    return (
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-300">
          <AlertCircle className="h-3.5 w-3.5" />
          Sharing de Drive no configurado
        </div>
        <p className="text-muted-foreground">
          Falta el Service Account JSON en{" "}
          <code className="rounded bg-muted px-1">secrets/google-sa.json</code>{" "}
          del server. Ver guía en{" "}
          <code className="rounded bg-muted px-1">deploy/DRIVE_SHARING.md</code>.
        </p>
      </div>
    );
  }

  const handleShare = async () => {
    const e = email.trim().toLowerCase();
    if (!e) return;
    await create.mutateAsync({
      email: e,
      folders: ["entrada", "salida"],
      role: "reader",
      notify: true,
    });
    setEmail("");
  };

  return (
    <div className="space-y-2 rounded-md border bg-muted/20 p-3">
      <div className="flex items-center gap-2">
        <Share2 className="h-3.5 w-3.5 text-brand-cyan" />
        <p className="flex-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Personas con acceso
        </p>
        {shares.isFetching && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        )}
      </div>
      <p className="flex items-start gap-1.5 text-[10px] text-muted-foreground">
        <Info className="mt-0.5 h-2.5 w-2.5 shrink-0" />
        Le doy acceso de SOLO LECTURA a <code>entrada/</code> y{" "}
        <code>salida/</code> de <code>{userName}</code>. La persona recibe un
        email de Google Drive con el link.
      </p>

      {/* Form: añadir nuevo */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Mail className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@gmail.com"
            className="h-8 pl-7 text-xs"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleShare();
            }}
          />
        </div>
        <Button
          size="sm"
          className="h-8 gap-1 bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90"
          onClick={handleShare}
          disabled={!email.trim() || create.isPending}
        >
          {create.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <UserPlus className="h-3 w-3" />
          )}
          Compartir
        </Button>
      </div>
      {create.error && (
        <p className="text-[10px] text-destructive">
          {(create.error as Error).message}
        </p>
      )}

      {/* Lista de compartidos actuales */}
      {grouped.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">
          Nadie tiene acceso aún.
        </p>
      ) : (
        <ul className="space-y-1">
          {visible.map((g) => (
            <li
              key={g.email}
              className="flex items-center gap-2 rounded-md border bg-card/40 px-2 py-1 text-xs"
            >
              <Mail className="h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate">{g.email}</span>
              <span className="flex gap-1">
                {(["entrada", "salida"] as FolderName[]).map((f) => {
                  const has = g.folders[f];
                  return has ? (
                    <span
                      key={f}
                      className="rounded bg-emerald-500/15 px-1 text-[9px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400"
                      title={`acceso ${has.role}`}
                    >
                      {f}
                    </span>
                  ) : null;
                })}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                title="Revocar acceso"
                disabled={revoke.isPending}
                onClick={async () => {
                  for (const folder of ["entrada", "salida"] as FolderName[]) {
                    const s = g.folders[folder];
                    if (s) {
                      await revoke.mutateAsync({
                        permission_id: s.permission_id,
                        folder,
                      });
                    }
                  }
                }}
              >
                <X className="h-3 w-3 text-destructive" />
              </Button>
            </li>
          ))}
          {grouped.length > 4 && !showAll && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              +{grouped.length - 4} más
            </button>
          )}
        </ul>
      )}
      {revoke.error && (
        <p className="text-[10px] text-destructive">
          {(revoke.error as Error).message}
        </p>
      )}
    </div>
  );
}

interface GroupedShare {
  email: string;
  folders: Partial<Record<FolderName, DriveShare>>;
}

function groupSharesByEmail(
  shares: Record<FolderName, DriveShare[]> | undefined,
): GroupedShare[] {
  if (!shares) return [];
  const byEmail = new Map<string, GroupedShare>();
  for (const folder of Object.keys(shares) as FolderName[]) {
    for (const s of shares[folder] ?? []) {
      const email = s.email ?? "(sin email)";
      const existing = byEmail.get(email) ?? { email, folders: {} };
      existing.folders[folder] = s;
      byEmail.set(email, existing);
    }
  }
  return Array.from(byEmail.values()).sort((a, b) =>
    a.email.localeCompare(b.email),
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
  const hasScript = Boolean(file.script);
  return (
    <li className="rounded-md border bg-card/40 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <FileVideo className="h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-sm font-medium">
              {file.filename}
            </span>
            {hasScript && (
              <span
                className="inline-flex shrink-0 items-center gap-1 rounded bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-violet-600 dark:text-violet-300"
                title={`Guión asociado: ${file.script!.filename} (${formatBytes(file.script!.size_bytes)})`}
              >
                <FileText className="h-2.5 w-2.5" />
                guión
              </span>
            )}
          </div>
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
            scriptCompanion={file.script?.filename ?? null}
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
  scriptCompanion,
  onEnqueue,
  disabled,
}: {
  filename: string;
  needsScript: boolean;
  /** Nombre del `.txt` companion si existe en la carpeta (el backend lo
   *  detecta automáticamente al listar). Cuando existe, no pedimos
   *  textarea — el backend lo lee al encolar. */
  scriptCompanion: string | null;
  onEnqueue: (script: string) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [script, setScript] = useState("");
  // Necesitamos guión SOLO si el flow lo pide Y no hay companion .txt.
  // Si hay companion, dejamos `script` vacío y el backend lo lee del .txt.
  const needsManualScript = needsScript && !scriptCompanion;
  const ready = !needsManualScript || script.trim().length > 0;
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
        {needsScript && scriptCompanion && (
          <div className="rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2 text-xs text-emerald-700 dark:text-emerald-300">
            <p className="flex items-center gap-1.5 font-medium">
              <FileText className="h-3 w-3" />
              Guión detectado: <code>{scriptCompanion}</code>
            </p>
            <p className="mt-0.5 text-[10px] opacity-80">
              El backend lo leerá automáticamente al encolar. Ambos archivos
              se mueven juntos por todo el flujo.
            </p>
          </div>
        )}
        {needsManualScript && (
          <div className="space-y-1">
            <p className="text-xs font-medium">
              Guión de referencia (obligatorio — el flow usa
              silence_cutter_scripted)
            </p>
            <p className="text-[10px] text-muted-foreground">
              Tip: la próxima vez puedes subir{" "}
              <code>{filename.replace(/\.[^.]+$/, ".txt")}</code> junto al
              vídeo en entrada/ y se detectará solo.
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
              onEnqueue(needsManualScript ? script.trim() : "");
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
