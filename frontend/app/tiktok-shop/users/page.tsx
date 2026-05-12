"use client";

import { useState } from "react";
import { AlertCircle, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { UserCard } from "@/components/users/UserCard";
import { UserCreateDialog } from "@/components/users/UserCreateDialog";
import { useUsers } from "@/lib/queries/users";

const NICHES = ["__all__", "skincare", "fitness", "hogar", "tech", "moda", "otros"];

export default function ShopUsersPage() {
  const [open, setOpen] = useState(false);
  const [niche, setNiche] = useState<string>("__all__");
  const [statusFilter, setStatusFilter] = useState<string>("__all__");

  const filters = niche === "__all__" ? { limit: 100 } : { limit: 100, niche };
  const users = useUsers(filters);

  const filtered = (users.data?.items ?? []).filter((u) => {
    if (statusFilter === "__all__") return true;
    return u.status === statusFilter;
  });

  return (
    <div className="container mx-auto p-6 md:p-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Usuarios TikTok</h1>
          <p className="text-sm text-muted-foreground">
            Cuentas afiliadas y su estado en el Pilot Program.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Nuevo usuario
        </Button>
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <Select value={niche} onValueChange={setNiche}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Nicho" />
          </SelectTrigger>
          <SelectContent>
            {NICHES.map((n) => (
              <SelectItem key={n} value={n}>
                {n === "__all__" ? "Todos los nichos" : n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Estado" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Todos</SelectItem>
            <SelectItem value="pilot">Pilot</SelectItem>
            <SelectItem value="graduated">Graduados</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {users.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      )}

      {users.isError && (
        <Card>
          <CardContent className="flex items-center gap-3 p-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <div>
              <p className="font-medium">Error cargando usuarios</p>
              <p className="text-sm text-muted-foreground">
                {users.error?.message ?? "Sin detalles"}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {users.data && filtered.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-lg font-medium">
              {users.data.items.length === 0 ? "Sin usuarios todavía" : "Sin resultados"}
            </p>
            <p className="max-w-md text-sm text-muted-foreground">
              {users.data.items.length === 0
                ? "Crea tu primera cuenta TikTok afiliada."
                : "No hay usuarios que coincidan con los filtros actuales."}
            </p>
            {users.data.items.length === 0 && (
              <Button onClick={() => setOpen(true)}>
                <Plus className="h-4 w-4" /> Crear el primero
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {filtered.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((u) => (
            <UserCard key={u.id} user={u} />
          ))}
        </div>
      )}

      <UserCreateDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
