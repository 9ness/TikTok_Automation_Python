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
import { useEffect, useRef, useState } from "react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  useCreateUserShare,
  useDeleteUserFile,
  useEditorUser,
  useEnqueueFromEntrada,
  useForgetKnownEmail,
  useMoveUserFile,
  useReleaseDay,
  useRevokeUserShare,
  useSharingStatus,
  useUpdateEditorUser,
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

import { ManualEditor } from "@/components/editor-auto/ManualEditor";
import { Sparkles } from "lucide-react";


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

  const update = useUpdateEditorUser(userId);
  const release = useReleaseDay(userId);

  const [active, setActive] = useState<FolderName>("entrada");
  // Vídeo de salida abierto en el editor de retoque manual (overlay).
  const [retouching, setRetouching] = useState<string | null>(null);
  // Config por usuario (delay + máx/día). Sync desde el server al cargar.
  const [delayMin, setDelayMin] = useState("");
  const [maxDay, setMaxDay] = useState("");
  useEffect(() => {
    if (user.data) {
      setDelayMin(String(user.data.auto_enqueue_delay_minutes ?? 0));
      setMaxDay(
        user.data.daily_video_limit_override == null
          ? ""
          : String(user.data.daily_video_limit_override),
      );
    }
  }, [user.data?.id, user.data?.auto_enqueue_delay_minutes, user.data?.daily_video_limit_override]);

  const counts = folders.data?.counts ?? {
    entrada: 0,
    cola: 0,
    recuperacion: 0,
    salida: 0,
  };
  const items = folders.data?.folders[active] ?? [];
  const usedToday = user.data?.usage?.daily_videos_used ?? 0;

  function saveConfig() {
    const d = Math.max(0, parseInt(delayMin || "0", 10) || 0);
    const m = maxDay.trim() === "" ? -1 : Math.max(0, parseInt(maxDay, 10) || 0);
    update.mutate(
      { auto_enqueue_delay_minutes: d, daily_video_limit_override: m },
      {
        onSuccess: () => toast.success("Ajustes guardados"),
        onError: (e) => toast.error(e.message),
      },
    );
  }

  async function markDayReady() {
    try {
      const r = await release.mutateAsync(undefined);
      if (r.warning) {
        toast.warning(r.warning);
      } else {
        const emailNote = r.email?.ok
          ? ` · email enviado (${r.email.sent})`
          : r.email?.error
            ? ` · email no enviado: ${r.email.error}`
            : "";
        toast.success(`Carpeta compartida con ${r.shared.length} email(s)${emailNote}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  return (
    <>
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
        <p className="break-all text-xs text-muted-foreground">
          {folders.data?.user_name &&
            `Drive: TIKTOK_EDITOR/Usuarios/${folders.data.user_name}/`}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Config por usuario: delay de encolado + máx vídeos/día */}
        <div className="space-y-2 rounded-md border border-cyan-500/30 bg-cyan-500/5 p-2.5">
          <p className="text-xs font-semibold text-cyan-700 dark:text-cyan-300">
            ⚙️ Ajustes de encolado (vacío = sin restricción)
          </p>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground">
                ⏱ Delay auto-encolado (min)
              </label>
              <Input
                type="number"
                min={0}
                value={delayMin}
                onChange={(e) => setDelayMin(e.target.value)}
                placeholder="0"
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground">
                🎬 Máx vídeos/día
              </label>
              <Input
                type="number"
                min={0}
                value={maxDay}
                onChange={(e) => setMaxDay(e.target.value)}
                placeholder="sin límite"
                className="h-8 text-sm"
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={saveConfig} disabled={update.isPending} className="h-7">
              {update.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Guardar ajustes"}
            </Button>
            <span className="text-[11px] text-muted-foreground">
              Hoy: <strong>{usedToday}</strong>
              {maxDay.trim() !== "" ? ` / ${maxDay}` : ""} vídeo(s)
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground">
            El delay es la cuenta atrás antes de auto-encolar un vídeo nuevo
            (puedes encolar a mano antes desde la pestaña entrada). El máx/día
            se resetea a medianoche.
          </p>
        </div>

        {/* Marcar día listo: comparte salida + email aviso */}
        <Button
          variant="outline"
          size="sm"
          onClick={markDayReady}
          disabled={release.isPending}
          className="h-auto min-h-9 w-full items-center whitespace-normal py-2 text-center text-xs leading-snug border-emerald-500/40 text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300"
        >
          {release.isPending ? (
            <Loader2 className="mr-2 h-3.5 w-3.5 shrink-0 animate-spin" />
          ) : (
            <Mail className="mr-2 h-3.5 w-3.5 shrink-0" />
          )}
          <span>
            ✅ Marcar vídeos del día como listos{" "}
            <span className="text-emerald-600/70 dark:text-emerald-400/70">
              (comparte salida + avisa por email)
            </span>
          </span>
        </Button>
        {(() => {
          const rel = user.data?.output_released_on;
          const today = new Date().toISOString().slice(0, 10);
          if (rel && rel === today) {
            return (
              <p className="text-[10px] text-emerald-600 dark:text-emerald-400">
                🔓 Acceso a salida ACTIVO hoy · se revoca solo al cambiar de día.
              </p>
            );
          }
          if (rel) {
            return (
              <p className="text-[10px] text-muted-foreground">
                🔒 Acceso de un día anterior — se revocará en el próximo ciclo.
              </p>
            );
          }
          return (
            <p className="text-[10px] text-muted-foreground">
              🔒 Carpeta salida sin acceso compartido ahora mismo.
            </p>
          );
        })()}

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

        {/* Descripción de la carpeta activa + acción batch (solo en entrada/) */}
        <div className="flex flex-wrap items-center gap-2">
          <p className="flex-1 text-[11px] text-muted-foreground">
            {FOLDERS.find((f) => f.id === active)?.description}
          </p>
          {active === "entrada" && items.length > 1 && (
            <BatchEnqueueButton
              files={items}
              disabled={enqueue.isPending}
              onEnqueueOne={(filename, script) =>
                enqueue.mutateAsync({ filename, script })
              }
            />
          )}
        </div>

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
                onRetouch={() => setRetouching(f.filename)}
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
    {retouching && (
      <ManualEditor
        userId={userId}
        filename={retouching}
        onClose={() => setRetouching(null)}
      />
    )}
    </>
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
  const forget = useForgetKnownEmail(userId);

  const [email, setEmail] = useState("");
  const [showAll, setShowAll] = useState(false);
  // Carpetas seleccionadas por defecto al añadir un nuevo email. Por
  // requerimiento del operador: `entrada` por defecto, `salida` NO — así
  // primero el cliente sube, tú revisas, y solo entonces le das salida.
  const [shareEntrada, setShareEntrada] = useState(true);
  const [shareSalida, setShareSalida] = useState(false);

  // Construimos la lista combinando shares activos + known_emails. Así
  // los gmails que ya usaste alguna vez quedan visibles aunque ahora no
  // tengan ninguna carpeta compartida — un solo click los re-activa.
  const grouped = mergeKnownEmails(
    groupSharesByEmail(shares.data?.shares),
    shares.data?.known_emails ?? [],
  );
  const visible = showAll ? grouped : grouped.slice(0, 6);

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
    const folders: FolderName[] = [];
    if (shareEntrada) folders.push("entrada");
    if (shareSalida) folders.push("salida");
    if (folders.length === 0) return;
    await create.mutateAsync({
      email: e,
      folders,
      role: "reader",
      notify: true,
    });
    setEmail("");
    // Reset a los defaults seguros: solo entrada para el siguiente
    setShareEntrada(true);
    setShareSalida(false);
  };

  // Toggle granular para una persona existente — añade o quita acceso a
  // una sola carpeta sin tocar la otra. La UI usa esto para que puedas
  // dar `salida` solo después de revisar el output.
  const handleToggleFolder = async (g: GroupedShare, folder: FolderName) => {
    const existing = g.folders[folder];
    if (existing) {
      // Revocar solo esa carpeta
      await revoke.mutateAsync({
        permission_id: existing.permission_id,
        folder,
      });
    } else {
      // Conceder solo esa carpeta (sin tocar las demás del email)
      await create.mutateAsync({
        email: g.email,
        folders: [folder],
        role: "reader",
        notify: false, // ya tiene la carpeta hermana — no spam email
      });
    }
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
      <p className="flex items-start gap-1.5 text-[11px] leading-snug text-muted-foreground">
        <Info className="mt-0.5 h-3 w-3 shrink-0" />
        <span>
          Solo lectura. Elige por carpeta si la persona ve <b>entrada</b>,{" "}
          <b>salida</b> o ambas. Recibirá un email de Drive con el link.
        </span>
      </p>

      {/* Form: añadir nuevo */}
      <div className="space-y-1.5">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Mail className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@gmail.com"
              className="h-9 pl-7 text-xs sm:h-8"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleShare();
              }}
            />
          </div>
          <Button
            size="sm"
            className="h-9 gap-1 bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90 sm:h-8"
            onClick={handleShare}
            disabled={
              !email.trim() ||
              create.isPending ||
              (!shareEntrada && !shareSalida)
            }
          >
            {create.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <UserPlus className="h-3 w-3" />
            )}
            Compartir
          </Button>
        </div>
        <div className="flex items-center gap-3 px-0.5">
          <FolderCheckbox
            label="entrada"
            checked={shareEntrada}
            onChange={setShareEntrada}
          />
          <FolderCheckbox
            label="salida"
            checked={shareSalida}
            onChange={setShareSalida}
          />
          {!shareEntrada && !shareSalida && (
            <span className="text-[9px] text-amber-600 dark:text-amber-400">
              elige al menos una carpeta
            </span>
          )}
        </div>
      </div>
      {create.error && (
        <p className="text-[10px] text-destructive">
          {(create.error as Error).message}
        </p>
      )}

      {/* Lista de compartidos + emails recordados */}
      {grouped.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">
          Nadie tiene acceso aún. Añade un email arriba para empezar.
        </p>
      ) : (
        <ul className="space-y-1">
          {visible.map((g) => {
            const hasAnyAccess =
              Boolean(g.folders.entrada) || Boolean(g.folders.salida);
            return (
              <li
                key={g.email}
                className="flex flex-col gap-1.5 rounded-md border bg-card/40 px-2 py-1.5 text-xs sm:flex-row sm:flex-wrap sm:items-center sm:gap-2"
              >
                <div className="flex min-w-0 flex-1 items-center gap-1.5">
                  <Mail className="h-3 w-3 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 break-all">
                    {g.email}
                    {!hasAnyAccess && (
                      <span className="ml-1 text-[9px] uppercase tracking-wider text-muted-foreground">
                        · sin acceso
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex items-center justify-end gap-1 sm:shrink-0">
                  {(["entrada", "salida"] as FolderName[]).map((f) => (
                    <FolderToggle
                      key={f}
                      folder={f}
                      has={Boolean(g.folders[f])}
                      disabled={create.isPending || revoke.isPending}
                      onClick={() => handleToggleFolder(g, f)}
                    />
                  ))}
                  {hasAnyAccess && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 sm:h-6 sm:w-6"
                      title="Revocar TODAS las carpetas (mantiene el email recordado)"
                      disabled={revoke.isPending}
                      onClick={async () => {
                        for (const folder of [
                          "entrada",
                          "salida",
                        ] as FolderName[]) {
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
                      <X className="h-3.5 w-3.5 text-destructive sm:h-3 sm:w-3" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 sm:h-6 sm:w-6"
                    title={
                      hasAnyAccess
                        ? "Revoca primero los accesos para olvidar este email"
                        : "Olvidar email (quita de la agenda)"
                    }
                    disabled={hasAnyAccess || forget.isPending}
                    onClick={() => forget.mutate({ email: g.email })}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive sm:h-3 sm:w-3" />
                  </Button>
                </div>
              </li>
            );
          })}
          {grouped.length > 6 && !showAll && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              +{grouped.length - 6} más
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

/** Mezcla las filas con accesos activos + los emails recordados pero
 *  sin acceso actual. Resultado ordenado: primero los que tienen acceso,
 *  luego los "fríos" — todos alfabéticos dentro de su grupo. */
function mergeKnownEmails(
  active: GroupedShare[],
  knownEmails: string[],
): GroupedShare[] {
  const byEmail = new Map<string, GroupedShare>();
  for (const g of active) byEmail.set(g.email.toLowerCase(), g);
  for (const e of knownEmails) {
    const key = e.toLowerCase();
    if (!byEmail.has(key)) {
      byEmail.set(key, { email: key, folders: {} });
    }
  }
  const all = Array.from(byEmail.values());
  const withAccess = all
    .filter(
      (g) => Boolean(g.folders.entrada) || Boolean(g.folders.salida),
    )
    .sort((a, b) => a.email.localeCompare(b.email));
  const withoutAccess = all
    .filter(
      (g) => !g.folders.entrada && !g.folders.salida,
    )
    .sort((a, b) => a.email.localeCompare(b.email));
  return [...withAccess, ...withoutAccess];
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
  onMove,
  onDelete,
  onEnqueue,
  onRetouch,
  disabled,
}: {
  file: FolderFile;
  userId: string;
  onMove: (dst: FolderName) => void;
  onDelete: () => void;
  onEnqueue: (script: string) => void;
  onRetouch?: () => void;
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

        {/* En cola/ normalmente solo previsualizamos (no tocar lo que
            procesa). PERO si un job se interrumpió (deploy/crash) el
            archivo se queda huérfano en cola — añadimos esta acción
            manual para que el admin lo recupere sin SSH. */}
        {file.folder === "cola" && (
          <MoveAction
            label="Devolver a entrada"
            icon={ArrowLeft}
            confirmTitle={`¿Devolver "${file.filename}" a entrada?`}
            confirmBody="Úsalo solo si el job se quedó atascado tras un deploy/crash. Si está procesando ahora mismo, NO lo muevas — espera a que termine."
            onAction={() => onMove("entrada")}
            disabled={disabled}
          />
        )}

        {file.folder === "salida" && (
          <>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 border-brand-cyan/40 text-brand-cyan hover:bg-brand-cyan/10"
              onClick={onRetouch}
              title="Retocar manualmente (quitar silencios/palabras) y reemplazar"
            >
              <Sparkles className="h-3 w-3" />
              Retocar
            </Button>
            <a
              href={userFilePreviewUrl(userId, file.folder, file.filename)}
              download={file.filename}
              className="inline-flex h-7 items-center gap-1 rounded-md border bg-background px-2 text-xs hover:bg-accent"
              title="Descargar MP4 final"
            >
              <Download className="h-3 w-3" />
              Descargar
            </a>
          </>
        )}

        {/* Borrar disponible en TODAS las carpetas. En cola/ es peligroso
            si hay un job activo procesándolo, pero útil cuando el job
            crasheó y dejó basura — la confirmación deja claro el riesgo. */}
        <DeleteAction
          filename={file.filename}
          folder={file.folder}
          onAction={onDelete}
          disabled={disabled}
        />
      </div>
      {previewOpen && (
        <PreviewVideo
          src={userFilePreviewUrl(userId, file.folder, file.filename)}
        />
      )}
    </li>
  );
}

/** Reproductor de previsualización con selector de velocidad (1x/1.5x/2x)
 *  para repasar los vídeos más rápido. */
function PreviewVideo({ src }: { src: string }) {
  const SPEEDS = [1, 1.5, 2] as const;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [speed, setSpeed] = useState<number>(1);

  function applySpeed(s: number) {
    setSpeed(s);
    const v = videoRef.current;
    if (v) v.playbackRate = s;
  }

  return (
    <div className="mt-2 overflow-hidden rounded-md bg-black">
      <video
        ref={videoRef}
        src={src}
        controls
        onLoadedMetadata={(e) => {
          (e.currentTarget as HTMLVideoElement).playbackRate = speed;
        }}
        className="mx-auto block max-h-[50vh] w-full"
      />
      <div className="flex items-center justify-center gap-1 bg-black/80 px-2 py-1.5">
        <span className="mr-1 text-[10px] text-white/60">Velocidad</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => applySpeed(s)}
            className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
              speed === s
                ? "bg-white text-black"
                : "bg-white/15 text-white hover:bg-white/25"
            }`}
          >
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Acciones (todas con AlertDialog para confirmación)
// ---------------------------------------------------------------------------
function EnqueueAction({
  filename,
  scriptCompanion,
  onEnqueue,
  disabled,
}: {
  filename: string;
  /** Nombre del `.txt` companion si existe en la carpeta (el backend lo
   *  detecta automáticamente al listar). Aquí solo lo usamos para el
   *  tooltip — el backend lee el archivo al encolar. */
  scriptCompanion: string | null;
  onEnqueue: (script: string) => void;
  disabled: boolean;
}) {
  // Encolar directo, sin modal de confirmación: el flow scripted hace
  // fallback automático a modo sin guion si no hay companion `.txt`.
  // Para usar guion manual, el operador sube `<stem>.txt` junto al
  // vídeo en entrada/ y el backend lo lee solo.
  const title = scriptCompanion
    ? `Encolar — guion detectado: ${scriptCompanion}`
    : `Encolar — modo sin guion (sube ${filename.replace(/\.[^.]+$/, ".txt")} para usar modo con guion)`;
  return (
    <Button
      variant="default"
      size="sm"
      className="h-7 gap-1 bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90"
      disabled={disabled}
      title={title}
      onClick={() => onEnqueue("")}
    >
      <Rocket className="h-3 w-3" />
      Encolar
    </Button>
  );
}

/** Botón "Encolar todos N" — solo visible en el tab entrada/ cuando hay
 *  ≥2 vídeos. Procesa secuencialmente cada vídeo con script vacío: el
 *  backend usa el companion `.txt` si existe (detectado al listar) y
 *  cae al modo SIN guion si no. Para encolar con guion manual pegado
 *  por vídeo, sigue habiendo el botón individual de cada fila. */
function BatchEnqueueButton({
  files,
  disabled,
  onEnqueueOne,
}: {
  files: FolderFile[];
  disabled: boolean;
  onEnqueueOne: (filename: string, script: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const withCompanion = files.filter((f) => f.script).length;
  const withoutCompanion = files.length - withCompanion;
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button
          variant="default"
          size="sm"
          className="h-7 gap-1 bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90"
          disabled={disabled || running}
        >
          <Rocket className="h-3 w-3" />
          Encolar todos ({files.length})
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Encolar {files.length} vídeos?</AlertDialogTitle>
          <AlertDialogDescription>
            Se moverán todos de entrada/ → cola/ y se procesarán uno
            detrás de otro. Tras procesar OK irán a recuperacion/; si
            alguno falla volverá a entrada/.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-1 rounded-md border bg-muted/20 p-2 text-xs">
          <p>
            <span className="font-medium text-emerald-600 dark:text-emerald-400">
              ✓ {withCompanion}
            </span>{" "}
            con guion (`.txt` junto al vídeo) — modo premium con diff
          </p>
          <p>
            <span className="font-medium text-muted-foreground">
              ○ {withoutCompanion}
            </span>{" "}
            sin guion — modo VAD/IA con auto-detect estilo
          </p>
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={running}>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            disabled={running}
            onClick={async (e) => {
              // Bloquea el cierre automático del AlertDialog para poder
              // ejecutar todo el batch antes de cerrar.
              e.preventDefault();
              setRunning(true);
              let ok = 0;
              const failed: string[] = [];
              for (const f of files) {
                try {
                  await onEnqueueOne(f.filename, "");
                  ok += 1;
                } catch {
                  failed.push(f.filename);
                }
              }
              setRunning(false);
              setOpen(false);
              if (failed.length === 0) {
                toast.success(`Encolados ${ok} vídeos.`);
              } else if (ok === 0) {
                toast.error(
                  `No se pudo encolar ningún vídeo (${failed.length} fallidos).`,
                );
              } else {
                toast.warning(
                  `Encolados ${ok}/${files.length}. Fallidos: ${failed
                    .slice(0, 3)
                    .join(", ")}${failed.length > 3 ? "…" : ""}`,
                );
              }
            }}
          >
            {running ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" />
                Encolando…
              </>
            ) : (
              `Encolar ${files.length}`
            )}
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
// Subcomponentes del sharing (checkbox del form, toggle por fila)
// ---------------------------------------------------------------------------
function FolderCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer select-none items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider transition-colors",
        checked
          ? "border-brand-cyan/60 bg-brand-cyan/10 text-brand-cyan"
          : "border-muted-foreground/30 text-muted-foreground hover:bg-accent/40",
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only"
      />
      <span
        className={cn(
          "h-2 w-2 rounded-sm border",
          checked
            ? "border-brand-cyan bg-brand-cyan"
            : "border-muted-foreground/50",
        )}
      />
      {label}
    </label>
  );
}

function FolderToggle({
  folder,
  has,
  disabled,
  onClick,
}: {
  folder: FolderName;
  has: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={
        has
          ? `Tiene acceso a ${folder}/ — click para revocar`
          : `Sin acceso a ${folder}/ — click para conceder`
      }
      className={cn(
        "rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider transition-colors disabled:opacity-50",
        has
          ? "bg-emerald-500/15 text-emerald-600 hover:bg-rose-500/15 hover:text-rose-600 dark:text-emerald-400"
          : "bg-muted/40 text-muted-foreground hover:bg-emerald-500/15 hover:text-emerald-600",
      )}
    >
      {has ? "✓ " : "+ "}
      {folder}
    </button>
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
