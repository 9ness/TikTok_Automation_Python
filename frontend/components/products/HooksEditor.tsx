"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { useUpdateProduct } from "@/lib/queries/products";
import type { Hook, Product } from "@/lib/types/product";

export function HooksEditor({ product }: { product: Product }) {
  const update = useUpdateProduct(product.id);
  const [draft, setDraft] = useState({ category: "", template: "" });

  async function persist(next: Hook[]) {
    try {
      await update.mutateAsync({ hooks_library: next });
      toast.success("Hooks actualizados.");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al guardar hooks.";
      toast.error(message);
    }
  }

  async function addHook() {
    if (!draft.category.trim() || !draft.template.trim()) return;
    const next = [
      ...product.hooks_library,
      { category: draft.category.trim(), template: draft.template.trim(), performance_score: null },
    ];
    setDraft({ category: "", template: "" });
    await persist(next);
  }

  async function removeHook(idx: number) {
    const next = product.hooks_library.filter((_, i) => i !== idx);
    await persist(next);
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Hooks guardados</Label>
        {product.hooks_library.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay hooks aún.</p>
        ) : (
          <ul className="space-y-2">
            {product.hooks_library.map((hook, idx) => (
              <li key={idx} className="flex items-start gap-2 rounded-md border p-3">
                <div className="flex-1">
                  <p className="text-xs font-mono uppercase text-muted-foreground">
                    {hook.category}
                  </p>
                  <p className="text-sm">{hook.template}</p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => removeHook(idx)}
                  disabled={update.isPending}
                  aria-label="Eliminar hook"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2 rounded-md border bg-card/50 p-3">
        <Label className="text-sm font-medium">Añadir hook nuevo</Label>
        <Input
          placeholder="Categoría (curiosity, social_proof, problem_solution…)"
          value={draft.category}
          onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))}
        />
        <Textarea
          placeholder="Texto del hook…"
          value={draft.template}
          onChange={(e) => setDraft((d) => ({ ...d, template: e.target.value }))}
          rows={2}
        />
        <Button
          size="sm"
          onClick={addHook}
          disabled={!draft.category.trim() || !draft.template.trim() || update.isPending}
        >
          <Plus className="h-4 w-4" /> Añadir
        </Button>
      </div>
    </div>
  );
}
