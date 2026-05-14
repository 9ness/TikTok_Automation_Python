"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Film,
  Loader2,
  Scissors,
  Sparkles,
  Timer,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useJobLogs, useJobSummary } from "@/lib/queries/queue";

interface Props {
  jobId: string;
  title: string;
  isRunning: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Detalle de un job en dos vistas:
 *   - "Resumen": métricas pre-procesadas (duración antes/después, % cortado,
 *     quality score, breakdown por fuente, false-starts detectados, silencios
 *     remanentes). Vista por defecto, lectura humana.
 *   - "Logs": salida raw línea-a-línea (estilo terminal) para deep-debug.
 *
 * Ambas refrescan automáticamente cada 2-3s mientras el job esté running.
 */
export function JobDetailDialog({ jobId, title, isRunning, open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* w-[calc(100vw-1rem)] clamp al viewport en móvil; max-h-[95vh]
          overflow-y-auto para que en móvil el contenido scrollee dentro
          del dialog en lugar de salirse. p-3 en móvil para no comer ancho. */}
      <DialogContent
        className={
          "max-h-[95vh] w-[calc(100vw-1rem)] max-w-3xl overflow-y-auto p-3 sm:p-6"
        }
      >
        <DialogHeader>
          <DialogTitle className="truncate text-sm sm:text-base">
            <span className="text-muted-foreground">Detalle · </span>
            <span className="font-mono text-xs sm:text-sm">{jobId.slice(0, 8)}</span>
            <span className="ml-1 text-muted-foreground">· {title}</span>
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="summary" className="flex flex-col gap-3">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="summary" className="text-xs sm:text-sm">
              Resumen
            </TabsTrigger>
            <TabsTrigger value="logs" className="text-xs sm:text-sm">
              Logs detallados
            </TabsTrigger>
          </TabsList>
          <TabsContent value="summary">
            <SummaryView jobId={jobId} isRunning={isRunning} open={open} />
          </TabsContent>
          <TabsContent value="logs">
            <LogsView jobId={jobId} isRunning={isRunning} open={open} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Tab: Resumen — métricas humanas del job
// ---------------------------------------------------------------------------
function SummaryView({ jobId, isRunning, open }: { jobId: string; isRunning: boolean; open: boolean }) {
  const q = useJobSummary(open ? jobId : null, { live: open && isRunning });
  if (q.isLoading) {
    return (
      <div className="flex h-40 items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <p className="text-sm text-destructive">
        Error: {(q.error as Error)?.message ?? "no se pudo cargar el resumen"}
      </p>
    );
  }

  const s = q.data;

  // Si no hay diagnóstico (jobs que no son editor_auto), vista mínima.
  if (!s.has_diagnostic) {
    return (
      <div className="space-y-3">
        <MetricGrid
          metrics={[
            { label: "Estado", value: s.status },
            {
              label: "Tiempo de generación",
              value: s.generation_seconds != null ? formatSeconds(s.generation_seconds) : "—",
            },
            {
              label: "Duración del vídeo",
              value:
                s.output_duration_seconds != null
                  ? formatDuration(s.output_duration_seconds)
                  : "—",
            },
          ]}
        />
        <p className="text-xs text-muted-foreground">
          (Resumen detallado disponible solo para jobs de Editor Auto.)
        </p>
        {s.error && (
          <div className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            {s.error}
          </div>
        )}
      </div>
    );
  }

  const inputDur = s.input_duration_seconds ?? 0;
  const outputDur =
    s.output_duration_seconds ?? s.output_duration_seconds_calc ?? 0;
  const cutS = s.cut_duration_seconds ?? 0;
  const cutPct = s.cut_pct ?? 0;
  const score = s.quality_score;

  return (
    <div className="space-y-4">
      {/* Métricas principales */}
      <MetricGrid
        metrics={[
          {
            label: "Duración original",
            value: formatDuration(inputDur),
            icon: <Film className="h-3 w-3" />,
          },
          {
            label: "Duración final",
            value: formatDuration(outputDur),
            highlight: true,
            icon: <Film className="h-3 w-3" />,
          },
          {
            label: "Recortado",
            value: `${formatDuration(cutS)} (${cutPct.toFixed(0)}%)`,
            icon: <Scissors className="h-3 w-3" />,
          },
          {
            label: "Tiempo de generación",
            value:
              s.generation_seconds != null ? formatSeconds(s.generation_seconds) : "—",
            icon: <Timer className="h-3 w-3" />,
          },
        ]}
      />

      {/* Quality score */}
      {score != null && (
        <QualityCard score={score} verdict={s.quality_verdict ?? ""} />
      )}

      {/* Breakdown de cortes */}
      <section className="space-y-2">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <Scissors className="h-3 w-3" /> Qué se ha recortado
        </h4>
        <div className="space-y-1.5 rounded-md border bg-card/50 p-3 text-xs">
          {s.head_trim_seconds != null && s.head_trim_seconds > 0 && (
            <CutRow
              label="Silencio inicial"
              value={`${s.head_trim_seconds.toFixed(2)}s`}
              count={1}
            />
          )}
          {s.tail_trim_seconds != null && s.tail_trim_seconds > 0 && (
            <CutRow
              label="Silencio final"
              value={`${s.tail_trim_seconds.toFixed(2)}s`}
              count={1}
            />
          )}
          {s.n_long_gaps_cut != null && s.n_long_gaps_cut > 0 && (
            <CutRow
              label="Pausas entre frases (≥0.5s)"
              count={s.n_long_gaps_cut}
            />
          )}
          {s.cuts_by_source?.acoustic != null && s.cuts_by_source.acoustic > 0 && (
            <CutRow
              label="Silencios acústicos (Silero + amplitud)"
              count={s.cuts_by_source.acoustic}
              hint="ruidos de boca, respiración, ejem ejem"
            />
          )}
          {s.n_phantom_words != null && s.n_phantom_words > 0 && (
            <CutRow
              label="Palabras fantasma de Whisper"
              count={s.n_phantom_words}
              hint="alucinaciones dentro de silencios"
            />
          )}
          {s.cuts_by_source?.ai != null && s.cuts_by_source.ai > 0 && (
            <CutRow
              label="Cortes IA general (head/tail/gaps)"
              count={s.cuts_by_source.ai}
            />
          )}
          {s.n_false_starts_cut != null && s.n_false_starts_cut > 0 && (
            <CutRow
              label="Equivocaciones / frases repetidas"
              count={s.n_false_starts_cut}
              highlight
            />
          )}
        </div>
      </section>

      {/* False-starts con texto */}
      {s.false_starts_preview && s.false_starts_preview.length > 0 && (
        <section className="space-y-2">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Wand2 className="h-3 w-3" /> Frases reformuladas por la IA
          </h4>
          <ul className="space-y-2">
            {s.false_starts_preview.map((fs, i) => (
              <li
                key={i}
                className="rounded-md border bg-card/50 p-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline" className="text-[10px]">
                    {fs.kind ?? "?"}
                  </Badge>
                  {fs.reason && (
                    <span className="break-words text-muted-foreground">
                      {fs.reason}
                    </span>
                  )}
                </div>
                {/* En móvil los dos bloques (cortado / mantenido) van uno
                    sobre otro; en sm+ van lado a lado. break-words evita
                    overflow horizontal con frases largas. */}
                <div className="mt-1 grid gap-1 sm:grid-cols-2">
                  <div className="break-words">
                    <span className="text-muted-foreground">✂ cortado: </span>
                    <span className="text-destructive line-through">
                      {fs.first_attempt ?? "—"}
                    </span>
                  </div>
                  <div className="break-words">
                    <span className="text-muted-foreground">✓ mantenido: </span>
                    <span className="text-emerald-500">
                      {fs.kept_version ?? "—"}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Silencios remanentes (lo que NO se cortó pero debería) */}
      {s.n_silences_remaining != null && s.n_silences_remaining > 0 && (
        <section className="space-y-2">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-amber-500">
            <AlertTriangle className="h-3 w-3" /> Silencios sin cortar
          </h4>
          <ul className="space-y-1">
            {s.silences_remaining_preview?.map((p, i) => (
              <li
                key={i}
                className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs"
              >
                {/* Línea principal: duración + entre qué palabras. flex-wrap
                    para que en móvil rompa si las palabras son largas. */}
                <div className="flex flex-wrap items-baseline gap-x-1">
                  <span className="font-mono font-semibold">
                    {p.duration_s?.toFixed(2)}s
                  </span>
                  <span className="text-muted-foreground">entre</span>
                  <code className="break-all rounded bg-muted px-1">
                    {p.before_word ?? "?"}
                  </code>
                  <span className="text-muted-foreground">y</span>
                  <code className="break-all rounded bg-muted px-1">
                    {p.after_word ?? "?"}
                  </code>
                </div>
                {/* Timestamps input en línea aparte → no se sale en móvil */}
                <div className="mt-0.5 font-mono text-[10px] text-muted-foreground sm:text-xs">
                  input[{p.input_start?.toFixed(2)}s, {p.input_end?.toFixed(2)}s]
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Tools usadas en el flujo */}
      {s.tools_used && s.tools_used.length > 0 && (
        <section className="space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Herramientas aplicadas
          </h4>
          <div className="flex flex-wrap gap-1">
            {s.tools_used.map((t) => (
              <Badge key={t} variant="secondary" className="text-[10px]">
                {t}
              </Badge>
            ))}
          </div>
        </section>
      )}

      {s.error && (
        <div className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
          {s.error}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componentes del resumen
// ---------------------------------------------------------------------------
function MetricGrid({
  metrics,
}: {
  metrics: {
    label: string;
    value: string;
    icon?: React.ReactNode;
    highlight?: boolean;
  }[];
}) {
  return (
    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 sm:gap-2">
      {metrics.map((m) => (
        <div
          key={m.label}
          className={`min-w-0 rounded-md border bg-card/50 p-2 sm:p-2.5 ${
            m.highlight ? "border-emerald-500/40 bg-emerald-500/5" : ""
          }`}
        >
          <div className="flex items-center gap-1 truncate text-[9px] uppercase tracking-wider text-muted-foreground sm:text-[10px]">
            {m.icon}
            <span className="truncate">{m.label}</span>
          </div>
          <div className="mt-0.5 truncate text-sm font-semibold tabular-nums sm:text-base">
            {m.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function QualityCard({ score, verdict }: { score: number; verdict: string }) {
  const color =
    score >= 90
      ? "text-emerald-500 border-emerald-500/40 bg-emerald-500/5"
      : score >= 70
        ? "text-cyan-500 border-cyan-500/40 bg-cyan-500/5"
        : score >= 50
          ? "text-amber-500 border-amber-500/40 bg-amber-500/5"
          : "text-destructive border-destructive/40 bg-destructive/10";

  return (
    <div
      className={`flex items-center gap-2 rounded-md border p-2 sm:gap-3 sm:p-3 ${color}`}
    >
      {score >= 90 ? (
        <Sparkles className="h-5 w-5 shrink-0" />
      ) : score < 50 ? (
        <AlertTriangle className="h-5 w-5 shrink-0" />
      ) : (
        <CheckCircle2 className="h-5 w-5 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1">
          <span className="text-xl font-bold tabular-nums sm:text-2xl">
            {score}
          </span>
          <span className="text-xs text-muted-foreground sm:text-sm">/100</span>
        </div>
        <p className="break-words text-[11px] sm:text-xs">{verdict}</p>
      </div>
    </div>
  );
}

function CutRow({
  label,
  value,
  count,
  hint,
  highlight,
}: {
  label: string;
  value?: string;
  count?: number;
  hint?: string;
  highlight?: boolean;
}) {
  // En móvil el hint pasa a una segunda línea para que no fuerce truncate
  // ni corte el valor numérico de la derecha.
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className={highlight ? "font-medium text-emerald-500" : ""}>
        {label}
      </span>
      <span className="ml-auto shrink-0 font-mono tabular-nums">
        {value ?? (count != null ? `${count}` : "")}
      </span>
      {hint && (
        <span className="basis-full text-[10px] text-muted-foreground sm:text-xs">
          · {hint}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Logs raw (extraído del antiguo JobLogsDialog)
// ---------------------------------------------------------------------------
function LogsView({
  jobId,
  isRunning,
  open,
}: {
  jobId: string;
  isRunning: boolean;
  open: boolean;
}) {
  const logs = useJobLogs(open ? jobId : null, { live: open && isRunning });
  const [filter, setFilter] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const lines = logs.data?.lines ?? [];
  const filtered = useMemo(() => {
    if (!filter.trim()) return lines;
    const q = filter.toLowerCase();
    return lines.filter((l) => l.toLowerCase().includes(q));
  }, [lines, filter]);

  useEffect(() => {
    if (!autoScroll || !containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [filtered.length, autoScroll]);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  };

  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      toast.success(`${lines.length} líneas copiadas.`);
    } catch {
      toast.error("No se pudo copiar.");
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Input
          placeholder={`Filtrar ${lines.length}…`}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-8 min-w-0 flex-1 text-xs"
        />
        <Button
          size="sm"
          variant="outline"
          onClick={copyAll}
          disabled={lines.length === 0}
          className="h-8 shrink-0 gap-1 text-xs"
        >
          <Copy className="h-3 w-3" />
          <span className="hidden sm:inline">Copiar</span>
        </Button>
      </div>
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="h-[50vh] overflow-y-auto rounded-md border bg-zinc-950 p-2 font-mono text-[10px] leading-relaxed text-zinc-200 sm:h-[55vh] sm:p-3 sm:text-[11px]"
      >
        {logs.isLoading && (
          <div className="flex items-center gap-2 text-zinc-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            Cargando logs…
          </div>
        )}
        {logs.isError && (
          <p className="text-red-400">
            Error: {(logs.error as Error)?.message}
          </p>
        )}
        {!logs.isLoading && filtered.length === 0 && (
          <p className="text-zinc-500">
            {lines.length === 0
              ? "(sin logs registrados)"
              : `Sin resultados para "${filter}"`}
          </p>
        )}
        {filtered.map((line, i) => (
          <div key={i} className="whitespace-pre-wrap break-words">
            <span className="select-none pr-2 text-zinc-600">
              {String(i + 1).padStart(3, " ")}
            </span>
            <span className={lineColor(line)}>{line}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {filter ? `${filtered.length} / ${lines.length}` : `${lines.length} líneas`}
          {isRunning && (
            <span className="ml-2 inline-flex items-center gap-1 text-emerald-500">
              <Loader2 className="h-3 w-3 animate-spin" />
              en vivo
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

function lineColor(line: string): string {
  if (/❌|⚠️|⚠|error|Failed/i.test(line)) return "text-red-400";
  if (/✅|🏆|completado|listo/i.test(line)) return "text-emerald-400";
  if (/👻|🤖|🛡️|📉|🎙️/.test(line)) return "text-amber-300";
  if (/\[silence_cutter\]|\[editor_auto\]|\[subs_auto\]/.test(line))
    return "text-cyan-300";
  return "";
}

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------
function formatSeconds(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`;
  const min = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${min}m ${sec}s`;
}

function formatDuration(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`;
  const min = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${min}:${sec.toString().padStart(2, "0")}`;
}
