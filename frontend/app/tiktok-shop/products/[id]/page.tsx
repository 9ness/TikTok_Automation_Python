"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { use } from "react";
import { ArrowLeft, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Skeleton } from "@/components/ui/skeleton";
import { ProductEditorTabs } from "@/components/products/ProductEditorTabs";
import { ApiError } from "@/lib/api";
import { useDeleteProduct, useProduct } from "@/lib/queries/products";

export default function ProductEditorPage({
  params,
}: {
  params: Promise<{ id: string }> | { id: string };
}) {
  const resolvedParams = params instanceof Promise ? use(params) : params;
  const { id } = resolvedParams;
  const router = useRouter();
  const product = useProduct(id);
  const del = useDeleteProduct();
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function handleDelete() {
    try {
      await del.mutateAsync(id);
      toast.success("Producto eliminado.");
      router.push("/tiktok-shop/products");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al eliminar.";
      toast.error(message);
    }
  }

  if (product.isLoading) {
    return (
      <div className="container mx-auto space-y-4 p-6 md:p-10">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (product.isError || !product.data) {
    return (
      <div className="container mx-auto p-6 md:p-10">
        <Card>
          <CardContent className="space-y-3 py-12 text-center">
            <p className="text-lg font-medium">Producto no encontrado</p>
            <p className="text-sm text-muted-foreground">
              {product.error?.message ?? "El producto pudo haber sido eliminado."}
            </p>
            <Button asChild variant="outline">
              <Link href="/tiktok-shop/products">Volver al catálogo</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const p = product.data;

  return (
    <div className="container mx-auto space-y-4 p-3 sm:p-6 md:space-y-6 md:p-10">
      {/* Header — 1 fila compacta: back · título · eliminar (icon-only en mobile) */}
      <div className="flex items-center gap-2">
        <Button
          asChild
          size="icon"
          variant="ghost"
          aria-label="Volver"
          className="shrink-0"
        >
          <Link href="/tiktok-shop/products">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-base font-bold tracking-tight sm:text-xl md:text-2xl">
            {p.name}
          </h1>
          <p className="truncate font-mono text-[10px] text-muted-foreground sm:text-xs">
            {p.slug} · {p.category}
          </p>
        </div>

        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogTrigger asChild>
            <Button
              variant="destructive"
              size="icon"
              disabled={del.isPending}
              aria-label="Eliminar producto"
              className="shrink-0 sm:size-default sm:[&]:w-auto sm:px-3"
            >
              {del.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              <span className="ml-2 hidden sm:inline">Eliminar</span>
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>¿Eliminar el producto?</AlertDialogTitle>
              <AlertDialogDescription>
                Soft-delete: ocultará el producto del catálogo pero los archivos en Drive y
                el histórico de generaciones se mantienen.
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

      <ProductEditorTabs key={p.id} product={p} />
    </div>
  );
}
