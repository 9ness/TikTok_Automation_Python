"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface ServicesStatus {
  "tiktok-factory": string;
  "tiktok-webhook": string;
  "gdrive-mount": string;
}

export interface GitInfo {
  sha: string | null;
  sha_short: string | null;
  message: string | null;
  date: string | null;
}

export interface DeployStatus {
  /** `deferred`: había jobs renderizando, así que el deploy NO se hizo. */
  state?: "running" | "success" | "failed" | "deferred";
  current_sha?: string;
  current_sha_full?: string;
  target_sha?: string;
  previous_sha?: string;
  started_at?: number;
  finished_at?: number;
  updated_at?: number;
  error?: string;
  note?: string;
}

export interface DiagnosticsSummary {
  version: string;
  services: ServicesStatus;
  git: GitInfo;
  deploy: DeployStatus;
  queue: {
    total: number;
    pending: number;
    running: number;
    completed: number;
    failed: number;
    cancelled: number;
  };
  disk: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    used_pct: number;
    error?: string;
  };
}

/** `sondeo`: refrescar cada 30 s. Solo con el panel de Diagnóstico abierto;
 *  la versión del pie de la sidebar sale en TODAS las pantallas y no necesita
 *  pedirlo dos veces por minuto mientras la app está abierta. */
export function useDiagnosticsSummary(sondeo = true) {
  return useQuery<DiagnosticsSummary>({
    queryKey: ["diagnostics", "summary"],
    queryFn: () => api.get<DiagnosticsSummary>(`/api/v1/diagnostics/summary`),
    refetchInterval: sondeo ? 30_000 : false,
    staleTime: sondeo ? 10_000 : 5 * 60_000,
  });
}

export interface DeployDetail {
  status: DeployStatus;
  log_tail: string;
}

export function useDeployDetail() {
  return useQuery<DeployDetail>({
    queryKey: ["diagnostics", "deploy"],
    queryFn: () => api.get<DeployDetail>(`/api/v1/diagnostics/deploy`),
    refetchInterval: 15_000,
    staleTime: 5_000,
  });
}

export interface AppLogs {
  source: "file" | "journalctl" | "none";
  log_tail: string;
}

export function useAppLogs() {
  return useQuery<AppLogs>({
    queryKey: ["diagnostics", "app-logs"],
    queryFn: () => api.get<AppLogs>(`/api/v1/diagnostics/app-logs`),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

/** Una sonda de `/api/health/completo` (Redis, Drive, disco). */
export interface Sonda {
  ok: boolean;
  ms?: number;
  error?: string;
  [extra: string]: unknown;
}

export interface TrabajoAtascado {
  id: string;
  modo: string;
  titulo: string;
  estado: "corriendo" | "pendiente";
  minutos: number;
  progreso: number;
  etiqueta: string;
  usuario: string | null;
  motivo: string;
}

export interface SaludCompleta {
  ok: boolean;
  fallos: string[];
  redis_fabrica: Sonda;
  redis_compartido: Sonda;
  drive: Sonda;
  disco_trabajo: Sonda;
  cola: {
    ok: boolean;
    pendientes: number;
    corriendo: number;
    workers_vivos?: number;
    atascados: TrabajoAtascado[];
  };
}

/** Lo que el panel de mando no ve: Redis, Drive montado y cola atascada.
 *  Sin polling: solo se pide al abrir Diagnóstico o al pulsar Refrescar. */
export function useSaludCompleta() {
  return useQuery<SaludCompleta>({
    queryKey: ["diagnostics", "salud"],
    queryFn: () => api.get<SaludCompleta>(`/api/health/completo`),
    staleTime: 20_000,
  });
}
