"use client";

import { Film } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { VideoSummary } from "@/lib/types/dashboard";

export function RecentVideosGrid({ videos }: { videos: VideoSummary[] }) {
  return (
    <Card>
      <CardHeader className="pb-2 sm:pb-4">
        <CardTitle className="text-base sm:text-lg">Vídeos recientes</CardTitle>
      </CardHeader>
      <CardContent>
        {videos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin generaciones recientes.</p>
        ) : (
          <ul className="space-y-1.5 sm:space-y-2">
            {videos.map((v) => (
              <li
                key={v.generation_id}
                className="flex items-center gap-2 rounded-md border bg-card/50 p-1.5 sm:gap-3 sm:p-2"
              >
                <div className="flex h-8 w-10 shrink-0 items-center justify-center rounded bg-muted sm:h-10 sm:w-14">
                  <Film className="h-3.5 w-3.5 text-muted-foreground sm:h-4 sm:w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-[11px] sm:text-xs">
                    {v.generation_id.slice(0, 8)}
                  </p>
                  <p className="truncate text-[10px] text-muted-foreground sm:text-xs">
                    {v.tier_used} · {v.created_at.slice(0, 10)} · ${v.cost_total.toFixed(3)}
                  </p>
                </div>
                <Badge
                  variant={statusVariant(v.status)}
                  className="shrink-0 px-1.5 text-[10px] sm:text-xs"
                >
                  {v.status}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "completed") return "default";
  if (status === "failed") return "destructive";
  if (status === "manual_pending" || status === "manual_completed") return "outline";
  return "secondary";
}
