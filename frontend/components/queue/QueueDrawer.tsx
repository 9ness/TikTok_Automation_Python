"use client";

import { useMemo, useState } from "react";
import { Activity, ChevronDown, ChevronRight, Trash2, WifiOff, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useClearRecentJobs } from "@/lib/queries/queue";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import { useQueueStore } from "@/lib/stores/queueStore";
import {
  MODE_TO_PROGRAM,
  PROGRAM_LABEL,
  SUBMODULE_LABEL,
  type Program,
} from "@/lib/queue-meta";
import type { ActiveJob, JobMode } from "@/lib/types/queue";
import { useEsPro, useMe } from "@/lib/queries/auth";
import { colorDeUsuario, nombreDueno } from "@/lib/usuarios-color";
import { cn } from "@/lib/utils";
import { AvisoDespliegue } from "./AvisoDespliegue";
import { JobCard } from "./JobCard";

type ProgramFilter = "all" | Program;
type SubmoduleFilter = "all" | JobMode;

const CR_SUBMODULES: JobMode[] = ["presidents", "pronosticos", "copyright", "subs_auto"];

export function QueueDrawer() {
  const esAdmin = useQueueStore((s) => s.esAdmin);
  const otros = useQueueStore((s) => s.otros);
  const verDe = useQueueStore((s) => s.verDe);
  const setVerDe = useQueueStore((s) => s.setVerDe);
  const open = useDrawerStore((s) => s.queueOpen);
  const close = useDrawerStore((s) => s.closeQueue);
  const activeMap = useQueueStore((s) => s.active);
  const recent = useQueueStore((s) => s.recent);
  const connection = useQueueStore((s) => s.connection);

  const esPro = useEsPro();
  const me = useMe();
  const [programFilter, setProgramFilter] = useState<ProgramFilter>("all");
  const [crSubFilter, setCrSubFilter] = useState<SubmoduleFilter>("all");
  const [recentOpen, setRecentOpen] = useState(true);

  const clearRecentLocal = useQueueStore((s) => s.clearRecent);
  const clearRecentMutation = useClearRecentJobs();

  async function handleClearAll() {
    try {
      const res = await clearRecentMutation.mutateAsync();
      clearRecentLocal();
      toast.success(`${res.removed} job(s) eliminados del historial.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al limpiar.");
    }
  }

  const active = useMemo(
    () =>
      Object.values(activeMap).sort((a, b) => {
        // Lo que está corriendo, arriba. Y los pendientes por su PUESTO real
        // en la cola, no por hora de creación: con el reordenado a mano (subir
        // a lo alto) y la prioridad de los trabajos de admin, el orden por
        // fecha ya no era el orden en que se van a ejecutar — la lista decía
        // una cosa y la etiqueta "nº 3 de 9" otra.
        const corriendoA = a.status === "running" ? 0 : 1;
        const corriendoB = b.status === "running" ? 0 : 1;
        if (corriendoA !== corriendoB) return corriendoA - corriendoB;
        const posA = a.queue_position ?? Number.MAX_SAFE_INTEGER;
        const posB = b.queue_position ?? Number.MAX_SAFE_INTEGER;
        if (posA !== posB) return posA - posB;
        return a.created_at - b.created_at;
      }),
    [activeMap],
  );

  const filtered = useMemo(() => {
    return active.filter((j) => matchFilter(j, programFilter, crSubFilter));
  }, [active, programFilter, crSubFilter]);

  const grouped = useMemo(() => {
    const ts = filtered.filter((j) => MODE_TO_PROGRAM[j.mode] === "tiktok_shop");
    const cr = filtered.filter((j) => MODE_TO_PROGRAM[j.mode] === "creator_reward");
    const ea = filtered.filter((j) => MODE_TO_PROGRAM[j.mode] === "editor_auto");
    // El último grupo recoge lo suyo Y todo lo que no encajó en los
    // anteriores. Con `=== "viralizacion"` a secas, un modo nuevo que aún no
    // esté en MODE_TO_PROGRAM se contaba en el badge pero no se pintaba en
    // ningún sitio: el job existía y era invisible hasta terminar.
    const resto = filtered.filter(
      (j) => !ts.includes(j) && !cr.includes(j) && !ea.includes(j),
    );
    return { ts, cr, ea, vi: resto };
  }, [filtered]);

  if (!open) return null;
  const disconnected = connection !== "connected";

  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Cerrar cola"
        onClick={close}
        className="absolute inset-0 bg-black/40"
      />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l bg-card shadow-lg">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            {disconnected ? (
              <WifiOff className="h-4 w-4 text-amber-500" />
            ) : (
              <Activity className="h-4 w-4 text-green-600" />
            )}
            <h2 className="font-semibold">Cola</h2>
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                connection === "connected" && "bg-green-500",
                connection === "connecting" && "animate-pulse bg-amber-400",
                connection === "disconnected" && "bg-amber-500",
              )}
              aria-label={`WS ${connection}`}
            />
          </div>
          <Button size="icon" variant="ghost" aria-label="Cerrar cola" onClick={close}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Qué pasa con el despliegue. Va aquí porque la duda ("¿ya está
            subido lo nuevo?", "¿puedo mandar un vídeo o se corta?") siempre se
            tiene mirando la cola. */}
        <AvisoDespliegue enCurso={active.length} />

        {/* Multiusuario: cada uno ve LO SUYO. El admin puede mirar la de otro
            y se le avisa, en pequeño, de quién tiene algo en marcha — pediste
            que no ocupara. */}
        {esAdmin && (
          <div className="flex flex-wrap items-center gap-1.5 border-b px-4 pb-2 text-[11px]">
            <span className="text-muted-foreground">Viendo:</span>
            {[{ v: "", n: "La mía" }, { v: "todos", n: "Todas" }]
              // TODOS los usuarios, no solo los que tienen algo encolado: con
              // `Object.keys(otros)` no podías mirar la cola de Ana si estaba
              // vacía, que es justo cuando quieres comprobar que está vacía.
              .concat(
                (me.data?.usuarios ?? [])
                  .filter((u) => u.username !== me.data?.username)
                  .map((u) => ({ v: u.username, n: u.nombre })),
              )
              .map((o) => (
                <button
                  key={o.v || "mia"}
                  type="button"
                  onClick={() => setVerDe(o.v)}
                  className={cn(
                    "rounded border px-1.5 py-0.5 transition",
                    verDe === o.v
                      ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                      : "border-border/60 text-muted-foreground hover:border-foreground/40",
                  )}
                >
                  {o.n}
                </button>
              ))}
            {Object.entries(otros).length > 0 && verDe === "" && (
              <span className="flex flex-wrap items-center gap-1.5">
                {Object.entries(otros).map(([u, d]) => {
                  const color = colorDeUsuario(u);
                  return (
                    <span
                      key={u}
                      className={cn("inline-flex items-center gap-1", color.texto)}
                      title={
                        d.ejecutando > 0
                          ? `${d.ejecutando} en marcha de ${d.total}`
                          : `${d.total} esperando`
                      }
                    >
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          color.punto,
                          d.ejecutando > 0 && "animate-pulse",
                        )}
                      />
                      {nombreDueno(u)}: {d.total}
                      {d.ejecutando > 0 ? ` (${d.ejecutando} ▶)` : ""}
                    </span>
                  );
                })}
              </span>
            )}
          </div>
        )}

        {disconnected && (
          <div className="border-b bg-amber-500/10 px-4 py-2 text-xs text-amber-700 dark:text-amber-300">
            Desconectado del servidor — reintentando…
          </div>
        )}

        {/* Filtros por programa. A un `pro` (Ana, Mauro) NO se le enseñan: su
            menú es solo Tiktok Shop AI Pro, así que filtrar por Creator Reward
            o TikTok Shop le ofrece cosas que no puede tener — botones que
            siempre devuelven una lista vacía. */}
        {!esPro && (
        <div className="space-y-2 border-b px-4 py-3">
          <div className="flex flex-wrap gap-1">
            {(
              ["all", "tiktok_shop", "creator_reward", "editor_auto", "viralizacion"] as ProgramFilter[]
            ).map(
              (f) => (
                <Button
                  key={f}
                  size="sm"
                  variant={programFilter === f ? "default" : "outline"}
                  onClick={() => {
                    setProgramFilter(f);
                    if (f !== "creator_reward") setCrSubFilter("all");
                  }}
                  className="h-7 text-xs"
                >
                  {f === "all" ? "Todos" : PROGRAM_LABEL[f]}
                </Button>
              ),
            )}
          </div>
          {programFilter === "creator_reward" && (
            <div className="flex flex-wrap gap-1">
              <Button
                size="sm"
                variant={crSubFilter === "all" ? "default" : "outline"}
                onClick={() => setCrSubFilter("all")}
                className="h-7 text-xs"
              >
                Todos los nichos
              </Button>
              {CR_SUBMODULES.map((m) => (
                <Button
                  key={m}
                  size="sm"
                  variant={crSubFilter === m ? "default" : "outline"}
                  onClick={() => setCrSubFilter(m)}
                  className="h-7 text-xs"
                >
                  {SUBMODULE_LABEL[m]}
                </Button>
              ))}
            </div>
          )}
        </div>
        )}

        <div className="flex-1 overflow-y-auto p-4">
          <Section title={`Activos (${filtered.length})`}>
            {filtered.length === 0 ? (
              <p className="text-sm text-muted-foreground">No hay jobs activos.</p>
            ) : programFilter === "all" ? (
              <>
                {grouped.ts.length > 0 && (
                  <ProgramGroup label={PROGRAM_LABEL.tiktok_shop} jobs={grouped.ts} />
                )}
                {grouped.cr.length > 0 && (
                  <ProgramGroup label={PROGRAM_LABEL.creator_reward} jobs={grouped.cr} />
                )}
                {grouped.ea.length > 0 && (
                  <ProgramGroup label={PROGRAM_LABEL.editor_auto} jobs={grouped.ea} />
                )}
                {grouped.vi.length > 0 && (
                  <ProgramGroup label={PROGRAM_LABEL.viralizacion} jobs={grouped.vi} />
                )}
              </>
            ) : (
              <ul className="space-y-2">
                {filtered.map((j) => (
                  <li key={j.job_id}>
                    <JobCard job={j} />
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <section className="mt-6">
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setRecentOpen((v) => !v)}
                className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                {recentOpen ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                Recientes ({recent.length})
              </button>
              {recent.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleClearAll}
                  disabled={clearRecentMutation.isPending}
                  className="h-7 gap-1 text-xs text-muted-foreground hover:text-destructive"
                  aria-label="Limpiar todos los recientes"
                  title="Limpiar todos los recientes"
                >
                  <Trash2 className="h-3 w-3" />
                  Limpiar todos
                </Button>
              )}
            </div>
            {recentOpen && (
              <ul className="mt-2 space-y-2">
                {recent.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Sin jobs recientes.</p>
                ) : (
                  recent
                    .filter((j) => matchFilter(j, programFilter, crSubFilter))
                    .map((j) => (
                      <li key={j.job_id}>
                        <JobCard job={j} />
                      </li>
                    ))
                )}
              </ul>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}

function matchFilter(
  job: ActiveJob,
  programFilter: ProgramFilter,
  subFilter: SubmoduleFilter,
): boolean {
  if (programFilter === "all") return true;
  const program = MODE_TO_PROGRAM[job.mode];
  if (program !== programFilter) return false;
  if (programFilter === "creator_reward" && subFilter !== "all") {
    return job.mode === subFilter;
  }
  return true;
}

function ProgramGroup({ label, jobs }: { label: string; jobs: ActiveJob[] }) {
  return (
    <div className="mb-4">
      <p className="mb-2 text-xs font-medium text-muted-foreground">
        {label} <Badge variant="secondary" className="ml-1">{jobs.length}</Badge>
      </p>
      <ul className="space-y-2">
        {jobs.map((j) => (
          <li key={j.job_id}>
            <JobCard job={j} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}
