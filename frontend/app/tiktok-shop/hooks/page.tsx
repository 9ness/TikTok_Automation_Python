"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
  Loader2,
  MessageSquareText,
  Package,
  Sparkles,
  User as UserIcon,
  Wand2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import {
  useGenerateHookVariants,
  useGenerateThemedHooks,
  type HookVariant,
  type HookThemed,
} from "@/lib/queries/hooks";
import { useProduct, useProducts } from "@/lib/queries/products";
import {
  migrateLocalShortcutsIfNeeded,
  useShortcuts,
} from "@/lib/queries/shortcuts";
import { useUsers } from "@/lib/queries/users";
import type { Product, VideoPreset } from "@/lib/types/product";
import { cn } from "@/lib/utils";

const LS_KEY = "tiktokshop_hooks_dest_v1";

interface DestSelection {
  userId: string;
  productId: string;
}

function readDest(): DestSelection | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (p && typeof p.userId === "string" && typeof p.productId === "string") {
      return p;
    }
  } catch {
    /* corrupted */
  }
  return null;
}

function writeDest(sel: DestSelection): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(sel));
  } catch {
    /* silencia */
  }
}

function formatHandle(u: string | null | undefined): string {
  if (!u) return "—";
  return `@${u.replace(/^@+/, "")}`;
}

function copyToClipboard(text: string) {
  if (typeof window === "undefined") return;
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success("Copiado"))
    .catch(() => toast.error("No se pudo copiar"));
}

export default function HooksPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Cargando…</div>}>
      <HooksInner />
    </Suspense>
  );
}

function HooksInner() {
  const searchParams = useSearchParams();
  const usersQ = useUsers({ limit: 200 }, { refetchOnMount: "always" });
  const productsQ = useProducts({ limit: 200 }, { refetchOnMount: "always" });
  const shortcutsQ = useShortcuts();
  const shortcuts = shortcutsQ.data?.items ?? [];

  const [userId, setUserId] = useState<string>("");
  const [productId, setProductId] = useState<string>("");
  const [hydrated, setHydrated] = useState(false);

  // Hidratar destino: URL > localStorage
  useEffect(() => {
    const urlUserId = searchParams?.get("user_id");
    const urlProductId = searchParams?.get("product_id");
    if (urlUserId && urlProductId) {
      setUserId(urlUserId);
      setProductId(urlProductId);
    } else {
      const last = readDest();
      if (last) {
        setUserId(last.userId);
        setProductId(last.productId);
      }
    }
    migrateLocalShortcutsIfNeeded().then((n) => {
      if (n > 0) shortcutsQ.refetch();
    });
    setHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (userId && productId) {
      writeDest({ userId, productId });
    }
  }, [hydrated, userId, productId]);

  const users = usersQ.data?.items ?? [];
  const allProducts = productsQ.data?.items ?? [];
  const selectedUser = useMemo(
    () => users.find((u) => u.id === userId) ?? null,
    [users, userId],
  );
  const userProducts = useMemo(() => {
    if (!selectedUser) return [];
    const assigned = new Set(selectedUser.assigned_products);
    return allProducts.filter((p) => assigned.has(p.id));
  }, [allProducts, selectedUser]);
  const selectedProductLite = useMemo(
    () => userProducts.find((p) => p.id === productId) ?? null,
    [userProducts, productId],
  );

  // Producto completo con video_presets
  const productQ = useProduct(productId || undefined);
  const product: Product | null = (productQ.data as Product | undefined) ?? null;

  // Si cambia el user, reset product si ya no pertenece
  useEffect(() => {
    if (!selectedUser) {
      setProductId("");
      return;
    }
    if (productId && !userProducts.some((p) => p.id === productId)) {
      setProductId("");
    }
  }, [selectedUser, productId, userProducts]);

  const destReady = Boolean(selectedUser && selectedProductLite);

  return (
    <div className="container mx-auto max-w-5xl space-y-4 px-3 py-4 sm:px-6 sm:py-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
          <MessageSquareText className="h-5 w-5 text-amber-500 sm:h-6 sm:w-6" />
          Generador de Hooks
        </h1>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Hooks existentes de tus presets + variantes IA + hooks orientados a
          tema. Para usar copiando manualmente en otros vídeos.
        </p>
      </div>

      {/* Selector cuenta + producto */}
      <Card>
        <CardContent className="space-y-2 p-3 sm:p-4">
          <Label className="text-xs font-semibold sm:text-sm">
            Cuenta + Producto
          </Label>

          {/* Shortcuts */}
          {shortcuts.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground sm:text-[11px]">
                Entradas rápidas
              </Label>
              <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {shortcuts.map((s) => {
                  const u = users.find((x) => x.id === s.user_id);
                  const p = allProducts.find((x) => x.id === s.product_id);
                  if (!u || !p) return null;
                  const active = s.user_id === userId && s.product_id === productId;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => {
                        setUserId(s.user_id);
                        setProductId(s.product_id);
                      }}
                      className={cn(
                        "flex w-full min-w-0 flex-col items-start gap-0.5 overflow-hidden rounded-md border px-2.5 py-2 text-left transition-colors",
                        active
                          ? "border-amber-500 bg-amber-500/10"
                          : "border-muted bg-muted/30 hover:bg-muted/60",
                      )}
                    >
                      <span className="block w-full truncate text-[11px] font-semibold sm:text-xs">
                        {formatHandle(u.username)}
                      </span>
                      <span className="block w-full truncate text-[10px] text-muted-foreground sm:text-[11px]">
                        {p.name}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Selectores manuales */}
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <Label className="text-[10px] text-muted-foreground sm:text-xs">
                <UserIcon className="mr-1 inline h-3 w-3" />
                Cuenta TikTok
              </Label>
              <Select value={userId} onValueChange={setUserId}>
                <SelectTrigger className="h-10 max-w-full text-sm [&>span]:truncate">
                  <SelectValue placeholder="Elige cuenta" />
                </SelectTrigger>
                <SelectContent>
                  {users.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      <span className="block max-w-[18rem] truncate sm:max-w-[24rem]">
                        {formatHandle(u.username)}
                        {u.display_name ? ` · ${u.display_name}` : ""}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-[10px] text-muted-foreground sm:text-xs">
                <Package className="mr-1 inline h-3 w-3" />
                Producto
              </Label>
              <Select
                value={productId}
                onValueChange={setProductId}
                disabled={!selectedUser}
              >
                <SelectTrigger className="h-10 max-w-full text-sm [&>span]:truncate">
                  <SelectValue
                    placeholder={
                      !selectedUser
                        ? "Elige cuenta primero"
                        : userProducts.length === 0
                          ? "Sin productos"
                          : "Elige producto"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {userProducts.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      <span className="block max-w-[18rem] truncate sm:max-w-[24rem]">
                        {p.name}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {!destReady && (
        <Card className="bg-muted/30">
          <CardContent className="p-4 text-center text-xs text-muted-foreground sm:text-sm">
            Elige cuenta + producto para empezar.
          </CardContent>
        </Card>
      )}

      {destReady && product && (
        <>
          <ThemedHooksGenerator product={product} />
          <ExistingHooksSection product={product} />
        </>
      )}

      {destReady && !product && productQ.isLoading && (
        <Card>
          <CardContent className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Cargando producto…
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   THEMED HOOKS — generar N hooks orientados a un tema
   ═══════════════════════════════════════════════════════════════ */
function ThemedHooksGenerator({ product }: { product: Product }) {
  const [theme, setTheme] = useState("");
  const [n, setN] = useState<number>(10);
  const mutation = useGenerateThemedHooks();

  function onGenerate() {
    if (!theme.trim()) {
      toast.error("Escribe un tema o contexto");
      return;
    }
    mutation.mutate({ productId: product.id, theme: theme.trim(), n });
  }

  return (
    <Card className="border-purple-500/40">
      <CardContent className="space-y-3 p-3 sm:p-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-purple-500" />
          <h2 className="text-sm font-semibold sm:text-base">
            Crear hooks orientados a un tema
          </h2>
        </div>
        <p className="text-[11px] text-muted-foreground sm:text-xs">
          Escribe el tema/contexto y Gemini genera N hooks nuevos del producto
          orientados a eso. Usa research_context si está disponible para
          afinar.
        </p>
        <Textarea
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          placeholder="ej. orientados a verano y vacaciones · para regalar a la pareja · dramáticos · para edad >40 · antes de ir al gym"
          rows={2}
          maxLength={300}
          className="text-sm"
          disabled={mutation.isPending}
        />
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <Label className="text-[10px] text-muted-foreground sm:text-xs">
              Nº hooks:
            </Label>
            <Select
              value={String(n)}
              onValueChange={(v) => setN(Number(v))}
              disabled={mutation.isPending}
            >
              <SelectTrigger className="h-8 w-20 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[5, 10, 15, 20].map((v) => (
                  <SelectItem key={v} value={String(v)}>
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={onGenerate}
            disabled={mutation.isPending || !theme.trim()}
            className="h-9 gap-1 bg-purple-600 text-xs hover:bg-purple-700 sm:h-8"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Generando…
              </>
            ) : (
              <>
                <Wand2 className="h-3.5 w-3.5" />
                Generar {n}
              </>
            )}
          </Button>
        </div>

        {mutation.data && (
          <div className="space-y-2 pt-2">
            {mutation.data.theme_interpretation && (
              <p className="rounded bg-muted/30 px-2 py-1.5 text-[10px] italic text-muted-foreground sm:text-[11px]">
                Interpretación: {mutation.data.theme_interpretation}
              </p>
            )}
            <div className="space-y-1.5">
              {mutation.data.hooks.map((h, i) => (
                <HookRow
                  key={i}
                  text={h.text}
                  meta={h.angle}
                  hint={h.rationale}
                  productId={product.id}
                />
              ))}
            </div>
          </div>
        )}
        {mutation.error && (
          <p className="text-xs text-red-600 dark:text-red-400">
            Error: {mutation.error.message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/* ═══════════════════════════════════════════════════════════════
   EXISTING HOOKS — agrupados por preset
   ═══════════════════════════════════════════════════════════════ */
function ExistingHooksSection({ product }: { product: Product }) {
  const presets: VideoPreset[] = product.video_presets ?? [];

  if (presets.length === 0) {
    return (
      <Card className="bg-muted/30">
        <CardContent className="p-4 text-center text-xs text-muted-foreground sm:text-sm">
          Este producto no tiene presets generados. Ve a la pestaña{" "}
          <strong>Presets</strong> del producto para generarlos primero.
        </CardContent>
      </Card>
    );
  }

  // Agrupar por kind + angle para que sea legible
  const groups = useMemo(() => {
    const byKey = new Map<string, VideoPreset[]>();
    for (const p of presets) {
      const key = `${p.kind ?? "scripted"}__${p.angle ?? "general"}`;
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key)!.push(p);
    }
    return Array.from(byKey.entries()).map(([key, arr]) => {
      const [kind, angle] = key.split("__");
      return { kind, angle, presets: arr };
    });
  }, [presets]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold sm:text-base">
          <MessageSquareText className="h-4 w-4 text-amber-500" />
          Hooks de tus presets ({presets.length})
        </h2>
        <span className="text-[10px] text-muted-foreground sm:text-xs">
          {groups.length} grupos
        </span>
      </div>

      {groups.map((g) => (
        <Card key={`${g.kind}-${g.angle}`}>
          <CardContent className="space-y-2 p-3 sm:p-4">
            <div className="flex items-center gap-1.5 text-xs sm:text-sm">
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[9px] font-medium uppercase sm:text-[10px]",
                  g.kind === "music"
                    ? "bg-pink-500/20 text-pink-700 dark:text-pink-300"
                    : "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
                )}
              >
                {g.kind}
              </span>
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-medium uppercase text-amber-700 dark:text-amber-300 sm:text-[10px]">
                {g.angle}
              </span>
              <span className="ml-auto text-[10px] text-muted-foreground sm:text-xs">
                {g.presets.length} preset(s)
              </span>
            </div>

            <div className="space-y-1.5">
              {g.presets.map((p) => (
                <PresetHooksBlock key={p.id} preset={p} productId={product.id} />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function PresetHooksBlock({
  preset,
  productId,
}: {
  preset: VideoPreset;
  productId: string;
}) {
  const hooks: { text: string; label: string }[] = [];
  if (preset.text_overlay && preset.text_overlay.trim()) {
    hooks.push({ text: preset.text_overlay.trim(), label: "principal" });
  }
  for (const h of preset.hooks_alternatives ?? []) {
    if (h && h.trim()) hooks.push({ text: h.trim(), label: "alt" });
  }
  if (preset.title && preset.title.trim()) {
    hooks.push({ text: preset.title.trim(), label: "title" });
  }
  // Dedup
  const seen = new Set<string>();
  const dedup = hooks.filter((h) => {
    const key = h.text.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (dedup.length === 0) return null;

  return (
    <div className="rounded border bg-muted/20 p-2">
      <p className="mb-1 truncate text-[10px] font-semibold text-muted-foreground sm:text-[11px]">
        {preset.name || preset.id?.slice(0, 8)}
      </p>
      <div className="space-y-1">
        {dedup.map((h, i) => (
          <HookRow
            key={i}
            text={h.text}
            meta={h.label}
            productId={productId}
          />
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   HookRow — fila genérica con copy + generar variantes
   ═══════════════════════════════════════════════════════════════ */
function HookRow({
  text,
  meta,
  hint,
  productId,
}: {
  text: string;
  meta?: string;
  hint?: string;
  productId: string;
}) {
  const [showVariants, setShowVariants] = useState(false);
  const variantsMut = useGenerateHookVariants();
  const [n, setN] = useState(5);

  function onCopy() {
    copyToClipboard(text);
  }
  function onGenerate() {
    variantsMut.mutate({ productId, hook: text, n });
    setShowVariants(true);
  }

  return (
    <div className="rounded border border-muted bg-card p-2 text-[11px] sm:text-xs">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="break-words font-medium text-foreground">{text}</p>
          {(meta || hint) && (
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {meta && (
                <span className="mr-1 inline-block rounded bg-muted px-1 py-0.5 uppercase">
                  {meta}
                </span>
              )}
              {hint}
            </p>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={onCopy}
            className="h-7 gap-1 px-2 text-[10px]"
          >
            <Copy className="h-3 w-3" />
            Copiar
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onGenerate}
            disabled={variantsMut.isPending}
            className="h-7 gap-1 px-2 text-[10px] text-purple-600 hover:text-purple-700 dark:text-purple-400"
          >
            {variantsMut.isPending && showVariants ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Wand2 className="h-3 w-3" />
            )}
            +{n} variantes
          </Button>
        </div>
      </div>

      {showVariants && variantsMut.data && (
        <div className="mt-2 space-y-1 border-t pt-2">
          <p className="text-[10px] text-muted-foreground">
            Ángulo detectado: <strong>{variantsMut.data.angle_detected}</strong>
          </p>
          {variantsMut.data.variants.map((v: HookVariant, i: number) => (
            <div
              key={i}
              className="flex items-start gap-1.5 rounded bg-muted/30 px-2 py-1"
            >
              <ChevronRight className="mt-0.5 h-3 w-3 flex-shrink-0 text-purple-500" />
              <div className="min-w-0 flex-1">
                <p className="break-words text-[11px] sm:text-xs">{v.text}</p>
                {v.rationale && (
                  <p className="text-[9px] italic text-muted-foreground sm:text-[10px]">
                    {v.rationale}
                  </p>
                )}
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => copyToClipboard(v.text)}
                className="h-6 gap-1 px-1.5 text-[10px]"
              >
                <Copy className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
      {showVariants && variantsMut.error && (
        <p className="mt-1 text-[10px] text-red-600 dark:text-red-400">
          Error: {variantsMut.error.message}
        </p>
      )}
    </div>
  );
}
