"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Settings2 } from "lucide-react";

import { ShopGenerateCards } from "@/components/generate/ShopGenerateCards";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useProducts } from "@/lib/queries/products";
import { useUsers } from "@/lib/queries/users";

// `useSearchParams` requiere un `<Suspense>` boundary para que Next pueda
// pre-renderizar el shell estático. Sin esto el `next build` falla con
// "Export encountered errors on /tiktok-shop/generate". Patrón oficial:
// https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout
export default function ShopGeneratePage() {
  return (
    <Suspense fallback={<ShopGenerateLoading />}>
      <ShopGenerateInner />
    </Suspense>
  );
}

function ShopGenerateLoading() {
  return (
    <div className="container mx-auto space-y-4 p-3 sm:space-y-6 sm:p-6 md:p-10">
      <div className="h-8 w-64 animate-pulse rounded bg-muted" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="h-10 animate-pulse rounded bg-muted" />
        <div className="h-10 animate-pulse rounded bg-muted" />
      </div>
    </div>
  );
}

function ShopGenerateInner() {
  const params = useSearchParams();
  // refetchOnMount + staleTime 0 → al volver a la página del generador
  // siempre traemos productos/usuarios frescos del backend. Antes pasaba
  // que tras asignar un producto a un user en otra pestaña, al venir aquí
  // el dropdown salía con la lista cacheada vieja sin el nuevo producto.
  const users = useUsers(
    { limit: 200 },
    { refetchOnMount: "always", staleTime: 0 },
  );
  const products = useProducts(
    { limit: 200 },
    { refetchOnMount: "always", staleTime: 0 },
  );

  const [userId, setUserId] = useState<string>(params?.get("user_id") ?? "");
  const [productId, setProductId] = useState<string>(params?.get("product_id") ?? "");

  const activeUsers = (users.data?.items ?? []).filter((u) => !u.deleted);
  const activeProducts = (products.data?.items ?? []).filter((p) => !p.deleted);

  const selectedUser = activeUsers.find((u) => u.id === userId);
  const assignedSet = new Set(selectedUser?.assigned_products ?? []);
  const eligibleProducts = activeProducts.filter((p) => assignedSet.has(p.id));

  // Auto-reset product si el seleccionado deja de estar asignado al user.
  useEffect(() => {
    if (productId && selectedUser && !assignedSet.has(productId)) {
      setProductId("");
    }
  }, [userId, productId, selectedUser, assignedSet]);

  const selectedProduct = activeProducts.find((p) => p.id === productId);

  return (
    <div className="container mx-auto space-y-4 p-3 sm:space-y-6 sm:p-6 md:p-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Generador de vídeos</h1>
          <p className="text-sm text-muted-foreground">
            Elige usuario + producto, y genera en 1 clic con presets guardados.
          </p>
        </div>
        <Link href="/tiktok-shop/generate/advanced">
          <Button variant="outline" size="sm">
            <Settings2 className="h-4 w-4" />
            Modo avanzado
          </Button>
        </Link>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs">Cuenta TikTok</Label>
          <Select value={userId} onValueChange={setUserId}>
            <SelectTrigger>
              <SelectValue placeholder={users.isLoading ? "Cargando…" : "Selecciona cuenta"} />
            </SelectTrigger>
            <SelectContent>
              {activeUsers.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.username} · {u.niche}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Producto</Label>
          <Select
            value={productId}
            onValueChange={setProductId}
            disabled={!selectedUser}
          >
            <SelectTrigger>
              <SelectValue
                placeholder={
                  !selectedUser
                    ? "Elige cuenta primero"
                    : eligibleProducts.length === 0
                      ? "Sin productos asignados"
                      : "Selecciona producto"
                }
              />
            </SelectTrigger>
            <SelectContent>
              {eligibleProducts.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {selectedUser && selectedProduct ? (
        <ShopGenerateCards
          userId={selectedUser.id}
          username={selectedUser.username}
          productId={selectedProduct.id}
          productName={selectedProduct.name}
        />
      ) : (
        <div className="rounded-md border border-dashed bg-muted/30 p-10 text-center">
          <p className="text-sm text-muted-foreground">
            Elige cuenta y producto para ver los 4 modos de generación con sus presets.
          </p>
        </div>
      )}
    </div>
  );
}
