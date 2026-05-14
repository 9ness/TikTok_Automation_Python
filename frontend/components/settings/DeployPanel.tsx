"use client";

import {
  AlertCircle,
  CheckCircle2,
  Container,
  Cpu,
  Database,
  HardDrive,
  Loader2,
  Play,
  RefreshCw,
  RotateCw,
  Server,
  Terminal,
  Wrench,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  type DeployServiceName,
  useDeployContainers,
  useDeployHealth,
  useDeployLog,
  useDeployRebuild,
  useDeployRestart,
  useDeployRun,
  useDeploySystem,
} from "@/lib/queries/deploy";
import { cn } from "@/lib/utils";

/**
 * Panel "Deploy" del Settings — botones de acción + estado del host y
 * containers. Está pensado para que un usuario sin experiencia técnica
 * pueda desplegar, reiniciar y diagnosticar sin SSH.
 *
 * Diseña a prueba de pánico:
 *   - Cada acción destructiva pide confirmación (AlertDialog).
 *   - Estado del webhook_listener bien visible (rojo si caído → todos los
 *     botones disabled con explicación).
 *   - Log en vivo con polling 3s tras una acción → 15s en reposo.
 */
export function DeployPanel() {
  const health = useDeployHealth();
  const reachable = health.data?.reachable === true;

  const containers = useDeployContainers({ enabled: reachable });
  const system = useDeploySystem({ enabled: reachable });

  const [livePolling, setLivePolling] = useState(false);
  const log = useDeployLog({ enabled: reachable, lines: 200, live: livePolling });

  // Tras pulsar un botón, refrescamos el log más rápido durante 2 min,
  // luego volvemos al ritmo lento.
  const liveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startLivePoll = () => {
    setLivePolling(true);
    if (liveTimerRef.current) clearTimeout(liveTimerRef.current);
    liveTimerRef.current = setTimeout(() => setLivePolling(false), 120_000);
  };
  useEffect(() => () => {
    if (liveTimerRef.current) clearTimeout(liveTimerRef.current);
  }, []);

  const runDeploy = useDeployRun();
  const rebuild = useDeployRebuild();
  const restart = useDeployRestart();

  const busy = runDeploy.isPending || rebuild.isPending || restart.isPending;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Wrench className="h-4 w-4 text-brand-cyan" />
              Deploy
            </CardTitle>
            <CardDescription>
              Despliegues, rebuilds y reinicios sin SSH.
            </CardDescription>
          </div>
          <HealthBadge reachable={reachable} loading={health.isLoading} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {!reachable && !health.isLoading && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="space-y-1">
              <p className="font-medium">
                El webhook listener no responde
              </p>
              <p className="text-xs">
                {health.data?.error ??
                  "Comprueba en el server: sudo systemctl status tiktok-webhook"}
                . Hasta que esté activo, no puedo lanzar deploys ni reinicios
                desde aquí.
              </p>
            </div>
          </div>
        )}

        {/* ----- Acciones principales ----- */}
        <div className="grid gap-2 sm:grid-cols-2">
          <ActionButton
            label="Deploy ahora"
            description="git pull + rebuild si cambió código"
            icon={Play}
            confirmTitle="¿Lanzar deploy ahora?"
            confirmBody="Hará git pull en main y si hay cambios reconstruye los containers afectados. Tarda ~5–10 min la primera vez."
            confirmActionLabel="Lanzar deploy"
            onAction={async () => {
              await runDeploy.mutateAsync();
              startLivePoll();
            }}
            disabled={!reachable || busy}
            loading={runDeploy.isPending}
            tone="primary"
          />

          <ActionButton
            label="Rebuild containers"
            description="Forzar rebuild api + web (sin git pull)"
            icon={RefreshCw}
            confirmTitle="¿Rebuildear api y web?"
            confirmBody="Reconstruye las imágenes de api y web desde cero con el código actual. Útil tras tocar el .env o si algo se quedó raro."
            confirmActionLabel="Rebuild"
            onAction={async () => {
              await rebuild.mutateAsync({ services: ["api", "web"] });
              startLivePoll();
            }}
            disabled={!reachable || busy}
            loading={rebuild.isPending}
          />
        </div>

        {/* ----- Restart individual ----- */}
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Reiniciar un container (rápido, sin rebuild)
          </p>
          <div className="grid grid-cols-3 gap-2">
            {(["api", "web", "caddy"] as DeployServiceName[]).map((svc) => (
              <RestartButton
                key={svc}
                service={svc}
                disabled={!reachable || busy}
                onDone={startLivePoll}
                pending={restart.isPending && restart.variables?.service === svc}
                run={restart.mutateAsync}
              />
            ))}
          </div>
        </div>

        {/* ----- Estado containers ----- */}
        <ContainersBlock query={containers} />

        {/* ----- Host stats ----- */}
        <SystemBlock query={system} />

        {/* ----- Log en vivo ----- */}
        <LogBlock
          log={log.data?.log ?? ""}
          loading={log.isLoading}
          live={livePolling}
        />

        {/* ----- Errores recientes (toast-style) ----- */}
        {(runDeploy.error || rebuild.error || restart.error) && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
            {String(
              runDeploy.error?.message ??
                rebuild.error?.message ??
                restart.error?.message,
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Subcomponentes
// ---------------------------------------------------------------------------
function HealthBadge({
  reachable,
  loading,
}: {
  reachable: boolean;
  loading: boolean;
}) {
  if (loading) {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        comprobando
      </Badge>
    );
  }
  if (reachable) {
    return (
      <Badge variant="outline" className="gap-1 border-emerald-500/40 text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        listener OK
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 border-destructive/40 text-destructive">
      <AlertCircle className="h-3 w-3" />
      listener caído
    </Badge>
  );
}

function ActionButton({
  label,
  description,
  icon: Icon,
  onAction,
  disabled,
  loading,
  confirmTitle,
  confirmBody,
  confirmActionLabel,
  tone,
}: {
  label: string;
  description: string;
  icon: typeof Play;
  onAction: () => Promise<unknown> | void;
  disabled?: boolean;
  loading?: boolean;
  confirmTitle: string;
  confirmBody: string;
  confirmActionLabel: string;
  tone?: "primary" | "default";
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant={tone === "primary" ? "default" : "outline"}
          className={cn(
            "h-auto justify-start gap-3 p-3 text-left",
            tone === "primary" &&
              "bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90",
          )}
          disabled={disabled}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
          ) : (
            <Icon className="h-4 w-4 shrink-0" />
          )}
          <span className="flex flex-col">
            <span className="text-sm font-medium leading-tight">{label}</span>
            <span className={cn(
              "text-[11px] leading-tight",
              tone === "primary" ? "text-white/80" : "text-muted-foreground",
            )}>
              {description}
            </span>
          </span>
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{confirmTitle}</AlertDialogTitle>
          <AlertDialogDescription>{confirmBody}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={() => void onAction()}>
            {confirmActionLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function RestartButton({
  service,
  disabled,
  pending,
  onDone,
  run,
}: {
  service: DeployServiceName;
  disabled: boolean;
  pending: boolean;
  onDone: () => void;
  run: (args: { service: DeployServiceName }) => Promise<unknown>;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={disabled}
        >
          {pending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RotateCw className="h-3 w-3" />
          )}
          {service}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Reiniciar {service}?</AlertDialogTitle>
          <AlertDialogDescription>
            Reinicia el container sin rebuild (rápido, ~5s). Útil tras tocar
            el .env o si el servicio se quedó tieso.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            onClick={async () => {
              await run({ service });
              onDone();
            }}
          >
            Reiniciar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function ContainersBlock({
  query,
}: {
  query: ReturnType<typeof useDeployContainers>;
}) {
  const items = query.data?.containers ?? [];
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Container className="h-3.5 w-3.5 text-muted-foreground" />
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Containers
        </p>
        {query.isFetching && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        )}
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {query.isLoading ? "cargando…" : "(sin datos)"}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((c, i) => {
            const name = c.Service ?? c.Name ?? `c${i}`;
            const state = (c.State ?? "").toLowerCase();
            const health = (c.Health ?? "").toLowerCase();
            const isHealthy =
              state === "running" && (health === "healthy" || health === "");
            return (
              <li
                key={name}
                className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 px-2 py-1.5 text-xs"
              >
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    isHealthy
                      ? "bg-emerald-500"
                      : state === "running"
                        ? "bg-amber-500"
                        : "bg-rose-500",
                  )}
                />
                <span className="font-medium">{name}</span>
                <Badge variant="outline" className="text-[10px]">
                  {state || "?"}
                </Badge>
                {health && (
                  <Badge variant="outline" className="text-[10px]">
                    {health}
                  </Badge>
                )}
                <span className="ml-auto truncate text-muted-foreground">
                  {c.Status}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function SystemBlock({
  query,
}: {
  query: ReturnType<typeof useDeploySystem>;
}) {
  const sys = query.data;
  if (!sys) {
    return null;
  }
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Server className="h-3.5 w-3.5 text-muted-foreground" />
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Host
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {sys.uptime_seconds != null && (
          <Stat
            icon={Cpu}
            label="uptime"
            value={formatUptime(sys.uptime_seconds)}
          />
        )}
        {sys.disk && (
          <Stat
            icon={HardDrive}
            label="disco"
            value={`${sys.disk.free_gb.toFixed(0)} GB libres`}
            sub={`${sys.disk.used_pct?.toFixed(0)}% usado`}
            warn={sys.disk.used_pct != null && sys.disk.used_pct >= 85}
          />
        )}
        {sys.memory && (
          <Stat
            icon={Database}
            label="memoria"
            value={`${sys.memory.available_gb.toFixed(1)} GB libres`}
            sub={`${sys.memory.used_pct?.toFixed(0)}% usado`}
            warn={sys.memory.used_pct != null && sys.memory.used_pct >= 90}
          />
        )}
        {sys.load_avg && (
          <Stat
            icon={Cpu}
            label="carga (1/5/15m)"
            value={sys.load_avg.map((n) => n.toFixed(2)).join(" · ")}
          />
        )}
      </div>
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  sub,
  warn,
}: {
  icon: typeof Cpu;
  label: string;
  value: string;
  sub?: string;
  warn?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-md border bg-muted/30 px-2 py-1.5",
        warn && "border-amber-500/40 bg-amber-500/5",
      )}
    >
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="text-sm font-medium">{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function LogBlock({
  log,
  loading,
  live,
}: {
  log: string;
  loading: boolean;
  live: boolean;
}) {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [log]);
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          deploy.log
        </p>
        {live && (
          <Badge variant="outline" className="gap-1 text-[10px]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
            en vivo
          </Badge>
        )}
        {loading && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        )}
      </div>
      <pre
        ref={ref}
        className="max-h-72 overflow-auto rounded-md border bg-zinc-950 p-2 font-mono text-[11px] leading-snug text-zinc-200"
      >
        {log || "(log vacío)"}
      </pre>
    </div>
  );
}

function formatUptime(s: number): string {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
