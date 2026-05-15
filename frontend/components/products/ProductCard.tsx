"use client";

import Link from "next/link";
import { Image as ImageIcon, AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Product, Tier } from "@/lib/types/product";

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

  return (
    <Link href={{ pathname: `/tiktok-shop/products/${product.id}` }} className="block">
      <Card
        className={cn(
          "h-full overflow-hidden transition-shadow hover:shadow-md",
          product.deleted && "opacity-50",
        )}
      >
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
  );
}

function pickCoverPhotoUrl(product: Product): string | null {
  const generated = product.photos.generated.find((p) => !p.deleted);
  const source = product.photos.source.find((p) => !p.deleted);
  const photo = generated ?? source;
  if (!photo?.filename) return null;
  const base =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}/api/v1/products/${product.id}/photos/${encodeURIComponent(photo.filename)}/file${qs}`;
}
