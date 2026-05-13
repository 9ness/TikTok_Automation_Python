"use client";

import { useState } from "react";
import {
  Activity,
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  useAppLogs,
  useDeployDetail,
  useDiagnosticsSummary,
} from "@/lib/queries/diagnostics";
import { cn } from "@/lib/utils";

/**
 * Panel "🩺 Diagnóstico" en la sidebar (parte inferior).
 *
 * 3 tabs:
 *   - Resumen   → servicios + git + cola + disco
 *   - Deploy    → estado del último deploy + tail del log
 *   - App       → tail del log de la app
 *
 * Refresh manual con botón + refetch automático 30s.
 */
type Tab = "resumen" | "deploy" | "app";

export function DiagnosticsPanel() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("resumen");

  return (
    <div className="rounded-md border bg-card/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-xs font-medium hover:bg-accent/40"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <Activity className="h-3.5 w-3.5 text-brand-cyan" />
        Diagnóstico
      </button>
      {open && (
        <div className="space-y-2 border-t p-2">
          <TabBar tab={tab} onChange={setTab} />
          {tab === "resumen" && <ResumenTab />}
          {tab === "deploy" && <DeployTab />}
          {tab === "app" && <AppTab />}
        </div>
      )}
    </div>
  );
}

function TabBar({ tab, onChange }: { tab: Tab; onChange: (t: Tab) => void }) {
  const items: { key: Tab; label: string }[] = [
    { key: "resumen", label: "Resumen" },
    { key: "deploy", label: "Deploy" },
    { key: "app", label: "App" },
  ];
  return (
    <div className="flex items-center gap-1 border-b text-[11px]">
      {items.map((it) => (
        <button
          key={it.key}
          type="button"
          onClick={() => onChange(it.key)}
          className={cn(
            "px-2 py-1 transition-colors",
            tab === it.key
              ? "border-b-2 border-primary font-semibold text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

function ResumenTab() {
  const q = useDiagnosticsSummary();

  return (
    <div className="space-y-2 text-[11px]">
      <Button
        size="sm"
        variant="outline"
        className="h-6 w-full gap-1 text-[10px]"
        onClick={() => q.refetch()}
        disabled={q.isFetching}
      >
        {q.isFetching ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <RefreshCw className="h-3 w-3" />
        )}
        Refrescar
      </Button>
      {!q.data && (
        <p className="text-muted-foreground">
          {q.isLoading ? "Cargando…" : "Sin datos."}
        </p>
      )}
      {q.data && (
        <>
          <Section title="Servicios">
            {Object.entries(q.data.services).map(([svc, status]) => (
              <ServiceRow key={svc} name={svc} status={status} />
            ))}
          </Section>

          <Section title="Git">
            {q.data.git.sha_short ? (
              <>
                <KV
                  label="HEAD"
                  value={
                    <span className="font-mono">{q.data.git.sha_short}</span>
                  }
                />
                <p className="truncate text-muted-foreground" title={q.data.git.message ?? ""}>
                  {q.data.git.message}
                </p>
                {q.data.git.date && (
                  <p className="text-[10px] text-muted-foreground">
                    {q.data.git.date}
                  </p>
                )}
              </>
            ) : (
              <p className="text-muted-foreground">(.git no disponible)</p>
            )}
          </Section>

          <Section title="Último deploy">
            <DeployState status={q.data.deploy} />
          </Section>

          <Section title="Cola">
            <KV label="total" value={q.data.queue.total} />
            <KV
              label="pendientes / corriendo"
              value={`${q.data.queue.pending} / ${q.data.queue.running}`}
            />
            <KV
              label="completados / fallados"
              value={`${q.data.queue.completed} / ${q.data.queue.failed}`}
            />
          </Section>

          <Section title="Disco">
            {q.data.disk.error ? (
              <p className="text-destructive">{q.data.disk.error}</p>
            ) : (
              <KV
                label="libre / total"
                value={`${q.data.disk.free_gb}G / ${q.data.disk.total_gb}G (${q.data.disk.used_pct}%)`}
              />
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function DeployTab() {
  const q = useDeployDetail();
  return (
    <div className="space-y-1.5 text-[11px]">
      {q.data && <DeployState status={q.data.status} />}
      <pre className="max-h-[40vh] overflow-auto rounded bg-muted/30 p-1.5 font-mono text-[10px] leading-tight">
        {q.data?.log_tail || (q.isLoading ? "Cargando…" : "(sin log)")}
      </pre>
    </div>
  );
}

function AppTab() {
  const q = useAppLogs();
  return (
    <div className="space-y-1.5 text-[11px]">
      {q.data && q.data.source !== "none" && (
        <p className="text-[10px] text-muted-foreground">
          fuente: {q.data.source}
        </p>
      )}
      <pre className="max-h-[40vh] overflow-auto rounded bg-muted/30 p-1.5 font-mono text-[10px] leading-tight">
        {q.data?.log_tail ||
          (q.isLoading
            ? "Cargando…"
            : "(sin log — montar `logs/` en /host_data/logs)")}
      </pre>
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
    <div>
      <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      <div className="space-y-0.5 pl-1">{children}</div>
    </div>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </div>
  );
}

function ServiceRow({ name, status }: { name: string; status: string }) {
  const isActive = status === "active";
  const isInactive = status === "inactive" || status === "unknown";
  const isFailed = status === "failed";
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-1.5 truncate">
        {isActive ? (
          <Check className="h-3 w-3 text-green-500" />
        ) : isFailed ? (
          <AlertCircle className="h-3 w-3 text-destructive" />
        ) : (
          <span className="h-2 w-2 rounded-full bg-muted-foreground/50" />
        )}
        <span className="truncate">{name}</span>
      </span>
      <span
        className={cn(
          "font-mono text-[10px]",
          isActive && "text-green-500",
          isFailed && "text-destructive",
          isInactive && "text-muted-foreground",
        )}
      >
        {status}
      </span>
    </div>
  );
}

function DeployState({
  status,
}: {
  status: import("@/lib/queries/diagnostics").DeployStatus;
}) {
  if (!status || !status.state) {
    return <p className="text-muted-foreground">(sin deploys aún)</p>;
  }
  const state = status.state;
  const stateColor =
    state === "success"
      ? "text-green-500"
      : state === "failed"
        ? "text-destructive"
        : "text-amber-500";
  const elapsed =
    status.started_at && status.finished_at
      ? `${Math.max(0, status.finished_at - status.started_at)}s`
      : null;
  // Timestamp absoluto del último cambio de estado. Se prefiere `finished_at`
  // (deploy ya completado/fallado); en `running` cae a `updated_at` o
  // `started_at` para mostrar al menos "cuándo empezó".
  const eventTs =
    status.finished_at ?? status.updated_at ?? status.started_at ?? null;
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">estado</span>
        <span className={cn("font-mono font-semibold", stateColor)}>
          {state}
        </span>
      </div>
      {eventTs && (
        <KV
          label={state === "running" ? "empezó" : "cuándo"}
          value={formatRelativeTimestamp(eventTs)}
        />
      )}
      {status.current_sha && (
        <KV label="commit" value={<span className="font-mono">{status.current_sha}</span>} />
      )}
      {status.previous_sha && status.current_sha !== status.previous_sha && (
        <KV
          label="anterior"
          value={
            <span className="font-mono text-muted-foreground">
              {status.previous_sha}
            </span>
          }
        />
      )}
      {elapsed && <KV label="duración" value={elapsed} />}
      {status.error && (
        <p className="truncate text-destructive" title={status.error}>
          ⚠ {status.error}
        </p>
      )}
      {status.note && (
        <p className="text-[10px] text-muted-foreground">{status.note}</p>
      )}
    </div>
  );
}

/** "hoy 14:35", "ayer 09:12", "lun 14:00", "12/05 14:35" según antigüedad. */
function formatRelativeTimestamp(unixSeconds: number): string {
  const d = new Date(unixSeconds * 1000);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000);
  const time = d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  if (sameDay) return `hoy ${time}`;
  if (isYesterday) return `ayer ${time}`;
  if (diffDays < 7) {
    const wd = d.toLocaleDateString("es-ES", { weekday: "short" });
    return `${wd} ${time}`;
  }
  const date = d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit" });
  return `${date} ${time}`;
}
