"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Check, Package, Settings2, User as UserIcon } from "lucide-react";

import { ShopGenerateCards } from "@/components/generate/ShopGenerateCards";
import { Button } from "@/components/ui/button";
import { useProducts } from "@/lib/queries/products";
import { useUsers } from "@/lib/queries/users";
import type { Product } from "@/lib/types/product";
import type { User } from "@/lib/types/user";
import { cn } from "@/lib/utils";

// `useSearchParams` requiere un `<Suspense>` boundary para que Next pueda
// pre-renderizar el shell estático.
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
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 w-32 animate-pulse rounded bg-muted" />
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-3 md:grid-cols-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded bg-muted" />
        ))}
      </div>
    </div>
  );
}

// Persistimos la última selección user+producto en localStorage para que
// al volver al generador no haya que repetir los clicks. URL params
// (?user_id&product_id) tienen prioridad por si compartimos un link.
const LS_KEY = "tiktok_shop_generate.last_selection";

interface LastSelection {
  userId: string;
  productId: string;
}

function readLastSelection(): LastSelection | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.userId === "string" && typeof parsed.productId === "string") {
      return parsed;
    }
  } catch {
    /* corrupted — ignora */
  }
  return null;
}

function writeLastSelection(sel: LastSelection): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(sel));
  } catch {
    /* localStorage lleno o bloqueado — silencia */
  }
}

function ShopGenerateInner() {
  const params = useSearchParams();
  const users = useUsers(
    { limit: 200 },
    { refetchOnMount: "always", staleTime: 0 },
  );
  const products = useProducts(
    { limit: 200 },
    { refetchOnMount: "always", staleTime: 0 },
  );

  const [userId, setUserId] = useState<string>("");
  const [productId, setProductId] = useState<string>("");
  const [hydrated, setHydrated] = useState(false);

  const activeUsers = useMemo(
    () => (users.data?.items ?? []).filter((u) => !u.deleted),
    [users.data],
  );
  const activeProducts = useMemo(
    () => (products.data?.items ?? []).filter((p) => !p.deleted),
    [products.data],
  );

  const selectedUser = activeUsers.find((u) => u.id === userId);
  const assignedSet = useMemo(
    () => new Set(selectedUser?.assigned_products ?? []),
    [selectedUser],
  );
  const eligibleProducts = useMemo(
    () => activeProducts.filter((p) => assignedSet.has(p.id)),
    [activeProducts, assignedSet],
  );

  // Hidratación inicial: URL > localStorage > primer usuario disponible.
  // Solo corre una vez tras cargar usuarios/productos.
  useEffect(() => {
    if (hydrated || users.isLoading || products.isLoading) return;
    if (activeUsers.length === 0) {
      setHydrated(true);
      return;
    }

    const urlUserId = params?.get("user_id") ?? "";
    const urlProductId = params?.get("product_id") ?? "";
    const last = readLastSelection();

    // Prioridad usuario: URL → localStorage → primero de la lista
    let pickUser = "";
    if (urlUserId && activeUsers.some((u) => u.id === urlUserId)) {
      pickUser = urlUserId;
    } else if (last && activeUsers.some((u) => u.id === last.userId)) {
      pickUser = last.userId;
    } else {
      pickUser = activeUsers[0]?.id ?? "";
    }
    setUserId(pickUser);

    // Producto: URL → localStorage si pertenece al user elegido → primero
    // asignado al user
    const user = activeUsers.find((u) => u.id === pickUser);
    const userAssigned = new Set(user?.assigned_products ?? []);
    let pickProduct = "";
    if (urlProductId && userAssigned.has(urlProductId)) {
      pickProduct = urlProductId;
    } else if (
      last &&
      last.userId === pickUser &&
      userAssigned.has(last.productId)
    ) {
      pickProduct = last.productId;
    } else {
      const firstEligible = activeProducts.find((p) => userAssigned.has(p.id));
      pickProduct = firstEligible?.id ?? "";
    }
    setProductId(pickProduct);
    setHydrated(true);
  }, [
    hydrated,
    users.isLoading,
    products.isLoading,
    activeUsers,
    activeProducts,
    params,
  ]);

  // Si el user actual deja de tener el producto asignado, reset.
  useEffect(() => {
    if (productId && selectedUser && !assignedSet.has(productId)) {
      setProductId("");
    }
  }, [productId, selectedUser, assignedSet]);

  // Persistir cada cambio confirmado (con producto válido) en localStorage.
  useEffect(() => {
    if (!hydrated) return;
    if (userId && productId) {
      writeLastSelection({ userId, productId });
    }
  }, [hydrated, userId, productId]);

  function pickUser(id: string): void {
    if (id === userId) return;
    setUserId(id);
    // Al cambiar de cuenta, intentamos preservar el producto si está
    // asignado a la nueva. Si no, auto-elegimos el primero compatible.
    const user = activeUsers.find((u) => u.id === id);
    const userAssigned = new Set(user?.assigned_products ?? []);
    if (productId && userAssigned.has(productId)) return;
    const first = activeProducts.find((p) => userAssigned.has(p.id));
    setProductId(first?.id ?? "");
  }

  const selectedProduct = activeProducts.find((p) => p.id === productId);

  return (
    <div className="container mx-auto space-y-4 p-3 sm:space-y-6 sm:p-6 md:p-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Generador de vídeos</h1>
          <p className="text-sm text-muted-foreground">
            Elige cuenta y producto en 1 clic — se recuerda tu última selección.
          </p>
        </div>
        <Link href="/tiktok-shop/generate/advanced">
          <Button variant="outline" size="sm">
            <Settings2 className="h-4 w-4" />
            Modo avanzado
          </Button>
        </Link>
      </header>

      {/* Selector de cuenta — chips horizontales */}
      <section className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 font-medium">
            <UserIcon className="h-3.5 w-3.5 text-muted-foreground" />
            Cuenta TikTok
            <span className="text-muted-foreground">
              · {activeUsers.length}
            </span>
          </div>
          {selectedUser && (
            <span className="text-[10px] text-muted-foreground">
              Click para cambiar
            </span>
          )}
        </div>
        {users.isLoading ? (
          <div className="flex gap-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-16 w-32 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : activeUsers.length === 0 ? (
          <EmptyState
            text="No hay cuentas TikTok creadas todavía."
            cta="Crear cuenta"
            href="/tiktok-shop/users"
          />
        ) : (
          <div className="-mx-1 flex gap-2 overflow-x-auto pb-1 px-1">
            {activeUsers.map((u) => (
              <UserPill
                key={u.id}
                user={u}
                active={u.id === userId}
                onClick={() => pickUser(u.id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Selector de producto — grid de tarjetas con thumbnail */}
      <section className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 font-medium">
            <Package className="h-3.5 w-3.5 text-muted-foreground" />
            Producto
            {selectedUser && (
              <span className="text-muted-foreground">
                · {eligibleProducts.length} asignado{eligibleProducts.length === 1 ? "" : "s"} a @{selectedUser.username}
              </span>
            )}
          </div>
        </div>
        {!selectedUser ? (
          <p className="rounded-md border border-dashed bg-muted/20 p-3 text-center text-xs text-muted-foreground">
            Elige una cuenta arriba para ver sus productos.
          </p>
        ) : eligibleProducts.length === 0 ? (
          <EmptyState
            text={`@${selectedUser.username} aún no tiene productos asignados.`}
            cta="Asignar producto"
            href={`/tiktok-shop/users/${selectedUser.id}`}
          />
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {eligibleProducts.map((p) => (
              <ProductCardChip
                key={p.id}
                product={p}
                active={p.id === productId}
                onClick={() => setProductId(p.id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Área de generación cuando hay selección completa */}
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
            {!selectedUser
              ? "Elige una cuenta para empezar."
              : "Elige un producto para ver los 4 modos de generación."}
          </p>
        </div>
      )}
    </div>
  );
}

function UserPill({
  user,
  active,
  onClick,
}: {
  user: User;
  active: boolean;
  onClick: () => void;
}) {
  const initials = (user.username || user.display_name || "?")
    .slice(0, 2)
    .toUpperCase();
  const productCount = user.assigned_products?.length ?? 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex shrink-0 items-center gap-2 rounded-md border-2 px-2 py-1.5 text-left transition-all",
        active
          ? "border-emerald-500 bg-emerald-500/10 shadow-sm"
          : "border-muted bg-card hover:border-muted-foreground/40",
      )}
    >
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-bold",
          active
            ? "bg-emerald-500 text-white"
            : "bg-muted text-muted-foreground group-hover:bg-muted-foreground/20",
        )}
      >
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold">@{user.username}</p>
        <p className="truncate text-[10px] text-muted-foreground">
          {user.niche || "—"} · {productCount} prod
        </p>
      </div>
      {active && (
        <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
      )}
    </button>
  );
}

function ProductCardChip({
  product,
  active,
  onClick,
}: {
  product: Product;
  active: boolean;
  onClick: () => void;
}) {
  // Primera foto source como thumbnail. Misma URL pattern que PresetsManager.
  const firstPhoto = product.photos?.source?.[0]?.filename;
  const base =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
  const thumb = firstPhoto
    ? `${base}/api/v1/products/${product.id}/photos/${encodeURIComponent(firstPhoto)}/file${qs}`
    : null;

  const presetCount = product.video_presets?.length ?? 0;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex flex-col gap-1.5 overflow-hidden rounded-md border-2 bg-card p-1.5 text-left transition-all",
        active
          ? "border-emerald-500 ring-2 ring-emerald-500/30"
          : "border-muted hover:border-muted-foreground/40",
      )}
    >
      <div className="relative aspect-square w-full overflow-hidden rounded bg-muted/30">
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={product.name}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Package className="h-6 w-6" />
          </div>
        )}
        {active && (
          <div className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-white shadow">
            <Check className="h-3 w-3" />
          </div>
        )}
        {presetCount > 0 && (
          <span
            className="absolute bottom-1 left-1 rounded bg-black/60 px-1 py-0 text-[9px] font-medium text-white"
            title={`${presetCount} preset${presetCount === 1 ? "" : "s"} guardado${presetCount === 1 ? "" : "s"}`}
          >
            ✨ {presetCount}
          </span>
        )}
      </div>
      <p
        className="line-clamp-2 text-[11px] font-semibold leading-tight"
        title={product.name}
      >
        {product.name}
      </p>
      {product.brand && (
        <p className="truncate text-[10px] text-muted-foreground">
          {product.brand}
        </p>
      )}
    </button>
  );
}

function EmptyState({
  text,
  cta,
  href,
}: {
  text: string;
  cta: string;
  href: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed bg-amber-500/5 p-3 text-xs">
      <span className="text-amber-700 dark:text-amber-300">{text}</span>
      <Link href={href}>
        <Button size="sm" variant="outline">
          {cta}
        </Button>
      </Link>
    </div>
  );
}
