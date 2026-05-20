"use client";

import { useMemo, useState } from "react";
import { FlaskConical, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  useEnqueueTestBatch,
  type VaryableDimension,
  VARYABLE_DIMENSIONS,
} from "@/lib/queries/generations";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { EnqueueRequest } from "@/lib/types/generation";

const DIM_LABELS: Record<VaryableDimension, string> = {
  hook_category: "Hook categoría",
  voice_id: "Voz",
  strategy: "Estrategia",
  duration_seconds: "Duración",
  hook_box_animation: "Animación hook box",
};

interface Props {
  basePayload: EnqueueRequest;
  estimatedCostPerVideo: number;
  disabled?: boolean;
}

/**
 * Mini-panel para encolar N variantes A/B desde el AutoVideoCard. El usuario
 * selecciona qué dimensiones rotar + cuántas variantes, y vemos el coste
 * total antes de confirmar.
 */
export function TestBatchPanel({ basePayload, estimatedCostPerVideo, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(4);
  const [vary, setVary] = useState<VaryableDimension[]>(["hook_category"]);
  const enqueueBatch = useEnqueueTestBatch();
  const openQueue = useDrawerStore((s) => s.openQueue);

  const totalCost = useMemo(
    () => estimatedCostPerVideo * count,
    [estimatedCostPerVideo, count],
  );

  function toggleDim(dim: VaryableDimension) {
    setVary((v) => {
      if (v.includes(dim)) {
        if (v.length === 1) return v; // mínimo 1
        return v.filter((x) => x !== dim);
      }
      if (v.length >= 3) return v; // máximo 3
      return [...v, dim];
    });
  }

  async function submit() {
    try {
      const res = await enqueueBatch.mutateAsync({
        base: basePayload,
        vary,
        count,
      });
      toast.success(
        `Batch encolado · ${res.job_ids.length} variantes · $${res.estimated_cost_total.toFixed(2)} total`,
      );
      openQueue();
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error encolando batch.");
    }
  }

  if (!open) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={disabled}
        title="Encola N variantes rotando dimensiones"
      >
        <FlaskConical className="h-4 w-4" />
        N variantes
      </Button>
    );
  }

  return (
    <div className="w-full space-y-3 rounded-md border border-cyan-500/30 bg-cyan-500/5 p-3">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium flex items-center gap-1">
            <FlaskConical className="h-4 w-4 text-cyan-400" />
            Test batch · {count} variantes
          </p>
          <p className="text-[10px] text-muted-foreground">
            Encola N jobs rotando las dimensiones seleccionadas. Útil para A/B testing.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          Cerrar
        </Button>
      </div>

      <div className="space-y-1">
        <Label className="text-xs">Número de variantes: {count}</Label>
        <input
          type="range"
          min={2}
          max={8}
          step={1}
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          className="w-full"
        />
      </div>

      <div className="space-y-1">
        <Label className="text-xs">Dimensiones a rotar (1-3)</Label>
        <div className="flex flex-wrap gap-1">
          {VARYABLE_DIMENSIONS.map((dim) => {
            const active = vary.includes(dim);
            return (
              <button
                key={dim}
                type="button"
                onClick={() => toggleDim(dim)}
                className={`rounded-full border px-2 py-0.5 text-[11px] ${
                  active
                    ? "border-cyan-500/60 bg-cyan-500/15 text-cyan-100"
                    : "border-border text-muted-foreground"
                }`}
              >
                {DIM_LABELS[dim]}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between rounded-md border bg-background/40 px-3 py-2 text-xs">
        <span className="text-muted-foreground">Coste total estimado</span>
        <span className="font-mono font-medium">
          ${totalCost.toFixed(2)} ({count} × ${estimatedCostPerVideo.toFixed(3)})
        </span>
      </div>

      <Button onClick={submit} disabled={enqueueBatch.isPending} className="w-full">
        {enqueueBatch.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <FlaskConical className="h-4 w-4" />
        )}
        Encolar {count} variantes
      </Button>
    </div>
  );
}
