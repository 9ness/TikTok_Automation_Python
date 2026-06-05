"use client";

import {
  CheckCircle2,
  Clock,
  CreditCard,
  FolderOpen,
  Globe,
  Inbox,
  Loader2,
  Plus,
  ShieldCheck,
  Trash2,
  Users as UsersIcon,
  Wand2,
  Zap,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateEditorUser,
  useDeleteEditorUser,
  adminStreamUrl,
  useApproveVideo,
  useEditorSettings,
  useEditorUsers,
  usePendingApprovals,
  useProvisionFromWeb,
  useToggleApproval,
  useUpdateCutoff,
  useUpdateEditorUser,
  useUserFolderCounts,
  useWebAccounts,
} from "@/lib/queries/editor-auto";
import type { EditorUser, WebAccount } from "@/lib/types/editor-auto";
import { cn } from "@/lib/utils";

import { UserBillingPanel } from "./_components/UserBillingPanel";
import { UserFlowEditor } from "./_components/UserFlowEditor";
import { UserFoldersPanel } from "./_components/UserFoldersPanel";
import { UserWebAccountPanel } from "./_components/UserWebAccountPanel";

type RightTab = "flow" | "folders" | "billing";
type UserFilter = "all" | "standard" | "plus" | "pro" | "admin" | "manual";

// Categoría del usuario según el ROL de su cuenta web. Sin cuenta web =
// "manual" (usuario interno creado a mano en el panel).
function userKind(u: EditorUser): Exclude<UserFilter, "all"> {
  const role = u.web_account?.role;
  if (!u.web_account) return "manual";
  if (role === "admin") return "admin";
  if (role === "pro") return "pro";
  if (role === "plus") return "plus";
  return "standard";
}

function matchesFilter(u: EditorUser, f: UserFilter): boolean {
  if (f === "all") return true;
  return userKind(u) === f;
}

export default function EditorAutoUsersPage() {
  const users = useEditorUsers();
  const createUser = useCreateEditorUser();
  const deleteUser = useDeleteEditorUser();

  const [userFilter, setUserFilter] = useState<UserFilter>("all");
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [referredByCode, setReferredByCode] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<RightTab>("folders");

  const handleCreate = async () => {
    if (!name.trim()) return;
    const u = await createUser.mutateAsync({
      name: name.trim(),
      display_name: displayName.trim() || name.trim(),
      description: description.trim(),
      tool_flow: [],
      referred_by_code: referredByCode.trim().toUpperCase() || undefined,
    });
    setName("");
    setDisplayName("");
    setDescription("");
    setReferredByCode("");
    setSelectedUserId(u.id);
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Usuarios — Editor Auto</h1>
        <p className="text-sm text-muted-foreground">
          Cada usuario tiene un flujo único de herramientas que se aplica al
          vídeo input al generar. Las carpetas en Drive viven en
          <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">
            TIKTOK_EDITOR/Usuarios/&lt;nombre&gt;/
          </code>
          con subcarpetas <code>entrada/</code> y <code>salida/</code>.
        </p>
      </header>

      <CutoffSetting />
      <ApprovalSetting />
      <PendingApprovalsCard />

      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        {/* Columna izquierda: crear + listar */}
        <div className="min-w-0 space-y-4">
          <CollapsibleCard
            title={
              <span className="flex items-center gap-2">
                <Plus className="h-4 w-4" />
                Crear usuario
              </span>
            }
          >
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="ea-name">Nombre (carpeta Drive)</Label>
                <Input
                  id="ea-name"
                  placeholder="usuario1"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ea-display">Nombre para mostrar</Label>
                <Input
                  id="ea-display"
                  placeholder="Usuario 1"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ea-desc">Descripción (opcional)</Label>
                <Textarea
                  id="ea-desc"
                  placeholder="Para vídeos de cocina, voz lenta, ..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ea-refcode">Código de referido (opcional)</Label>
                <Input
                  id="ea-refcode"
                  placeholder="ABCD1234"
                  value={referredByCode}
                  onChange={(e) =>
                    setReferredByCode(e.target.value.toUpperCase())
                  }
                  className="font-mono uppercase"
                />
                <p className="text-[10px] text-muted-foreground">
                  Si el cliente fue referido, el código aplica descuento al
                  referidor el mes siguiente.
                </p>
              </div>
              <Button
                className="w-full"
                onClick={handleCreate}
                disabled={!name.trim() || createUser.isPending}
              >
                {createUser.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                Crear
              </Button>
              {createUser.isError && (
                <p className="text-xs text-destructive">
                  {(createUser.error as Error).message}
                </p>
              )}
            </div>
          </CollapsibleCard>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <UsersIcon className="h-4 w-4" />
                Existentes
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {/* Filtro por tipo */}
              {(() => {
                const all = users.data ?? [];
                const c = (k: Exclude<UserFilter, "all">) =>
                  all.filter((u) => userKind(u) === k).length;
                const tabs: { id: UserFilter; label: string }[] = [
                  { id: "all", label: `Todos (${all.length})` },
                  { id: "standard", label: `Estándar (${c("standard")})` },
                  { id: "plus", label: `Plus (${c("plus")})` },
                  { id: "pro", label: `Pro (${c("pro")})` },
                  { id: "admin", label: `Admin (${c("admin")})` },
                  { id: "manual", label: `Manual (${c("manual")})` },
                ];
                return (
                  <div className="flex flex-wrap gap-1.5 pb-1">
                    {tabs.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setUserFilter(t.id)}
                        className={cn(
                          "rounded-full border px-2.5 py-1 text-xs transition-colors",
                          userFilter === t.id
                            ? "border-emerald-500 bg-emerald-500/10 text-foreground"
                            : "border-border text-muted-foreground hover:bg-accent/40",
                        )}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                );
              })()}
              {users.isLoading && (
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
              )}
              {!users.isLoading && (users.data ?? []).length === 0 && (
                <p className="text-sm text-muted-foreground">
                  Aún no hay usuarios. Crea el primero.
                </p>
              )}
              {(users.data ?? [])
                .filter((u) => matchesFilter(u, userFilter))
                .map((u) => (
                  <UserListItem
                    key={u.id}
                    user={u}
                    selected={u.id === selectedUserId}
                    onSelect={() => setSelectedUserId(u.id)}
                    onDelete={() => deleteUser.mutate({ id: u.id })}
                  />
                ))}
              {!users.isLoading &&
                (users.data ?? []).filter((u) => matchesFilter(u, userFilter)).length === 0 &&
                (users.data ?? []).length > 0 && (
                  <p className="py-2 text-center text-xs text-muted-foreground">
                    Ningún usuario en esta categoría.
                  </p>
                )}
            </CardContent>
          </Card>

          <WebAccountsCard onSelectUser={(id) => setSelectedUserId(id)} />
        </div>

        {/* Columna derecha: tabs Flujo / Carpetas del usuario seleccionado */}
        <div className="min-w-0 space-y-3">
          {selectedUserId ? (
            <>
              <div className="flex gap-1.5 rounded-md border bg-card/30 p-1">
                <button
                  type="button"
                  onClick={() => setRightTab("flow")}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs transition-colors sm:text-sm",
                    rightTab === "flow"
                      ? "bg-background font-medium shadow"
                      : "text-muted-foreground hover:bg-accent/40",
                  )}
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Flujo
                </button>
                <button
                  type="button"
                  onClick={() => setRightTab("folders")}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs transition-colors sm:text-sm",
                    rightTab === "folders"
                      ? "bg-background font-medium shadow"
                      : "text-muted-foreground hover:bg-accent/40",
                  )}
                >
                  <FolderOpen className="h-3.5 w-3.5" />
                  Carpetas
                </button>
                <button
                  type="button"
                  onClick={() => setRightTab("billing")}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs transition-colors sm:text-sm",
                    rightTab === "billing"
                      ? "bg-background font-medium shadow"
                      : "text-muted-foreground hover:bg-accent/40",
                  )}
                >
                  <CreditCard className="h-3.5 w-3.5" />
                  Billing
                </button>
              </div>
              {rightTab === "flow" && (
                <UserFlowEditor userId={selectedUserId} />
              )}
              {rightTab === "folders" && (
                <UserFoldersPanel userId={selectedUserId} />
              )}
              {rightTab === "billing" && (
                <div className="space-y-3">
                  <UserBillingPanel userId={selectedUserId} />
                  <UserWebAccountPanel userId={selectedUserId} />
                </div>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                Selecciona un usuario para editar su flujo o gestionar sus
                carpetas.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function UserListItem({
  user,
  selected,
  onSelect,
  onDelete,
}: {
  user: EditorUser;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const toolCount = user.tool_flow.filter((s) => s.enabled).length;
  // Conteos de carpetas — solo el endpoint de counts, refresca cada 30s.
  // Si el endpoint falla (server no actualizado) el badge no aparece y el
  // listado sigue funcionando.
  const counts = useUserFolderCounts(user.id);
  const entrada = counts.data?.counts.entrada ?? 0;
  const salida = counts.data?.counts.salida ?? 0;
  const updateUser = useUpdateEditorUser(user.id);
  const autoOn = Boolean(user.auto_enqueue);
  return (
    <div
      className={`flex items-center gap-2 rounded-md border p-2 text-sm transition-colors ${
        selected ? "border-emerald-500 bg-emerald-500/5" : "hover:bg-accent/40"
      }`}
    >
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        onClick={onSelect}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{user.display_name || user.name}</span>
          {user.web_account ? (
            // Cuenta web: mostramos el ROL (estándar/plus/pro/admin).
            <Badge
              variant="outline"
              className={cn(
                "px-1.5 text-[10px] capitalize",
                user.web_account.role === "admin" && "border-brand-violet/60 text-brand-violet",
                user.web_account.role === "pro" && "border-violet-500/60 text-violet-500",
                user.web_account.role === "plus" && "border-blue-500/60 text-blue-500",
                user.web_account.role === "standard" && "border-slate-400/60 text-slate-500 dark:text-slate-400",
              )}
              title={`Rol web: ${user.web_account.role}`}
            >
              {user.web_account.role === "standard" ? "estándar" : user.web_account.role}
            </Badge>
          ) : user.subscription ? (
            <Badge
              variant="default"
              className="gap-1 bg-emerald-600/90 px-1.5 text-[10px] text-white hover:bg-emerald-600"
              title={`Plan ${user.subscription.plan_name} · ${user.subscription.status}`}
            >
              <CreditCard className="h-2.5 w-2.5" />
              {user.subscription.plan_slug}
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="px-1.5 text-[10px]"
              title="Usuario interno (sin cuenta web) — modo prueba"
            >
              prueba
            </Badge>
          )}
          {autoOn && (
            <Badge
              variant="default"
              className="gap-1 bg-emerald-500/90 px-1.5 text-[10px] text-black hover:bg-emerald-500"
              title="Auto-enqueue activo: el watcher encola vídeos nuevos cada 30s"
            >
              <Zap className="h-2.5 w-2.5" />
              auto
            </Badge>
          )}
          {user.account_email && (
            <Badge
              variant="default"
              className="gap-1 bg-sky-500/90 px-1.5 text-[10px] text-white hover:bg-sky-500"
              title={`Cuenta web vinculada: ${user.account_email}${
                user.web_account ? "" : " (pendiente de login)"
              }`}
            >
              <Globe className="h-2.5 w-2.5" />
              web
            </Badge>
          )}
          {entrada > 0 && (
            <Badge
              variant="default"
              className="gap-1 bg-amber-500/90 px-1.5 text-[10px] text-black hover:bg-amber-500"
              title={`${entrada} vídeo(s) en entrada — pendiente(s) de encolar`}
            >
              <Inbox className="h-2.5 w-2.5" />
              {entrada}
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          <code>{user.name}</code> · {toolCount} tool(s)
          {user.usage && user.usage.daily_limit && user.usage.daily_limit > 0 && (
            <span className="ml-1">
              · {user.usage.daily_videos_used}/{user.usage.daily_limit} hoy
            </span>
          )}
          {/* Vídeos de prueba restantes (cuenta web sin plan) */}
          {user.web_account &&
            !user.web_account.plan_id &&
            user.web_account.role !== "admin" && (
              <span
                className="ml-1 font-medium text-amber-600 dark:text-amber-400"
                title="Vídeos de prueba que le quedan"
              >
                · {user.web_account.trial_videos} prueba
              </span>
            )}
          {salida > 0 && ` · ${salida} en salida`}
        </div>
      </button>
      <div
        className="flex items-center gap-1 px-1"
        title={
          autoOn
            ? "Auto-enqueue ON — el watcher escanea entrada/ cada 30s y encola vídeos automáticamente"
            : "Auto-enqueue OFF — encolas manualmente con el botón Encolar"
        }
      >
        <Zap
          className={cn(
            "h-3 w-3 transition-colors",
            autoOn ? "text-emerald-500" : "text-muted-foreground/40",
          )}
        />
        <Switch
          checked={autoOn}
          disabled={updateUser.isPending}
          onCheckedChange={(checked) => {
            updateUser.mutate(
              { auto_enqueue: checked },
              {
                onSuccess: () => {
                  toast.success(
                    checked
                      ? `Auto-enqueue ACTIVADO para ${user.name}.`
                      : `Auto-enqueue DESACTIVADO para ${user.name}.`,
                  );
                },
                onError: (err) =>
                  toast.error(`Error: ${(err as Error).message}`),
              },
            );
          }}
          aria-label="Auto-enqueue"
        />
      </div>
      <Badge variant="outline" className="text-xs">
        {toolCount}
      </Badge>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        onClick={onDelete}
        aria-label="Eliminar"
      >
        <Trash2 className="h-3.5 w-3.5 text-destructive" />
      </Button>
    </div>
  );
}

function CutoffSetting() {
  const settings = useEditorSettings();
  const update = useUpdateCutoff();
  const [hour, setHour] = useState<string>("");
  const [minute, setMinute] = useState<string>("");

  const curHour = settings.data?.send_cutoff_hour;
  const curMin = settings.data?.send_cutoff_minute ?? 0;
  const hVal = hour !== "" ? hour : curHour != null ? String(curHour) : "";
  const mVal = minute !== "" ? minute : curHour != null ? String(curMin) : "";
  const pad = (n: number) => String(n).padStart(2, "0");
  const unchanged = Number(hVal) === curHour && Number(mVal || 0) === curMin;

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 py-3">
        <Clock className="h-4 w-4 shrink-0 text-red-400" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">Hora de cierre de envíos</p>
          <p className="text-xs text-muted-foreground">
            Los clientes solo pueden mandar a edición un día antes de esta hora
            (Europe/Madrid). Tras el cierre, ese día se bloquea.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Input
            type="number"
            min={0}
            max={23}
            value={hVal}
            onChange={(e) => setHour(e.target.value)}
            className="w-16"
            placeholder="12"
          />
          <span className="text-sm text-muted-foreground">:</span>
          <Input
            type="number"
            min={0}
            max={59}
            value={mVal}
            onChange={(e) => setMinute(e.target.value)}
            className="w-16"
            placeholder="00"
          />
          <Button
            size="sm"
            disabled={update.isPending || hVal === "" || unchanged}
            onClick={() =>
              update.mutate(
                {
                  hour: Math.max(0, Math.min(23, Number(hVal))),
                  minute: Math.max(0, Math.min(59, Number(mVal || 0))),
                },
                {
                  onSuccess: (d) => {
                    toast.success(
                      `Cierre actualizado a las ${d.send_cutoff_hour}:${pad(d.send_cutoff_minute)}.`,
                    );
                    setHour("");
                    setMinute("");
                  },
                  onError: (e) => toast.error((e as Error).message),
                },
              )
            }
          >
            {update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Guardar"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ApprovalSetting() {
  const settings = useEditorSettings();
  const toggle = useToggleApproval();
  const on = settings.data?.manual_approval ?? true;
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 py-3">
        <ShieldCheck className="h-4 w-4 shrink-0 text-brand-violet" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">Aprobación manual antes de entregar</p>
          <p className="text-xs text-muted-foreground">
            Si está activo, los vídeos terminados (≥90) quedan retenidos hasta que
            tú los apruebas abajo. Si lo desactivas, se muestran al cliente solos.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Switch
            checked={on}
            disabled={toggle.isPending || settings.isLoading}
            onCheckedChange={(v) =>
              toggle.mutate(v, {
                onSuccess: (d) =>
                  toast.success(
                    d.manual_approval ? "Aprobación manual activada." : "Aprobación manual desactivada.",
                  ),
                onError: (e) => toast.error((e as Error).message),
              })
            }
          />
          <span className="text-sm text-muted-foreground">{on ? "Activa" : "Inactiva"}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function PendingApprovalsCard() {
  const pending = usePendingApprovals();
  const approve = useApproveVideo();
  const items = pending.data?.pending ?? [];

  if (!items.length) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Inbox className="h-4 w-4 text-amber-500" />
          Pendientes de aprobar ({items.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((it) => (
            <div key={`${it.user_id}-${it.day}-${it.filename}`} className="space-y-2 rounded-xl border border-border p-2">
              <div className="flex items-center justify-between gap-2 px-1 text-xs">
                <span className="truncate font-semibold">{it.user_name}</span>
                <span className="shrink-0 text-muted-foreground">
                  {it.day}{it.score != null ? ` · ${it.score}/100` : ""}
                </span>
              </div>
              <video
                controls
                playsInline
                preload="none"
                src={adminStreamUrl(it.user_id, it.day, it.filename)}
                className="mx-auto aspect-[9/16] max-h-[50vh] w-auto rounded-lg bg-black"
              />
              <Button
                size="sm"
                className="w-full"
                disabled={approve.isPending}
                onClick={() =>
                  approve.mutate(
                    { user_id: it.user_id, day: it.day, filename: it.filename, approve: true },
                    {
                      onSuccess: () => toast.success("Vídeo aprobado — ya lo ve el cliente."),
                      onError: (e) => toast.error((e as Error).message),
                    },
                  )
                }
              >
                <CheckCircle2 className="h-4 w-4" /> Aprobar
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function WebAccountsCard({ onSelectUser }: { onSelectUser: (id: string) => void }) {
  const accounts = useWebAccounts();
  const provision = useProvisionFromWeb();
  const list = accounts.data ?? [];

  return (
    <CollapsibleCard
      title={
        <span className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-sky-500" />
          Cuentas web ({list.length})
        </span>
      }
    >
      <p className="mb-3 text-xs text-muted-foreground">
        Personas registradas en la web (nebulabsmedia.com). Crea su usuario de
        edición para configurarle el flujo de herramientas.
      </p>
      {accounts.isLoading && (
        <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
      )}
      {!accounts.isLoading && list.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Aún no hay cuentas web registradas.
        </p>
      )}
      <div className="space-y-2">
        {list.map((a) => (
          <WebAccountRow
            key={a.email}
            account={a}
            provisioning={provision.isPending}
            onProvision={() =>
              provision.mutate(
                { email: a.email },
                {
                  onSuccess: (u) => {
                    toast.success(`Usuario de edición creado: ${u.name}`);
                    onSelectUser(u.id);
                  },
                  onError: (e) => toast.error((e as Error).message),
                },
              )
            }
            onOpen={() =>
              a.linked_editor_user_id && onSelectUser(a.linked_editor_user_id)
            }
          />
        ))}
      </div>
    </CollapsibleCard>
  );
}

function WebAccountRow({
  account,
  provisioning,
  onProvision,
  onOpen,
}: {
  account: WebAccount;
  provisioning: boolean;
  onProvision: () => void;
  onOpen: () => void;
}) {
  const a = account;
  const linked = Boolean(a.linked_editor_user_id);
  const planLabel = a.role === "admin" ? "admin" : a.plan_id ?? "prueba";
  return (
    <div className="flex items-center gap-2 rounded-md border p-2 text-sm">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sky-500/15 text-xs font-bold text-sky-600">
        {(a.name || a.email).charAt(0).toUpperCase()}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="truncate font-medium">{a.name || a.email.split("@")[0]}</span>
          <Badge variant="outline" className="px-1.5 text-[10px]">{planLabel}</Badge>
          {a.banned && (
            <Badge className="bg-red-500/90 px-1.5 text-[10px] text-white">baneado</Badge>
          )}
        </div>
        <p className="truncate text-xs text-muted-foreground">{a.email}</p>
      </div>
      {linked ? (
        <Button variant="outline" size="sm" className="h-7 shrink-0 text-xs" onClick={onOpen}>
          Abrir
        </Button>
      ) : (
        <Button
          size="sm"
          className="h-7 shrink-0 text-xs"
          disabled={provisioning}
          onClick={onProvision}
        >
          {provisioning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Crear usuario"}
        </Button>
      )}
    </div>
  );
}
