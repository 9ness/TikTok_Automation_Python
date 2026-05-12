"use client";

import { useRef, useState } from "react";
import { Image as ImageIcon, Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  useDeletePhoto,
  useUpdatePhoto,
  useUploadPhoto,
} from "@/lib/queries/products";
import type {
  PhotoLocation,
  PhotoOrigin,
  PhotoType,
  Product,
  ProductPhoto,
} from "@/lib/types/product";
import { cn } from "@/lib/utils";

const PHOTO_TYPES: PhotoType[] = ["packshot", "lifestyle", "detail", "in_use", "macro"];
const ORIGINS: PhotoOrigin[] = ["internet", "own", "tiktok_shop_url"];

export function PhotoManager({ product }: { product: Product }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <PhotoSection product={product} location="source" title="Fotos source" />
      <PhotoSection product={product} location="generated" title="Fotos generadas (Nano Banana)" />
    </div>
  );
}

function PhotoSection({
  product,
  location,
  title,
}: {
  product: Product;
  location: PhotoLocation;
  title: string;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const upload = useUploadPhoto();
  const [uploadType, setUploadType] = useState<PhotoType | undefined>();
  const [uploadOrigin, setUploadOrigin] = useState<PhotoOrigin | undefined>(
    location === "source" ? "internet" : undefined,
  );

  const photos = location === "source" ? product.photos.source : product.photos.generated;
  const visible = photos.filter((p) => !p.deleted);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    if (location === "generated" && !uploadType) {
      toast.error("Selecciona el tipo de foto antes de subir.");
      return;
    }
    try {
      for (const file of Array.from(files)) {
        await upload.mutateAsync({
          productId: product.id,
          file,
          location,
          type: uploadType,
          origin: location === "source" ? uploadOrigin : undefined,
        });
      }
      toast.success(`${files.length} foto(s) subidas.`);
      if (fileInput.current) fileInput.current.value = "";
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Error inesperado al subir.";
      toast.error(message);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">{title}</h3>
          <Badge variant="secondary">{visible.length}</Badge>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {location === "source" ? (
            <Select
              value={uploadOrigin}
              onValueChange={(v) => setUploadOrigin(v as PhotoOrigin)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Origen" />
              </SelectTrigger>
              <SelectContent>
                {ORIGINS.map((o) => (
                  <SelectItem key={o} value={o}>
                    {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <div />
          )}
          <Select value={uploadType} onValueChange={(v) => setUploadType(v as PhotoType)}>
            <SelectTrigger>
              <SelectValue
                placeholder={location === "generated" ? "Tipo (obligatorio)" : "Tipo (opcional)"}
              />
            </SelectTrigger>
            <SelectContent>
              {PHOTO_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Label
          htmlFor={`upload-${location}`}
          className={cn(
            "flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed py-6 text-sm text-muted-foreground transition-colors hover:bg-accent",
            upload.isPending && "pointer-events-none opacity-50",
          )}
        >
          {upload.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          {upload.isPending ? "Subiendo…" : "Click para subir o arrastrar fotos"}
        </Label>
        <input
          ref={fileInput}
          id={`upload-${location}`}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="sr-only"
          onChange={(e) => handleFiles(e.target.files)}
        />

        {visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <ImageIcon className="h-6 w-6" />
            Sin fotos.
          </div>
        ) : (
          <ul className="space-y-2">
            {visible.map((photo) => (
              <PhotoRow key={photo.filename} product={product} photo={photo} location={location} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PhotoRow({
  product,
  photo,
  location,
}: {
  product: Product;
  photo: ProductPhoto;
  location: PhotoLocation;
}) {
  const update = useUpdatePhoto();
  const del = useDeletePhoto();

  async function changeType(value: string) {
    try {
      await update.mutateAsync({
        productId: product.id,
        photoId: photo.filename,
        payload: { type: value as PhotoType },
      });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Error al actualizar tipo.";
      toast.error(message);
    }
  }

  async function handleDelete() {
    try {
      await del.mutateAsync({ productId: product.id, photoId: photo.filename });
      toast.success("Foto eliminada.");
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Error al eliminar.";
      toast.error(message);
    }
  }

  return (
    <li className="flex items-center gap-3 rounded-md border bg-card/50 p-2">
      <div className="flex-1 truncate">
        <p className="truncate text-sm font-medium">{photo.filename}</p>
        <p className="truncate text-xs text-muted-foreground">
          {location === "source" && photo.origin ? photo.origin : ""}
          {photo.added_at || photo.generated_at ? ` · ${(photo.added_at || photo.generated_at)?.slice(0, 10)}` : ""}
        </p>
      </div>
      <Select value={photo.type ?? undefined} onValueChange={changeType}>
        <SelectTrigger className="h-8 w-32">
          <SelectValue placeholder="Tipo" />
        </SelectTrigger>
        <SelectContent>
          {PHOTO_TYPES.map((t) => (
            <SelectItem key={t} value={t}>
              {t}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        variant="ghost"
        size="icon"
        onClick={handleDelete}
        disabled={del.isPending}
        aria-label={`Eliminar ${photo.filename}`}
      >
        {del.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
      </Button>
    </li>
  );
}
