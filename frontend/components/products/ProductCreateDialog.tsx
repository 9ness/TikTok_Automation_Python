"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";
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
import { ApiError } from "@/lib/api";
import { useCreateProduct } from "@/lib/queries/products";
import type { Tier } from "@/lib/types/product";

const TIER_OPTIONS: { value: Tier; label: string }[] = [
  { value: "standard", label: "🟢 Standard" },
  { value: "advanced", label: "🟡 Advanced" },
  { value: "pro", label: "🔴 Pro" },
  { value: "veo3_prompt_only", label: "🟣 Veo 3 (prompt-only)" },
  { value: "nano_banana_prompt_only", label: "🍌 Nano Banana (prompt-only)" },
];

const CATEGORY_OPTIONS = ["fitness", "skincare", "hogar", "tech", "moda", "otros"];

export function ProductCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const router = useRouter();
  const create = useCreateProduct();
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("otros");
  const [tier, setTier] = useState<Tier>("standard");

  function reset() {
    setName("");
    setBrand("");
    setCategory("otros");
    setTier("standard");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const product = await create.mutateAsync({
        name: name.trim(),
        brand: brand.trim() || null,
        category,
        default_tier: tier,
      });
      toast.success(`Producto '${product.name}' creado.`);
      onOpenChange(false);
      reset();
      // Typed routes (`experimental.typedRoutes`) no permite dynamic params en push();
      // el cast a `never` salta el chequeo solo aquí.
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
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Nuevo producto</DialogTitle>
            <DialogDescription>
              Datos mínimos. Podrás completar fotos, audiencia y hooks tras crearlo.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="product-name">Nombre *</Label>
            <Input
              id="product-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Primal Pump - Gominolas Creatina"
              required
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="product-brand">Marca</Label>
            <Input
              id="product-brand"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="Primal Pump"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
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
            <div className="space-y-2">
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
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Crear
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
