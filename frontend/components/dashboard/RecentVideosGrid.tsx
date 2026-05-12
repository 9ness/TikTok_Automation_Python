"use client";

import { Film } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { VideoSummary } from "@/lib/types/dashboard";

export function RecentVideosGrid({ videos }: { videos: VideoSummary[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Vídeos recientes</CardTitle>
      </CardHeader>
      <CardContent>
        {videos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin generaciones recientes.</p>
        ) : (
          <ul className="space-y-2">
            {videos.map((v) => (
              <li
                key={v.generation_id}
                className="flex items-center gap-3 rounded-md border bg-card/50 p-2"
              >
                <div className="flex h-10 w-14 items-center justify-center rounded bg-muted">
                  <Film className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs">
                    {v.generation_id.slice(0, 8)}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {v.tier_used} · {v.created_at.slice(0, 10)} · ${v.cost_total.toFixed(3)}
                  </p>
                </div>
                <Badge variant={statusVariant(v.status)}>{v.status}</Badge>
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
