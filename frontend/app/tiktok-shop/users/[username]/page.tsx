"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import { ArrowLeft, Loader2, Trash2 } from "lucide-react";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AssignedProductsList } from "@/components/users/AssignedProductsList";
import { PilotTracker } from "@/components/users/PilotTracker";
import { UserEditor } from "@/components/users/UserEditor";
import { ApiError } from "@/lib/api";
import { useDeleteUser, useUser } from "@/lib/queries/users";

export default function UserEditorPage({
  params,
}: {
  params: Promise<{ username: string }> | { username: string };
}) {
  const resolvedParams = params instanceof Promise ? use(params) : params;
  const { username: rawUsername } = resolvedParams;
  const username = decodeURIComponent(rawUsername);
  const router = useRouter();
  const user = useUser(username);
  const del = useDeleteUser();
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function handleDelete() {
    try {
      await del.mutateAsync(username);
      toast.success("Usuario eliminado.");
      router.push("/tiktok-shop/users");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al eliminar.";
      toast.error(message);
    }
  }

  if (user.isLoading) {
    return (
      <div className="container mx-auto space-y-4 p-6 md:p-10">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (user.isError || !user.data) {
    return (
      <div className="container mx-auto p-6 md:p-10">
        <Card>
          <CardContent className="space-y-3 py-12 text-center">
            <p className="text-lg font-medium">Usuario no encontrado</p>
            <p className="text-sm text-muted-foreground">
              {user.error?.message ?? "El usuario pudo haber sido eliminado."}
            </p>
            <Button asChild variant="outline">
              <Link href="/tiktok-shop/users">Volver al listado</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const u = user.data;

  return (
    <div className="container mx-auto space-y-6 p-6 md:p-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button asChild size="icon" variant="ghost" aria-label="Volver">
            <Link href="/tiktok-shop/users">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{u.username}</h1>
            <p className="text-xs text-muted-foreground">
              {u.display_name} · {u.niche}
            </p>
          </div>
        </div>

        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" disabled={del.isPending}>
              {del.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Eliminar
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>¿Eliminar el usuario?</AlertDialogTitle>
              <AlertDialogDescription>
                Soft-delete: ocultará la cuenta pero la carpeta Drive y el histórico
                de generaciones se mantienen.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  handleDelete();
                  setConfirmOpen(false);
                }}
              >
                Eliminar
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Datos de la cuenta</CardTitle>
          </CardHeader>
          <CardContent>
            <UserEditor key={u.username} user={u} />
          </CardContent>
        </Card>

        <PilotTracker username={u.username} />
      </div>

      <AssignedProductsList user={u} />
    </div>
  );
}
