"use client";

import { useState } from "react";
import { Plus, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ProductCard } from "@/components/products/ProductCard";
import { ProductCreateDialog } from "@/components/products/ProductCreateDialog";
import { useProducts } from "@/lib/queries/products";

export default function ShopProductsPage() {
  const [open, setOpen] = useState(false);
  const products = useProducts({ limit: 100 });

  return (
    <div className="container mx-auto p-6 md:p-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Productos TikTok Shop</h1>
          <p className="text-sm text-muted-foreground">
            Catálogo de productos para promocionar.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Nuevo producto
        </Button>
      </div>

      {products.isLoading && <ProductsSkeleton />}

      {products.isError && (
        <Card>
          <CardContent className="flex items-center gap-3 p-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <div>
              <p className="font-medium">Error cargando productos</p>
              <p className="text-sm text-muted-foreground">
                {products.error?.message ?? "Sin detalles"}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {products.data && products.data.items.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-lg font-medium">Sin productos todavía</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Crea tu primer producto para empezar a generar vídeos affiliate.
            </p>
            <Button onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> Crear el primero
            </Button>
          </CardContent>
        </Card>
      )}

      {products.data && products.data.items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {products.data.items.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}

      <ProductCreateDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

function ProductsSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <Card key={i} className="overflow-hidden">
          <Skeleton className="aspect-video w-full rounded-none" />
          <CardContent className="space-y-2 p-4">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
