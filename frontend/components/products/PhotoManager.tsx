"use client";

import { useRef, useState } from "react";
import {
  Download,
  Image as ImageIcon,
  Loader2,
  Trash2,
  Upload,
} from "lucide-react";
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
import { PhotoImportFromUrls } from "./PhotoImportFromUrls";
import { TabHint } from "./TabHint";

const PHOTO_TYPES: PhotoType[] = ["packshot", "lifestyle", "detail", "in_use", "macro"];
const ORIGINS: PhotoOrigin[] = ["internet", "own", "tiktok_shop_url"];

/** URL absoluta al endpoint que sirve la foto. Acepta api_key por query
 *  porque `<img src>` no puede enviar headers. Devuelve null si falta
 *  productId o filename. */
function buildPhotoUrl(productId: string, filename: string): string | null {
  if (!productId || !filename) return null;
  const base =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}/api/v1/products/${productId}/photos/${encodeURIComponent(filename)}/file${qs}`;
}

/** Descarga una foto al disco vía fetch+blob (fuerza descarga, evita
 *  que el browser la abra inline). Mantiene el filename original. */
async function downloadPhoto(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

/** Descarga secuencial de N fotos con toast persistente de progreso.
 *  Pequeño delay entre descargas para que Chrome/Firefox no bloqueen
 *  "multiple downloads". */
async function downloadManyPhotos(
  productId: string,
  filenames: string[],
): Promise<void> {
  if (!filenames?.length) return;
  const toastId = `dl-photos-${productId}-${Date.now()}`;
  toast.loading(`Descargando 0 / ${filenames.length} fotos…`, { id: toastId });
  let done = 0;
  let errors = 0;
  for (let i = 0; i < filenames.length; i++) {
    const fn = filenames[i];
    if (!fn) continue;
    const url = buildPhotoUrl(productId, fn);
    if (!url) {
      errors++;
      continue;
    }
    try {
      await downloadPhoto(url, fn);
      done++;
    } catch {
      errors++;
    }
    toast.loading(
      `Descargando ${done} / ${filenames.length} fotos${errors > 0 ? ` (${errors} fallaron)` : ""}…`,
      { id: toastId },
    );
    if (i < filenames.length - 1) {
      await new Promise((r) => setTimeout(r, 250));
    }
  }
  if (errors > 0) {
    toast.error(`Descargadas ${done}, fallaron ${errors}`, { id: toastId });
  } else {
    toast.success(`Descargadas ${done} foto(s)`, { id: toastId });
  }
}

export function PhotoManager({ product }: { product: Product }) {
  return (
    <div className="space-y-6">
      <PhotoImportFromUrls product={product} />
      <div className="grid gap-6 md:grid-cols-2">
        <PhotoSection product={product} location="source" title="Fotos source" />
        <PhotoSection product={product} location="generated" title="Fotos generadas (Nano Banana)" />
      </div>
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
  const [bulkDownloading, setBulkDownloading] = useState(false);

  async function downloadAll(): Promise<void> {
    if (visible.length === 0) return;
    setBulkDownloading(true);
    try {
      await downloadManyPhotos(
        product.id,
        visible.map((p) => p.filename),
      );
    } finally {
      setBulkDownloading(false);
    }
  }

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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{title}</h3>
            <Badge variant="secondary">{visible.length}</Badge>
          </div>
          {visible.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={downloadAll}
              disabled={bulkDownloading}
              className="h-7 gap-1 px-2 text-xs"
              title="Descarga todas las fotos al disco (calidad original)"
            >
              {bulkDownloading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {bulkDownloading
                ? "Descargando…"
                : `Descargar todas (${visible.length})`}
            </Button>
          )}
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
  const [downloading, setDownloading] = useState(false);
  const url = buildPhotoUrl(product.id, photo.filename);

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

  async function handleDownload(): Promise<void> {
    if (!url) {
      toast.error("URL de la foto no disponible.");
      return;
    }
    setDownloading(true);
    try {
      await downloadPhoto(url, photo.filename);
      toast.success(`${photo.filename} descargada.`);
    } catch (e) {
      toast.error(
        e instanceof Error
          ? `Descarga falló: ${e.message}`
          : "Descarga falló.",
      );
    } finally {
      setDownloading(false);
    }
  }

  return (
    <li className="flex items-center gap-2 rounded-md border bg-card/50 p-2">
      {/* Thumbnail clickable que abre el original en pestaña nueva */}
      <a
        href={url ?? "#"}
        target="_blank"
        rel="noopener noreferrer"
        className="block h-12 w-12 shrink-0 overflow-hidden rounded bg-muted/40 transition-transform hover:scale-105"
        title="Click: abre el original en pestaña nueva"
        onClick={(e) => {
          if (!url) e.preventDefault();
        }}
      >
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={photo.filename}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <ImageIcon className="h-5 w-5" />
          </div>
        )}
      </a>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{photo.filename}</p>
        <p className="truncate text-xs text-muted-foreground">
          {location === "source" && photo.origin ? photo.origin : ""}
          {photo.added_at || photo.generated_at
            ? ` · ${(photo.added_at || photo.generated_at)?.slice(0, 10)}`
            : ""}
        </p>
      </div>
      <Select value={photo.type ?? undefined} onValueChange={changeType}>
        <SelectTrigger className="h-8 w-28 shrink-0">
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
        onClick={handleDownload}
        disabled={downloading || !url}
        aria-label={`Descargar ${photo.filename}`}
        title="Descargar al disco (calidad original)"
      >
        {downloading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={handleDelete}
        disabled={del.isPending}
        aria-label={`Eliminar ${photo.filename}`}
      >
        {del.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Trash2 className="h-4 w-4" />
        )}
      </Button>
    </li>
  );
}
