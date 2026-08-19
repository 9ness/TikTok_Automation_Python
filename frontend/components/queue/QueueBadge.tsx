"use client";

import { useMemo } from "react";
import { Activity, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import { useQueueStore } from "@/lib/stores/queueStore";
import { MODE_TO_PROGRAM, SUBMODULE_LABEL } from "@/lib/queue-meta";
import type { JobMode } from "@/lib/types/queue";
import { colorDeUsuario, nombreDueno } from "@/lib/usuarios-color";
import { cn } from "@/lib/utils";

export function QueueBadge() {
  const activeMap = useQueueStore((s) => s.active);
  const connection = useQueueStore((s) => s.connection);
  const otros = useQueueStore((s) => s.otros);
  const esAdmin = useQueueStore((s) => s.esAdmin);
  const toggle = useDrawerStore((s) => s.toggleQueue);

  const summary = useMemo(() => buildSummary(activeMap), [activeMap]);
  const disconnected = connection !== "connected";
  // Lo de los DEMÁS. Solo lo manda el servidor si quien mira es admin, así que
  // a Ana y Mauro esto les llega vacío y no ven nada — es lo suyo: no tienen
  // por qué saber en qué anda el otro.
  const deOtros = useMemo(
    () =>
      Object.entries(otros)
        .filter(([, v]) => (v?.total ?? 0) > 0)
        .sort(([a], [b]) => a.localeCompare(b)),
    [otros],
  );

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
      {/* Un circulito por cada OTRA persona con algo en la cola, de su color.
          Late si lo está ejecutando ahora y se queda quieto si solo espera:
          así se sabe de un vistazo si Ana está renderizando o solo ha dejado
          cosas puestas, sin abrir el cajón. */}
      {esAdmin &&
        deOtros.map(([quien, datos]) => {
          const color = colorDeUsuario(quien);
          const nombre = nombreDueno(quien);
          return (
            <span
              key={quien}
              title={
                datos.ejecutando > 0
                  ? `${nombre}: ${datos.ejecutando} en marcha de ${datos.total}`
                  : `${nombre}: ${datos.total} esperando`
              }
              className={cn(
                "flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-bold text-white",
                color.punto,
                datos.ejecutando > 0 && "animate-pulse",
              )}
            >
              {datos.total}
            </span>
          );
        })}
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
