"use client";

import { Film } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { GenerationResponse } from "@/lib/types/generation";
import { cn } from "@/lib/utils";
import { VideoActions } from "./VideoActions";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  completed: "default",
  failed: "destructive",
  pending: "secondary",
  generating: "secondary",
  manual_pending: "outline",
  manual_completed: "outline",
};

export function HistoryTable({
  items,
  onRowClick,
}: {
  items: GenerationResponse[];
  onRowClick: (gen: GenerationResponse) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-md border bg-card/50 p-12 text-center text-sm text-muted-foreground">
        No hay generaciones que coincidan con los filtros.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/50 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="p-3 text-left">Vídeo</th>
            <th className="p-3 text-left">Tier</th>
            <th className="p-3 text-left">Status</th>
            <th className="p-3 text-right">Coste</th>
            <th className="p-3 text-left">Fecha</th>
            <th className="p-3 text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {items.map((gen) => (
            <tr
              key={gen.id}
              onClick={() => onRowClick(gen)}
              className={cn(
                "cursor-pointer border-b transition-colors hover:bg-accent/40 last:border-0",
              )}
            >
              <td className="p-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-14 items-center justify-center rounded bg-muted">
                    <Film className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="font-mono text-xs">{gen.id.slice(0, 8)}</p>
                    <p className="text-xs text-muted-foreground">
                      {gen.duration_seconds}s · {gen.resolution}
                    </p>
                  </div>
                </div>
              </td>
              <td className="p-3">{gen.tier_used}</td>
              <td className="p-3">
                <Badge variant={STATUS_VARIANT[gen.generation_status] ?? "secondary"}>
                  {gen.generation_status}
                </Badge>
              </td>
              <td className="p-3 text-right font-mono text-xs">
                ${gen.cost.total.toFixed(3)}
              </td>
              <td className="p-3 text-xs text-muted-foreground">
                {gen.created_at.slice(0, 10)}
              </td>
              <td className="p-3" onClick={(e) => e.stopPropagation()}>
                <div className="flex justify-end">
                  <VideoActions generation={gen} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
