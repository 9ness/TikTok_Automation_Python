"use client";

import Link from "next/link";
import { useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { useProducts } from "@/lib/queries/products";
import { useAssignProduct, useUnassignProduct } from "@/lib/queries/users";
import type { User } from "@/lib/types/user";

export function AssignedProductsList({ user }: { user: User }) {
  const products = useProducts({ limit: 200 });
  const assign = useAssignProduct(user.username);
  const unassign = useUnassignProduct(user.username);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickedId, setPickedId] = useState<string | undefined>();

  const allItems = products.data?.items ?? [];
  const assignedSet = new Set(user.assigned_products);
  const assigned = allItems.filter((p) => assignedSet.has(p.id));
  const available = allItems.filter((p) => !assignedSet.has(p.id) && !p.deleted);

  async function handleAssign() {
    if (!pickedId) return;
    try {
      await assign.mutateAsync({ productId: pickedId });
      toast.success("Producto asignado.");
      setPickerOpen(false);
      setPickedId(undefined);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al asignar.";
      toast.error(message);
    }
  }

  async function handleUnassign(productId: string) {
    try {
      await unassign.mutateAsync({ productId });
      toast.success("Producto desasignado.");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al desasignar.";
      toast.error(message);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Productos asignados ({assigned.length})</h3>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPickerOpen(true)}
            disabled={available.length === 0 || products.isLoading}
          >
            <Plus className="h-4 w-4" /> Asignar
          </Button>
        </div>

        {assigned.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin productos asignados.</p>
        ) : (
          <ul className="space-y-2">
            {assigned.map((p) => (
              <li
                key={p.id}
                className="flex items-center justify-between gap-2 rounded-md border bg-card/50 p-2"
              >
                <Link
                  href={`/tiktok-shop/products/${p.id}` as never}
                  className="flex-1 truncate"
                >
                  <p className="truncate text-sm font-medium">{p.name}</p>
                  <p className="truncate font-mono text-xs text-muted-foreground">
                    {p.slug}
                  </p>
                </Link>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => handleUnassign(p.id)}
                  disabled={unassign.isPending}
                  aria-label={`Desasignar ${p.name}`}
                >
                  {unassign.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <X className="h-4 w-4" />
                  )}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Asignar producto</DialogTitle>
            <DialogDescription>
              Selecciona un producto del catálogo para asignárselo a {user.username}.
            </DialogDescription>
          </DialogHeader>
          <Select value={pickedId} onValueChange={setPickedId}>
            <SelectTrigger>
              <SelectValue placeholder="Producto" />
            </SelectTrigger>
            <SelectContent>
              {available.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name} ({p.slug})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPickerOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleAssign} disabled={!pickedId || assign.isPending}>
              {assign.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Asignar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
