"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const ROOT = "/api/v1/deploy";

export const deployKeys = {
  all: ["deploy"] as const,
  health: () => [...deployKeys.all, "health"] as const,
  system: () => [...deployKeys.all, "system"] as const,
  containers: () => [...deployKeys.all, "containers"] as const,
  log: () => [...deployKeys.all, "log"] as const,
};

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------
export interface DeployHealth {
  reachable: boolean;
  code?: number;
  error?: string;
}

export interface DeploySystem {
  uptime_seconds: number | null;
  disk: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    used_pct: number | null;
  } | null;
  memory: {
    total_gb: number;
    available_gb: number;
    used_pct: number | null;
  } | null;
  load_avg: number[] | null;
}

export interface DockerContainer {
  Name?: string;
  Service?: string;
  Image?: string;
  Status?: string;
  State?: string;
  Health?: string;
}

export interface DeployContainersResponse {
  ok: boolean;
  containers: DockerContainer[];
  raw_error?: string | null;
}

export type DeployServiceName = "api" | "web" | "caddy";

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------
/** ¿El webhook_listener del host responde en :9000? */
export function useDeployHealth() {
  return useQuery<DeployHealth>({
    queryKey: deployKeys.health(),
    queryFn: () => api.get<DeployHealth>(`${ROOT}/health`),
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useDeploySystem(opts?: { enabled?: boolean }) {
  return useQuery<DeploySystem>({
    queryKey: deployKeys.system(),
    queryFn: () => api.get<DeploySystem>(`${ROOT}/system`),
    enabled: opts?.enabled ?? true,
    refetchInterval: 15_000,
  });
}

export function useDeployContainers(opts?: { enabled?: boolean }) {
  return useQuery<DeployContainersResponse>({
    queryKey: deployKeys.containers(),
    queryFn: () => api.get<DeployContainersResponse>(`${ROOT}/containers`),
    enabled: opts?.enabled ?? true,
    refetchInterval: 10_000,
  });
}

export function useDeployLog(opts?: { enabled?: boolean; lines?: number; live?: boolean }) {
  const n = opts?.lines ?? 200;
  return useQuery<{ log: string }>({
    queryKey: [...deployKeys.log(), n],
    queryFn: () => api.get<{ log: string }>(`${ROOT}/log?n=${n}`),
    enabled: opts?.enabled ?? true,
    // Si el deploy está en curso, polling más rápido para ver el progreso.
    refetchInterval: opts?.live ? 3_000 : 15_000,
  });
}

// ---------------------------------------------------------------------------
// Mutations — botones del panel
// ---------------------------------------------------------------------------
export function useDeployRun() {
  const qc = useQueryClient();
  return useMutation<{ status: string }, Error, void>({
    mutationFn: () => api.post(`${ROOT}/run`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: deployKeys.log() });
      qc.invalidateQueries({ queryKey: deployKeys.containers() });
    },
  });
}

export function useDeployRebuild() {
  const qc = useQueryClient();
  return useMutation<
    { status: string; services: string[] },
    Error,
    { services?: DeployServiceName[] } | void
  >({
    mutationFn: (input) =>
      api.post(`${ROOT}/rebuild`, input ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: deployKeys.log() });
      qc.invalidateQueries({ queryKey: deployKeys.containers() });
    },
  });
}

export function useDeployRestart() {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean; service: string; stdout?: string; stderr?: string },
    Error,
    { service: DeployServiceName }
  >({
    mutationFn: ({ service }) => api.post(`${ROOT}/restart`, { service }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: deployKeys.containers() });
      qc.invalidateQueries({ queryKey: deployKeys.log() });
    },
  });
}
