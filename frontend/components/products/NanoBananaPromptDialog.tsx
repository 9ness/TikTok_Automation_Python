"use client";

import { useState } from "react";
import { Check, Copy, Loader2 } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { useGenerateNanoBananaPrompt } from "@/lib/queries/products";
import type { PhotoType, Product } from "@/lib/types/product";

const PHOTO_TYPES: PhotoType[] = ["packshot", "lifestyle", "detail", "in_use", "macro"];

export function NanoBananaPromptDialog({
  product,
  open,
  onOpenChange,
}: {
  product: Product;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const generate = useGenerateNanoBananaPrompt();
  const [selected, setSelected] = useState<PhotoType[]>(["packshot", "lifestyle", "macro"]);
  const [angles, setAngles] = useState<number>(5);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function toggleType(type: PhotoType) {
    setSelected((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  }

  async function handleGenerate() {
    if (selected.length === 0) {
      toast.error("Selecciona al menos un tipo de foto.");
      return;
    }
    try {
      const res = await generate.mutateAsync({
        productId: product.id,
        payload: { photo_types_wanted: selected, n_angles: angles },
      });
      setPrompt(res.prompt);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al generar prompt.";
      toast.error(message);
    }
  }

  async function copyPrompt() {
    if (!prompt) return;
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setPrompt(null);
      setCopied(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Generar prompt Nano Banana 2</DialogTitle>
          <DialogDescription>
            Genera un prompt optimizado para crear fotos premium en Gemini chat con Nano Banana 2.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Tipos de foto deseados</Label>
            <div className="flex flex-wrap gap-2">
              {PHOTO_TYPES.map((t) => {
                const active = selected.includes(t);
                return (
                  <Button
                    key={t}
                    type="button"
                    size="sm"
                    variant={active ? "default" : "outline"}
                    onClick={() => toggleType(t)}
                  >
                    {t}
                  </Button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <Label>Número de ángulos: {angles}</Label>
            <Slider
              value={[angles]}
              min={4}
              max={8}
              step={1}
              onValueChange={(v) => setAngles(v[0] ?? 5)}
            />
          </div>

          <div className="rounded-md border bg-card/50 p-3 text-sm text-muted-foreground">
            <ol className="list-decimal space-y-1 pl-4">
              <li>Genera el prompt con el botón inferior.</li>
              <li>Cópialo y pégalo en Gemini chat con modelo Nano Banana 2 + las fotos source.</li>
              <li>Guarda las imágenes generadas y súbelas en la pestaña Fotos como “generated”.</li>
            </ol>
          </div>

          {prompt && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Prompt</Label>
                <Button size="sm" variant="ghost" onClick={copyPrompt}>
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {copied ? "Copiado" : "Copiar"}
                </Button>
              </div>
              <Textarea readOnly value={prompt} rows={10} className="font-mono text-xs" />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleClose(false)}
            disabled={generate.isPending}
          >
            Cerrar
          </Button>
          <Button onClick={handleGenerate} disabled={generate.isPending || selected.length === 0}>
            {generate.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {prompt ? "Regenerar" : "Generar prompt"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
