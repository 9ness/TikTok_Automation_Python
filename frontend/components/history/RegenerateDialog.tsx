"use client";

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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { useRegenerateGeneration } from "@/lib/queries/generations";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { GenerationResponse } from "@/lib/types/generation";
import type { Tier } from "@/lib/types/product";

const TIERS: Tier[] = ["standard", "advanced", "pro", "veo3_prompt_only"];
const DURATIONS = [5, 10, 12, 15, 20, 24, 25, 30];

export function RegenerateDialog({
  generation,
  open,
  onOpenChange,
}: {
  generation: GenerationResponse;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const regen = useRegenerateGeneration();
  const openQueue = useDrawerStore((s) => s.openQueue);
  const [tier, setTier] = useState<Tier>(generation.tier_used);
  const [duration, setDuration] = useState<number>(generation.duration_seconds);
  const [resolution, setResolution] = useState<string>(generation.resolution);

  async function submit() {
    const overrides: Record<string, unknown> = {};
    if (tier !== generation.tier_used) overrides.tier = tier;
    if (duration !== generation.duration_seconds) overrides.duration = duration;
    if (resolution !== generation.resolution) overrides.resolution = resolution;
    try {
      const res = await regen.mutateAsync({
        generationId: generation.id,
        overrides,
      });
      toast.success(
        `Encolado · job ${res.job_id.slice(0, 8)} · $${res.estimated_cost.toFixed(2)}`,
      );
      onOpenChange(false);
      openQueue();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al regenerar.";
      toast.error(message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Regenerar con cambios</DialogTitle>
          <DialogDescription>
            Pre-rellenado con la config original. Cambia lo que quieras y
            encólalo. Los campos sin cambios mantienen el valor original.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Tier</Label>
            <Select value={tier} onValueChange={(v) => setTier(v as Tier)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIERS.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Duración</Label>
            <Select
              value={String(duration)}
              onValueChange={(v) => setDuration(Number(v))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DURATIONS.map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {d}s
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Resolución</Label>
            <Select value={resolution} onValueChange={setResolution}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["480p", "720p", "1080p-SR", "1440p-SR"].map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={regen.isPending}
          >
            Cancelar
          </Button>
          <Button onClick={submit} disabled={regen.isPending}>
            {regen.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Regenerar con cambios
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
