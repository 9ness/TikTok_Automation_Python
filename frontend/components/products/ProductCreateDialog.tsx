"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  useAnalyzeUrlPreview,
  useCreateProduct,
} from "@/lib/queries/products";
import type { Tier } from "@/lib/types/product";

const TIER_OPTIONS: { value: Tier; label: string }[] = [
  { value: "standard", label: "🟢 Standard" },
  { value: "advanced", label: "🟡 Advanced" },
  { value: "pro", label: "🔴 Pro" },
  { value: "veo3_prompt_only", label: "🟣 Veo 3 (prompt-only)" },
  { value: "nano_banana_prompt_only", label: "🍌 Nano Banana (prompt-only)" },
];

const CATEGORY_OPTIONS = ["fitness", "skincare", "hogar", "tech", "moda", "otros"];

/** Redondea a 2 decimales y devuelve string (sin decimales si es entero). */
function roundTo2(n: number): string {
  if (!isFinite(n)) return "";
  const r = Math.round(n * 100) / 100;
  return r % 1 === 0 ? r.toString() : r.toFixed(2);
}

export function ProductCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const router = useRouter();
  const create = useCreateProduct();
  const analyze = useAnalyzeUrlPreview();

  // Sección "auto-analizar"
  const [url, setUrl] = useState("");
  const [rawText, setRawText] = useState("");
  // Imagen detectada por el scrape — se manda al backend con el create
  // y backend la descarga como primera foto packshot.
  const [imageUrlToDownload, setImageUrlToDownload] = useState<string | null>(
    null,
  );

  // Datos del producto (lo que termina yendo al POST)
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("otros");
  const [subcategory, setSubcategory] = useState("");
  const [priceEur, setPriceEur] = useState<string>("");
  // Comisión: dos strings INDEPENDIENTES mientras se escribe. Sólo se
  // sincronizan al salir del campo (onBlur). Evita el comportamiento
  // molesto en el que cada tecla pulsada recalcula el otro campo.
  const [commissionPct, setCommissionPct] = useState<string>("10");
  const [commissionEur, setCommissionEur] = useState<string>("");
  const [tier, setTier] = useState<Tier>("standard");

  const priceNum = parseFloat(priceEur.replace(",", ".")) || 0;
  const pctNum = parseFloat(commissionPct.replace(",", ".")) || 0;

  /** Cuando el user sale del campo % → recalcula €. */
  function syncEurFromPct() {
    if (priceNum <= 0) return;
    if (commissionPct.trim() === "") return;
    const eur = (priceNum * pctNum) / 100;
    setCommissionEur(roundTo2(eur));
  }

  /** Cuando el user sale del campo € → recalcula %. */
  function syncPctFromEur() {
    if (priceNum <= 0) {
      // No podemos calcular el % sin precio. No mostramos warning aquí
      // (el campo está disabled si no hay precio), pero por defensiva.
      return;
    }
    if (commissionEur.trim() === "") return;
    const eurNum = parseFloat(commissionEur.replace(",", ".")) || 0;
    const pct = (eurNum / priceNum) * 100;
    setCommissionPct(roundTo2(pct));
  }

  /** Cuando el user sale del campo precio → recalcula €
   *  (manteniendo el % que el user dejó). */
  function syncEurFromPrice() {
    if (priceNum <= 0) {
      setCommissionEur("");
      return;
    }
    if (commissionPct.trim() === "") return;
    const eur = (priceNum * pctNum) / 100;
    setCommissionEur(roundTo2(eur));
  }

  function reset() {
    setUrl("");
    setRawText("");
    setImageUrlToDownload(null);
    setName("");
    setBrand("");
    setCategory("otros");
    setSubcategory("");
    setPriceEur("");
    setCommissionPct("10");
    setCommissionEur("");
    setTier("standard");
  }

  async function handleAnalyze() {
    const u = url.trim();
    const t = rawText.trim();
    if (!u && !t) {
      toast.error("Pega URL TikTok Shop o texto del producto");
      return;
    }
    try {
      const result = await analyze.mutateAsync({
        url: u || undefined,
        raw_text: t || undefined,
      });
      // Aplicamos lo detectado a los campos que estén vacíos. No pisamos
      // lo que el user ya escribió a mano.
      if (result.name && !name.trim()) setName(result.name);
      if (result.brand && !brand.trim()) setBrand(result.brand);
      if (result.category && (category === "otros" || !category)) {
        setCategory(result.category);
      }
      if (result.subcategory && !subcategory.trim()) {
        setSubcategory(result.subcategory);
      }
      if (result.price_eur != null && !priceEur.trim()) {
        const newPrice = result.price_eur;
        setPriceEur(roundTo2(newPrice));
        // Si ya tenemos un % por defecto, recalcula la comisión € visible.
        if (pctNum > 0) {
          setCommissionEur(roundTo2((newPrice * pctNum) / 100));
        }
      }
      if (result.image_url) {
        setImageUrlToDownload(result.image_url);
      }
      const filled = [
        result.name && "nombre",
        result.brand && "marca",
        result.category && "categoría",
        result.subcategory && "subcategoría",
        result.price_eur != null && "precio",
        result.image_url && "foto",
      ].filter(Boolean);
      if (filled.length === 0) {
        toast.warning(
          "No se detectó información. " +
            (result.warnings[0] || "Intenta pegando texto del producto."),
        );
      } else {
        toast.success(`Detectado: ${filled.join(", ")}. Revisa y guarda.`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Análisis falló");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const product = await create.mutateAsync({
        name: name.trim(),
        brand: brand.trim() || null,
        category,
        subcategory: subcategory.trim() || null,
        default_tier: tier,
        tiktok_shop: {
          product_url: url.trim() || null,
          commission_rate: pctNum / 100,
          price_eur: priceNum > 0 ? priceNum : null,
        },
        image_url_to_download: imageUrlToDownload,
      });
      toast.success(
        `Producto '${product.name}' creado${
          imageUrlToDownload ? " · foto descargada" : ""
        }`,
      );
      onOpenChange(false);
      reset();
      router.push(`/tiktok-shop/products/${product.id}` as never);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Error inesperado al crear el producto.";
      toast.error(message);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-2xl overflow-y-auto">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Nuevo producto</DialogTitle>
            <DialogDescription>
              Pega la URL de TikTok Shop y pulsa <strong>Analizar</strong> —
              autorrellena nombre, marca, categoría, precio y descarga la foto.
              Si TikTok no devuelve nada, pega también texto del producto.
            </DialogDescription>
          </DialogHeader>

          {/* SECCIÓN AUTO-ANALIZAR */}
          <div className="space-y-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3">
            <Label htmlFor="product-url" className="text-xs font-semibold">
              URL TikTok Shop (opcional)
            </Label>
            <div className="flex gap-2">
              <Input
                id="product-url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://vm.tiktok.com/... o https://shop-xx.tiktok.com/view/product/..."
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleAnalyze}
                disabled={
                  analyze.isPending || (!url.trim() && !rawText.trim())
                }
              >
                {analyze.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="h-4 w-4" />
                )}
                <span className="ml-2">Analizar</span>
              </Button>
            </div>
            <Textarea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder="Opcional · pega título / descripción / precio del dashboard de TikTok Shop si la URL no da info."
              rows={2}
              className="text-xs"
            />
            {imageUrlToDownload && (
              <div className="flex items-center gap-2 text-[11px] text-emerald-700 dark:text-emerald-300">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={imageUrlToDownload}
                  alt=""
                  className="h-10 w-10 rounded object-cover"
                />
                <span>
                  Foto detectada — se descargará automáticamente al crear el producto.
                </span>
              </div>
            )}
          </div>

          {/* DATOS DEL PRODUCTO */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="product-name">Nombre *</Label>
              <Input
                id="product-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Crema bronceadora natural"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="product-brand">Marca</Label>
              <Input
                id="product-brand"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="Freshly Cosmetics"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="product-category">Categoría</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger id="product-category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORY_OPTIONS.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="product-subcategory">Subcategoría</Label>
              <Input
                id="product-subcategory"
                value={subcategory}
                onChange={(e) => setSubcategory(e.target.value)}
                placeholder="autobronceador"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="product-price">Precio EUR</Label>
              <Input
                id="product-price"
                type="number"
                step="any"
                min="0"
                value={priceEur}
                onChange={(e) => setPriceEur(e.target.value)}
                onBlur={syncEurFromPrice}
                placeholder="29.95"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="product-commission-pct">Comisión %</Label>
              <Input
                id="product-commission-pct"
                type="number"
                step="any"
                min="0"
                max="100"
                value={commissionPct}
                onChange={(e) => setCommissionPct(e.target.value)}
                onBlur={syncEurFromPct}
                placeholder="10"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="product-commission-eur">Comisión € (importe)</Label>
              <Input
                id="product-commission-eur"
                type="number"
                step="any"
                min="0"
                value={commissionEur}
                disabled={priceNum <= 0}
                placeholder={priceNum <= 0 ? "Pon antes el Precio" : "0.00"}
                onChange={(e) => setCommissionEur(e.target.value)}
                onBlur={syncPctFromEur}
              />
              {priceNum > 0 && (
                <p className="text-[10px] text-muted-foreground">
                  Escribe el valor exacto que quieras — al salir del campo se
                  recalcula el otro sobre {priceNum.toFixed(2)}€.
                </p>
              )}
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="product-tier">Tier por defecto</Label>
              <Select value={tier} onValueChange={(v) => setTier(v as Tier)}>
                <SelectTrigger id="product-tier">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={create.isPending || !name.trim()}
            >
              {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Crear producto
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
