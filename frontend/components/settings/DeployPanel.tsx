"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Container,
  Cpu,
  Database,
  GitCommitHorizontal,
  HardDrive,
  Loader2,
  Play,
  RefreshCw,
  RotateCw,
  Server,
  Smartphone,
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
  type DeployStatus,
  useClaudeSdkFree,
  useClaudeSdkRestart,
  useDeployContainers,
  useDeployHealth,
  useDeployLog,
  useDeployRebuild,
  useDeployRestart,
  useDeployRun,
  useDeployStatus,
  useDeploySystem,
} from "@/lib/queries/deploy";
import { cn } from "@/lib/utils";

/**
 * Panel "Deploy" — diseñado para que un usuario sin experiencia técnica
 * pueda actualizar y diagnosticar sin SSH.
 *
 * Estructura:
 *   1. SMART DEPLOY (botón principal): el panel detecta si hay commits
 *      pendientes; el botón decide solo qué hacer (`deploy_safe.sh` ya es
 *      idempotente y rebuildea solo lo necesario).
 *   2. Estado en vivo: containers, host stats, log.
 *   3. Avanzado (colapsado): rebuild forzado, restart individual.
 *
 * El botón principal está deshabilitado cuando:
 *   - El listener no responde
 *   - Ya hay un deploy en curso
 *   - No hay commits pendientes Y no hay rebuild manual seleccionado
 */
export function DeployPanel() {
  const health = useDeployHealth();
  const reachable = health.data?.reachable === true;

  const status = useDeployStatus({ enabled: reachable, live: false });
  const inProgress = status.data?.deploy_in_progress === true;

  // Re-key polling para "en vivo": cuando deploy_in_progress=true, el panel
  // refresca cada 3s; en reposo cada 20s.
  const liveStatus = useDeployStatus({ enabled: reachable, live: inProgress });

  const containers = useDeployContainers({ enabled: reachable });
  const system = useDeploySystem({ enabled: reachable });

  const [logLive, setLogLive] = useState(false);
  const log = useDeployLog({ enabled: reachable, lines: 250, live: logLive || inProgress });
  const liveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startLivePoll = () => {
    setLogLive(true);
    if (liveTimerRef.current) clearTimeout(liveTimerRef.current);
    liveTimerRef.current = setTimeout(() => setLogLive(false), 180_000);
  };
  useEffect(
    () => () => {
      if (liveTimerRef.current) clearTimeout(liveTimerRef.current);
    },
    [],
  );

  const runDeploy = useDeployRun();
  const rebuild = useDeployRebuild();
  const restart = useDeployRestart();
  const sdkFree = useClaudeSdkFree();
  const sdkRestart = useClaudeSdkRestart();
  const sdkBusy = sdkFree.isPending || sdkRestart.isPending;
  const busy = runDeploy.isPending || rebuild.isPending || restart.isPending;

  // El status puede venir de la query inicial o la live — preferimos la
  // más reciente (live siempre tras la primera respuesta).
  const stat: DeployStatus | undefined = liveStatus.data ?? status.data;

  const [showAdvanced, setShowAdvanced] = useState(false);

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
              Despliegue inteligente y diagnóstico sin SSH.
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
              <p className="font-medium">El listener del host no responde</p>
              <p className="text-xs">
                {health.data?.error ??
                  "Conéctate por SSH y ejecuta: sudo systemctl restart tiktok-webhook"}
              </p>
            </div>
          </div>
        )}

        {/* ----- SMART DEPLOY ----- */}
        <SmartDeployBlock
          status={stat}
          loading={status.isLoading}
          inProgress={inProgress}
          disabled={!reachable || busy}
          pending={runDeploy.isPending}
          onDeploy={async () => {
            await runDeploy.mutateAsync();
            startLivePoll();
          }}
        />

        {/* ----- Estado containers ----- */}
        <ContainersBlock query={containers} />

        {/* ----- Host stats ----- */}
        <SystemBlock query={system} />

        {/* ----- Log ----- */}
        <LogBlock
          log={log.data?.log ?? ""}
          loading={log.isLoading}
          live={logLive || inProgress}
        />

        {/* ----- Avanzado ----- */}
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex w-full items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground"
        >
          {showAdvanced ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          Avanzado
        </button>
        {showAdvanced && (
          <div className="space-y-3 rounded-md border bg-muted/20 p-3">
            <p className="text-xs text-muted-foreground">
              Solo si Smart Deploy no es suficiente. Estos botones fuerzan
              acciones aunque no haya cambios.
            </p>
            <AdvancedAction
              label="Rebuild forzado api + web"
              description="Reconstruye imágenes desde cero (sin git)"
              icon={RefreshCw}
              confirmTitle="¿Rebuildear api y web?"
              confirmBody="Reconstruye desde cero con el código actual del server. Útil tras tocar .env o si algo se quedó raro."
              confirmActionLabel="Rebuild"
              onAction={async () => {
                await rebuild.mutateAsync({ services: ["api", "web"] });
                startLivePoll();
              }}
              disabled={!reachable || busy}
              loading={rebuild.isPending}
            />
            <div>
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Restart sin rebuild (~5s)
              </p>
              <div className="grid grid-cols-3 gap-2">
                {(["api", "web", "caddy"] as DeployServiceName[]).map((svc) => (
                  <RestartButton
                    key={svc}
                    service={svc}
                    disabled={!reachable || busy}
                    onDone={startLivePoll}
                    pending={
                      restart.isPending && restart.variables?.service === svc
                    }
                    run={restart.mutateAsync}
                  />
                ))}
              </div>
            </div>

            {/* Claude Remoto — backend Agent SDK fuera de Docker (:8765).
                El chat web "A la app" tiene 1 solo slot remoto; si queda
                colgado, estos botones lo liberan/reinician sin SSH. */}
            <div>
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Claude Remoto (chat &quot;A la app&quot;)
              </p>
              <div className="space-y-2">
                <AdvancedAction
                  label="Liberar remoto colgado"
                  description="Suelta el slot remoto ocupado sin reiniciar — prueba esto primero"
                  icon={Smartphone}
                  confirmTitle="¿Liberar el control remoto?"
                  confirmBody="Hace stop de las sesiones remotas activas del chat de Claude. Desbloquea 'A la app' si el slot quedó pillado. No reinicia nada."
                  confirmActionLabel="Liberar"
                  onAction={() => sdkFree.mutateAsync()}
                  disabled={!reachable || sdkBusy}
                  loading={sdkFree.isPending}
                />
                <AdvancedAction
                  label="Reiniciar backend remoto"
                  description="Kill + relaunch del Agent SDK (:8765). Úsalo si liberar no basta"
                  icon={RotateCw}
                  confirmTitle="¿Reiniciar el backend de Remote Control?"
                  confirmBody="Reinicia el proceso host del chat de Claude (Agent SDK en :8765). Corta cualquier sesión remota activa unos segundos y libera el slot colgado."
                  confirmActionLabel="Reiniciar"
                  onAction={() => sdkRestart.mutateAsync()}
                  disabled={!reachable || sdkBusy}
                  loading={sdkRestart.isPending}
                />
              </div>
            </div>
          </div>
        )}

        {(sdkFree.data || sdkRestart.data) && (
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 font-mono text-[11px] text-emerald-700 dark:text-emerald-300">
            {(sdkRestart.data ?? sdkFree.data)?.stdout || "✅ OK"}
          </pre>
        )}

        {(runDeploy.error ||
          rebuild.error ||
          restart.error ||
          sdkFree.error ||
          sdkRestart.error) && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
            {String(
              runDeploy.error?.message ??
                rebuild.error?.message ??
                restart.error?.message ??
                sdkFree.error?.message ??
                sdkRestart.error?.message,
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Smart Deploy — el botón principal con auto-detección
// ---------------------------------------------------------------------------
function SmartDeployBlock({
  status,
  loading,
  inProgress,
  disabled,
  pending,
  onDeploy,
}: {
  status: DeployStatus | undefined;
  loading: boolean;
  inProgress: boolean;
  disabled: boolean;
  pending: boolean;
  onDeploy: () => Promise<void>;
}) {
  if (loading || !status) {
    return (
      <div className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Comprobando estado del repo…
      </div>
    );
  }

  const behind = status.commits_behind ?? 0;
  const upToDate = behind === 0;
  const rebuild = status.would_rebuild ?? [];

  // Tono visual del block: verde si up-to-date, ámbar si hay cambios, azul
  // si deploy en curso.
  let blockTone =
    "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300";
  let title = "Estás al día";
  let subtitle = `HEAD: ${status.current_sha_short || "?"} — no hay nada que aplicar.`;
  let actionLabel = "Forzar deploy";
  let actionTone: "primary" | "muted" = "muted";
  let buttonDisabled = disabled;

  if (inProgress) {
    blockTone =
      "border-brand-cyan/40 bg-brand-cyan/5 text-brand-cyan";
    title = "Deploy en curso";
    subtitle = "Esperando a que termine el rebuild — el log se actualiza solo.";
    actionLabel = "Esperando…";
    actionTone = "muted";
    buttonDisabled = true;
  } else if (!upToDate) {
    blockTone =
      "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300";
    title = `${behind} commit${behind === 1 ? "" : "s"} pendiente${behind === 1 ? "" : "s"}`;
    subtitle =
      rebuild.length > 0
        ? `Se rebuildearán: ${rebuild.join(" + ")}`
        : "Solo cambios menores — no requiere rebuild de containers.";
    actionLabel = `Aplicar ${behind} commit${behind === 1 ? "" : "s"}`;
    actionTone = "primary";
  }

  const confirmBody = upToDate
    ? "No hay commits nuevos en origin/main. El deploy correrá igual, pero no rebuildeará nada salvo que fuerces."
    : `Aplicará ${behind} commit(s) y rebuildeará: ${rebuild.length ? rebuild.join(" + ") : "(nada — solo docs/config)"}.\n\nCommits:\n${(status.commits_preview ?? [])
        .slice(0, 5)
        .map((c) => `• ${c.sha} ${c.subject}`)
        .join("\n")}`;

  return (
    <div className={cn("rounded-lg border p-4", blockTone)}>
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-current/10">
          {inProgress ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : upToDate ? (
            <CheckCircle2 className="h-5 w-5" />
          ) : (
            <GitCommitHorizontal className="h-5 w-5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs opacity-80">{subtitle}</p>
          {!upToDate && status.commits_preview.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-[11px] opacity-90">
              {status.commits_preview.slice(0, 4).map((c) => (
                <li key={c.sha} className="truncate">
                  <code className="font-mono">{c.sha}</code> · {c.subject}
                </li>
              ))}
              {status.commits_preview.length > 4 && (
                <li className="opacity-60">
                  …y {behind - 4} más
                </li>
              )}
            </ul>
          )}
        </div>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              size="lg"
              className={cn(
                "shrink-0 gap-2",
                actionTone === "primary"
                  ? "bg-gradient-to-r from-brand-cyan to-brand-violet text-white hover:opacity-90"
                  : "",
              )}
              variant={actionTone === "primary" ? "default" : "outline"}
              disabled={buttonDisabled}
            >
              {pending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {actionLabel}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {upToDate ? "¿Forzar deploy?" : "¿Aplicar cambios?"}
              </AlertDialogTitle>
              <AlertDialogDescription>
                <span className="whitespace-pre-wrap text-xs">
                  {confirmBody}
                </span>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={() => void onDeploy()}>
                {upToDate ? "Forzar deploy" : "Aplicar"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {/* Last deploy meta */}
      {status.last_deploy && !inProgress && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-current/15 pt-2 text-[11px] opacity-75">
          <span>Último:</span>
          <Badge variant="outline" className="border-current/30 text-[10px]">
            {status.last_deploy.state ?? "?"}
          </Badge>
          {status.last_deploy.current_sha && (
            <code className="font-mono">
              {status.last_deploy.current_sha.slice(0, 7)}
            </code>
          )}
          {status.last_deploy.error && (
            <span className="text-rose-500">
              · err: {status.last_deploy.error}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponentes auxiliares
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
      <Badge
        variant="outline"
        className="gap-1 border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
      >
        <CheckCircle2 className="h-3 w-3" />
        listener OK
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className="gap-1 border-destructive/40 text-destructive"
    >
      <AlertCircle className="h-3 w-3" />
      listener caído
    </Badge>
  );
}

function AdvancedAction({
  label,
  description,
  icon: Icon,
  onAction,
  disabled,
  loading,
  confirmTitle,
  confirmBody,
  confirmActionLabel,
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
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          className="h-auto w-full justify-start gap-3 p-3 text-left"
          disabled={disabled}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
          ) : (
            <Icon className="h-4 w-4 shrink-0" />
          )}
          <span className="flex flex-col">
            <span className="text-sm font-medium leading-tight">{label}</span>
            <span className="text-[11px] leading-tight text-muted-foreground">
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
            Reinicia el container sin rebuild (rápido, ~5s).
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
  if (!sys) return null;
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
          <Stat icon={Cpu} label="uptime" value={formatUptime(sys.uptime_seconds)} />
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
