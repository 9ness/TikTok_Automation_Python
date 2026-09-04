"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, Image as ImageIcon, Loader2, Trash2 } from "lucide-react";
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
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useDeleteProduct } from "@/lib/queries/products";
import { cn } from "@/lib/utils";
import type { Product, Tier } from "@/lib/types/product";
import { api } from "@/lib/api";

const TIER_LABEL: Record<Tier, string> = {
  standard: "🟢 Standard",
  advanced: "🟡 Advanced",
  pro: "🔴 Pro",
  veo3_prompt_only: "🟣 Veo 3",
  nano_banana_prompt_only: "🍌 Nano Banana",
};

export function ProductCard({ product }: { product: Product }) {
  const tier = product.video_config.default_tier;
  const cover = pickCoverPhotoUrl(product);
  const photoCount = product.photos.source.length + product.photos.generated.length;
  const deleteMut = useDeleteProduct();
  const [confirmOpen, setConfirmOpen] = useState(false);

  function openConfirm(e: React.MouseEvent) {
    // Sin esto, el click navegaría al detalle por el <Link> envolvente.
    e.preventDefault();
    e.stopPropagation();
    setConfirmOpen(true);
  }

  async function handleConfirmDelete() {
    try {
      await deleteMut.mutateAsync(product.id);
      toast.success(`'${product.name}' eliminado`);
      setConfirmOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al eliminar");
    }
  }

  return (
    <>
    <Link href={{ pathname: `/tiktok-shop/products/${product.id}` }} className="block">
      <Card
        className={cn(
          "group relative h-full overflow-hidden transition-shadow hover:shadow-md",
          product.deleted && "opacity-50",
        )}
      >
        {/* Botón borrar — visible en hover desktop, siempre en touch */}
        <button
          type="button"
          onClick={openConfirm}
          disabled={deleteMut.isPending}
          aria-label="Eliminar producto"
          className={cn(
            "absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full",
            "bg-black/70 text-white shadow-lg backdrop-blur-sm transition-all",
            "hover:bg-rose-600 disabled:opacity-50",
            // En desktop solo aparece al pasar el cursor por encima.
            // En móvil (touch) siempre visible.
            "opacity-100 sm:opacity-0 sm:group-hover:opacity-100",
          )}
        >
          {deleteMut.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Trash2 className="h-3.5 w-3.5" />
          )}
        </button>
        <div className="aspect-square bg-muted sm:aspect-video">
          {cover ? (
            <img
              src={cover}
              alt={product.name}
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-muted-foreground">
              <ImageIcon className="h-8 w-8" />
            </div>
          )}
        </div>
        <CardContent className="space-y-1 p-2 sm:space-y-2 sm:p-4">
          <div className="flex items-start justify-between gap-1.5 sm:gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold sm:text-base">
                {product.name}
              </h3>
              <p className="truncate text-[10px] text-muted-foreground sm:text-xs">
                {product.brand ? `${product.brand} · ` : ""}
                <span className="font-mono">{product.slug}</span>
              </p>
            </div>
            <Badge variant="secondary" className="shrink-0 px-1.5 text-[10px] sm:text-xs">
              {TIER_LABEL[tier] ?? tier}
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground sm:gap-2 sm:text-xs">
            <span>{product.category}</span>
            <span>·</span>
            <span>{photoCount} fotos</span>
            {product.tiktok_shop.price_eur != null && (
              <>
                <span>·</span>
                <span>{product.tiktok_shop.price_eur.toFixed(2)}€</span>
              </>
            )}
            {product.needs_nano_banana_regeneration && (
              <Badge variant="destructive" className="gap-1 px-1.5 text-[10px] sm:text-xs">
                <AlertTriangle className="h-3 w-3" />
                <span className="hidden sm:inline">Regenerar fotos</span>
                <span className="sm:hidden">Regen</span>
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
    {/* AlertDialog de confirmación con estilo de la app */}
    <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            ¿Eliminar &ldquo;{product.name}&rdquo;?
          </AlertDialogTitle>
          <AlertDialogDescription className="space-y-2">
            <span className="block">
              Se borrará el producto del catálogo y la carpeta del producto
              en Drive (
              <code className="rounded bg-muted px-1 text-xs">
                TIKTOK_SHOP/_products/{product.slug}
              </code>
              ) — fotos source, generadas y configuración.
            </span>
            <span className="block">
              Drive Desktop mueve la carpeta a la papelera de Google Drive,
              donde se queda 30 días por si necesitas recuperarla.{" "}
              <strong className="text-destructive">
                Desde la app no se puede deshacer.
              </strong>
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteMut.isPending}>
            Cancelar
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirmDelete}
            disabled={deleteMut.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleteMut.isPending ? (
              <>
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                Eliminando…
              </>
            ) : (
              <>
                <Trash2 className="mr-2 h-3 w-3" />
                Sí, eliminar
              </>
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}

function pickCoverPhotoUrl(product: Product): string | null {
  const generated = product.photos.generated.find((p) => !p.deleted);
  const source = product.photos.source.find((p) => !p.deleted);
  const photo = generated ?? source;
  if (!photo?.filename) return null;
  const base = api.baseUrl;
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}/api/v1/products/${product.id}/photos/${encodeURIComponent(photo.filename)}/file${qs}`;
}
