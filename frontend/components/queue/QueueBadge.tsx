"use client";

import { useMemo } from "react";
import { Activity, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import { useQueueStore } from "@/lib/stores/queueStore";
import { MODE_TO_PROGRAM, SUBMODULE_LABEL } from "@/lib/queue-meta";
import type { JobMode } from "@/lib/types/queue";
import { cn } from "@/lib/utils";

export function QueueBadge() {
  const activeMap = useQueueStore((s) => s.active);
  const connection = useQueueStore((s) => s.connection);
  const toggle = useDrawerStore((s) => s.toggleQueue);

  const summary = useMemo(() => buildSummary(activeMap), [activeMap]);
  const disconnected = connection !== "connected";

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggle}
      aria-label={disconnected ? "Cola (desconectado)" : "Cola"}
      className="relative gap-2"
      title={summary.tooltip}
    >
      {disconnected ? (
        <WifiOff className="h-4 w-4 text-amber-500" />
      ) : (
        <Activity className="h-4 w-4" />
      )}
      <span className="text-sm">Cola</span>
      {summary.runningCount > 0 && (
        <span
          className="absolute -right-0.5 -top-0.5 h-2 w-2 animate-pulse rounded-full bg-green-500"
          aria-label={`${summary.runningCount} jobs running`}
        />
      )}
      {summary.total > 0 && (
        <Badge
          variant={disconnected ? "secondary" : "destructive"}
          className={cn("h-5 min-w-[1.25rem] px-1 text-xs", disconnected && "opacity-60")}
        >
          {summary.total}
        </Badge>
      )}
    </Button>
  );
}

interface Summary {
  total: number;
  runningCount: number;
  // editor_auto/viralizacion añadidos para no perder typecheck en el for-of
  // que indexa por `MODE_TO_PROGRAM[j.mode]` (cuyo retorno incluye ambos).
  byProgram: {
    tiktok_shop: number;
    creator_reward: number;
    editor_auto: number;
    viralizacion: number;
  };
  byMode: Partial<Record<JobMode, number>>;
  tooltip: string;
}

function buildSummary(activeMap: Record<string, { mode: JobMode; status: string }>): Summary {
  const jobs = Object.values(activeMap);
  const total = jobs.length;
  const runningCount = jobs.filter((j) => j.status === "running").length;

  const byProgram = { tiktok_shop: 0, creator_reward: 0, editor_auto: 0, viralizacion: 0 };
  const byMode: Partial<Record<JobMode, number>> = {};
  for (const j of jobs) {
    byProgram[MODE_TO_PROGRAM[j.mode]] += 1;
    byMode[j.mode] = (byMode[j.mode] ?? 0) + 1;
  }

  const lines: string[] = [];
  if (total === 0) {
    lines.push("Sin jobs activos");
  } else {
    if (byProgram.tiktok_shop > 0) lines.push(`🛒 TikTok Shop: ${byProgram.tiktok_shop}`);
    if (byProgram.creator_reward > 0) {
      lines.push(`🏆 Creator Reward: ${byProgram.creator_reward}`);
      const crModes: JobMode[] = ["presidents", "pronosticos", "copyright", "subs_auto"];
      for (const m of crModes) {
        const n = byMode[m];
        if (n) lines.push(`  · ${SUBMODULE_LABEL[m]}: ${n}`);
      }
    }
    if (byProgram.editor_auto > 0) lines.push(`✂️ Editor Auto: ${byProgram.editor_auto}`);
    if (byProgram.viralizacion > 0) lines.push(`🚀 Tiktok Shop AI Pro: ${byProgram.viralizacion}`);
    if (runningCount > 0) lines.push(`(${runningCount} en ejecución)`);
  }

  return { total, runningCount, byProgram, byMode, tooltip: lines.join("\n") };
}
