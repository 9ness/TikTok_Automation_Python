"use client";

import {
  FolderOpen,
  Inbox,
  Loader2,
  Plus,
  Trash2,
  Users as UsersIcon,
  Wand2,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateEditorUser,
  useDeleteEditorUser,
  useEditorUsers,
  useUserFolderCounts,
} from "@/lib/queries/editor-auto";
import type { EditorUser } from "@/lib/types/editor-auto";
import { cn } from "@/lib/utils";

import { UserFlowEditor } from "./_components/UserFlowEditor";
import { UserFoldersPanel } from "./_components/UserFoldersPanel";

type RightTab = "flow" | "folders";

export default function EditorAutoUsersPage() {
  const users = useEditorUsers();
  const createUser = useCreateEditorUser();
  const deleteUser = useDeleteEditorUser();

  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<RightTab>("folders");

  const handleCreate = async () => {
    if (!name.trim()) return;
    const u = await createUser.mutateAsync({
      name: name.trim(),
      display_name: displayName.trim() || name.trim(),
      description: description.trim(),
      tool_flow: [],
    });
    setName("");
    setDisplayName("");
    setDescription("");
    setSelectedUserId(u.id);
  };

  return (
    <div className="space-y-6 p-6">
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

      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        {/* Columna izquierda: crear + listar */}
        <div className="space-y-4">
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
              {users.isLoading && (
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
              )}
              {!users.isLoading && (users.data ?? []).length === 0 && (
                <p className="text-sm text-muted-foreground">
                  Aún no hay usuarios. Crea el primero.
                </p>
              )}
              {(users.data ?? []).map((u) => (
                <UserListItem
                  key={u.id}
                  user={u}
                  selected={u.id === selectedUserId}
                  onSelect={() => setSelectedUserId(u.id)}
                  onDelete={() => deleteUser.mutate({ id: u.id })}
                />
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Columna derecha: tabs Flujo / Carpetas del usuario seleccionado */}
        <div className="space-y-3">
          {selectedUserId ? (
            <>
              <div className="flex gap-1.5 rounded-md border bg-card/30 p-1">
                <button
                  type="button"
                  onClick={() => setRightTab("flow")}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded px-3 py-1.5 text-sm transition-colors",
                    rightTab === "flow"
                      ? "bg-background font-medium shadow"
                      : "text-muted-foreground hover:bg-accent/40",
                  )}
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Flujo de herramientas
                </button>
                <button
                  type="button"
                  onClick={() => setRightTab("folders")}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded px-3 py-1.5 text-sm transition-colors",
                    rightTab === "folders"
                      ? "bg-background font-medium shadow"
                      : "text-muted-foreground hover:bg-accent/40",
                  )}
                >
                  <FolderOpen className="h-3.5 w-3.5" />
                  Carpetas
                </button>
              </div>
              {rightTab === "flow" ? (
                <UserFlowEditor userId={selectedUserId} />
              ) : (
                <UserFoldersPanel userId={selectedUserId} />
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
  return (
    <div
      className={`flex items-center gap-2 rounded-md border p-2 text-sm transition-colors ${
        selected ? "border-emerald-500 bg-emerald-500/5" : "hover:bg-accent/40"
      }`}
    >
      <button
        type="button"
        className="flex-1 text-left"
        onClick={onSelect}
      >
        <div className="flex items-center gap-2">
          <span className="font-medium">{user.display_name || user.name}</span>
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
          {salida > 0 && ` · ${salida} en salida`}
        </div>
      </button>
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
