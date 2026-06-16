"use client";

import { useState } from "react";
import { Plus, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ProductCard } from "@/components/products/ProductCard";
import { ProductCreateDialog } from "@/components/products/ProductCreateDialog";
import { useProducts } from "@/lib/queries/products";

type OriginFilter = "all" | "manual" | "radar";

export default function ShopProductsPage() {
  const [open, setOpen] = useState(false);
  const [originFilter, setOriginFilter] = useState<OriginFilter>("all");
  const products = useProducts({ limit: 100 });

  const allItems = products.data?.items ?? [];
  const nManual = allItems.filter((p) => (p.origin ?? "manual") !== "radar").length;
  const nRadar = allItems.filter((p) => (p.origin ?? "manual") === "radar").length;
  const items = allItems.filter((p) =>
    originFilter === "all"
      ? true
      : originFilter === "radar"
        ? (p.origin ?? "manual") === "radar"
        : (p.origin ?? "manual") !== "radar",
  );

  return (
    <div className="container mx-auto p-3 sm:p-6 md:p-10">
      <div className="mb-3 flex items-center justify-between gap-2 sm:mb-6">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold tracking-tight sm:text-2xl">
            Productos TikTok Shop
          </h1>
          <p className="hidden text-sm text-muted-foreground sm:block">
            Catálogo de productos para promocionar.
          </p>
        </div>
        <Button
          onClick={() => setOpen(true)}
          size="sm"
          className="shrink-0 sm:size-default"
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">Nuevo producto</span>
          <span className="sm:hidden">Nuevo</span>
        </Button>
      </div>

      {products.data && allItems.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {(
            [
              ["all", `Todos (${allItems.length})`],
              ["manual", `✍️ Manuales (${nManual})`],
              ["radar", `🔍 Radar (${nRadar})`],
            ] as [OriginFilter, string][]
          ).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setOriginFilter(val)}
              className={
                "rounded-full border px-3 py-1 text-xs transition " +
                (originFilter === val
                  ? "border-orange-500 bg-orange-500/10 font-medium"
                  : "border-border text-muted-foreground hover:border-foreground/40")
              }
            >
              {label}
            </button>
          ))}
        </div>
      )}

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
        <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((p) => (
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
