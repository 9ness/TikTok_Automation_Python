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
        <div className="aspect-video bg-muted">
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
        <CardContent className="space-y-2 p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate font-semibold">{product.name}</h3>
              <p className="truncate text-xs text-muted-foreground">
                {product.brand ? `${product.brand} · ` : ""}
                <span className="font-mono">{product.slug}</span>
              </p>
            </div>
            <Badge variant="secondary">{TIER_LABEL[tier] ?? tier}</Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
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
              <Badge variant="destructive" className="gap-1">
                <AlertTriangle className="h-3 w-3" /> Regenerar fotos
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
