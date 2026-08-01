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

export function useDiagnosticsSummary() {
  return useQuery<DiagnosticsSummary>({
    queryKey: ["diagnostics", "summary"],
    queryFn: () => api.get<DiagnosticsSummary>(`/api/v1/diagnostics/summary`),
    refetchInterval: 30_000, // refresh cada 30s
    staleTime: 10_000,
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
