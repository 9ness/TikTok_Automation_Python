"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Bookmark,
  Check,
  Package,
  Plus,
  Settings2,
  User as UserIcon,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

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
// Lista de "entradas rápidas" — combos user+producto pineados por el user.
// Se muestran arriba como cards de 1 click.
const LS_SHORTCUTS_KEY = "tiktok_shop_generate.shortcuts";
const MAX_SHORTCUTS = 8;

interface LastSelection {
  userId: string;
  productId: string;
}

interface Shortcut {
  userId: string;
  productId: string;
  /** Timestamp ISO de cuando se creó — sirve para ordenar más recientes
   *  arriba si crecemos a muchos shortcuts. */
  created_at: string;
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

function readShortcuts(): Shortcut[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LS_SHORTCUTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (s) =>
          s &&
          typeof s.userId === "string" &&
          typeof s.productId === "string",
      )
      .map((s) => ({
        userId: s.userId,
        productId: s.productId,
        created_at: typeof s.created_at === "string" ? s.created_at : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}

function writeShortcuts(list: Shortcut[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_SHORTCUTS_KEY, JSON.stringify(list));
  } catch {
    /* silencia */
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
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([]);

  // Cargar shortcuts una sola vez en mount (cliente only — localStorage).
  useEffect(() => {
    setShortcuts(readShortcuts());
  }, []);

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

  /** Pin del combo actual user+producto como shortcut de 1 click. */
  const addShortcut = useCallback((): void => {
    if (!userId || !productId) return;
    const exists = shortcuts.some(
      (s) => s.userId === userId && s.productId === productId,
    );
    if (exists) {
      toast.info("Ya tienes esta entrada rápida guardada.");
      return;
    }
    if (shortcuts.length >= MAX_SHORTCUTS) {
      toast.error(
        `Máximo ${MAX_SHORTCUTS} entradas rápidas — borra alguna antes.`,
      );
      return;
    }
    const next: Shortcut[] = [
      ...shortcuts,
      { userId, productId, created_at: new Date().toISOString() },
    ];
    setShortcuts(next);
    writeShortcuts(next);
    toast.success("Entrada rápida guardada.");
  }, [userId, productId, shortcuts]);

  const removeShortcut = useCallback(
    (s: Shortcut): void => {
      const next = shortcuts.filter(
        (x) => !(x.userId === s.userId && x.productId === s.productId),
      );
      setShortcuts(next);
      writeShortcuts(next);
    },
    [shortcuts],
  );

  function pickShortcut(s: Shortcut): void {
    // Validamos que ambos siguen vivos y el producto sigue asignado.
    const user = activeUsers.find((u) => u.id === s.userId);
    if (!user) {
      toast.error("Esa cuenta ya no existe. Quita la entrada rápida.");
      return;
    }
    const userAssigned = new Set(user.assigned_products ?? []);
    if (!userAssigned.has(s.productId)) {
      toast.error(
        "Ese producto ya no está asignado a la cuenta. Quita la entrada rápida.",
      );
      return;
    }
    setUserId(s.userId);
    setProductId(s.productId);
  }

  const selectedProduct = activeProducts.find((p) => p.id === productId);
  const currentComboSaved = shortcuts.some(
    (s) => s.userId === userId && s.productId === productId,
  );

  return (
    <div className="container mx-auto space-y-4 p-3 sm:space-y-6 sm:p-6 md:p-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Generador de vídeos</h1>
          <p className="text-sm text-muted-foreground">
            Entrada rápida en 1 clic — o elige cuenta y producto a mano.
          </p>
        </div>
        <Link href="/tiktok-shop/generate/advanced">
          <Button variant="outline" size="sm">
            <Settings2 className="h-4 w-4" />
            Modo avanzado
          </Button>
        </Link>
      </header>

      {/* Entradas rápidas: combos user+producto guardados que se aplican
          en 1 clic. Aparece si hay alguna O si el combo actual no está
          guardado todavía (para mostrar el botón Guardar). */}
      {(shortcuts.length > 0 ||
        (userId && productId && !currentComboSaved)) && (
        <section className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-1.5 font-medium">
              <Zap className="h-3.5 w-3.5 text-amber-500" />
              Entradas rápidas
              {shortcuts.length > 0 && (
                <span className="text-muted-foreground">
                  · {shortcuts.length}/{MAX_SHORTCUTS}
                </span>
              )}
            </div>
            {userId && productId && !currentComboSaved && (
              <button
                type="button"
                onClick={addShortcut}
                className="flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 hover:bg-amber-500/20 dark:text-amber-300"
                title="Guarda esta combinación cuenta+producto como entrada rápida"
              >
                <Plus className="h-3 w-3" />
                Guardar combo actual
              </button>
            )}
          </div>
          {shortcuts.length === 0 ? (
            <p className="rounded-md border border-dashed bg-amber-500/5 p-2 text-[11px] text-amber-700 dark:text-amber-300">
              <Bookmark className="mr-1 inline h-3 w-3" />
              Guarda combos cuenta+producto que uses a menudo — aparecerán
              aquí como tarjetas de 1 clic.
            </p>
          ) : (
            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
              {shortcuts.map((s) => {
                const user = activeUsers.find((u) => u.id === s.userId);
                const product = activeProducts.find(
                  (p) => p.id === s.productId,
                );
                const stale =
                  !user ||
                  !product ||
                  !(user.assigned_products ?? []).includes(s.productId);
                const isActive =
                  s.userId === userId && s.productId === productId;
                return (
                  <ShortcutCard
                    key={`${s.userId}__${s.productId}`}
                    user={user}
                    product={product}
                    stale={stale}
                    active={isActive}
                    onClick={() => pickShortcut(s)}
                    onRemove={() => removeShortcut(s)}
                  />
                );
              })}
            </div>
          )}
        </section>
      )}

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

function ShortcutCard({
  user,
  product,
  stale,
  active,
  onClick,
  onRemove,
}: {
  user: User | undefined;
  product: Product | undefined;
  stale: boolean;
  active: boolean;
  onClick: () => void;
  onRemove: () => void;
}) {
  // Si user/product están borrados o el producto ya no está asignado al
  // user, marcamos la card como "stale" — visualmente apagada + tooltip
  // explicativo + un X destacado para que el user la limpie.
  const initials = (user?.username || user?.display_name || "?")
    .slice(0, 2)
    .toUpperCase();
  const firstPhoto = product?.photos?.source?.[0]?.filename;
  const base =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
    "http://localhost:8000";
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
  const thumb =
    product && firstPhoto
      ? `${base}/api/v1/products/${product.id}/photos/${encodeURIComponent(firstPhoto)}/file${qs}`
      : null;

  const titleText = stale
    ? "Esta entrada rápida ya no es válida (cuenta o producto borrado/desasignado). Pulsa la X para quitarla."
    : `Cuenta: @${user?.username ?? "?"} · Producto: ${product?.name ?? "?"}`;

  return (
    <div
      className={cn(
        "group relative flex shrink-0 items-center gap-2 rounded-md border-2 bg-card p-1.5 transition-all",
        active && !stale && "border-emerald-500 bg-emerald-500/10 shadow-sm",
        !active && !stale && "border-amber-500/40 hover:border-amber-500",
        stale && "border-muted opacity-50 grayscale",
      )}
      title={titleText}
    >
      <button
        type="button"
        onClick={onClick}
        disabled={stale}
        className="flex min-w-0 items-center gap-2 text-left disabled:cursor-not-allowed"
      >
        {/* Avatar usuario */}
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
            active && !stale
              ? "bg-emerald-500 text-white"
              : "bg-amber-500/20 text-amber-700 dark:text-amber-300",
          )}
        >
          {initials}
        </div>
        {/* Thumbnail producto */}
        <div className="h-9 w-9 shrink-0 overflow-hidden rounded bg-muted/40">
          {thumb ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={thumb}
              alt={product?.name ?? ""}
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Package className="h-4 w-4" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1 pr-1">
          <p className="truncate text-[11px] font-semibold">
            @{user?.username ?? "—"}
          </p>
          <p className="truncate text-[10px] text-muted-foreground">
            {stale ? "Combo inválido" : (product?.name ?? "—")}
          </p>
        </div>
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors",
          stale
            ? "bg-red-500/20 text-red-700 hover:bg-red-500/40 dark:text-red-300"
            : "bg-muted/50 text-muted-foreground opacity-0 hover:bg-muted hover:text-foreground group-hover:opacity-100",
        )}
        title="Quitar entrada rápida"
        aria-label="Quitar entrada rápida"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
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
