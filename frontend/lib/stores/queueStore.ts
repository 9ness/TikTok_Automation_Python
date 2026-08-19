"use client";

import { create } from "zustand";

import type { ActiveJob, ActivosDeOtro, JobStatus } from "@/lib/types/queue";

const FINAL_STATUSES: JobStatus[] = ["completed", "failed", "cancelled"];
const RECENT_LIMIT = 10;

export type ConnectionState = "connecting" | "connected" | "disconnected";

export interface QueueState {
  // Jobs activos (pending + running) indexados por id
  active: Record<string, ActiveJob>;
  // Últimos finalizados (más recientes primero)
  recent: ActiveJob[];
  // Estado del WebSocket
  connection: ConnectionState;
  /** Multiusuario: de quién es la cola que se ve y qué tienen los demás. */
  viendo: string;
  esAdmin: boolean;
  otros: Record<string, ActivosDeOtro>;
  /** Cola de quién quiere ver el admin ("" = la suya, "todos" = mezcladas). */
  verDe: string;
  lastError: string | null;

  // Actions
  setSnapshot: (jobs: ActiveJob[]) => void;
  upsertJobs: (jobs: ActiveJob[]) => void;
  applyProgress: (jobs: ActiveJob[]) => void;
  removeJobs: (ids: string[]) => void;
  /** Vacía la lista de "Recientes" (solo estado local, no afecta al backend). */
  clearRecent: () => void;
  /** Quita un job individual del listado de "Recientes". */
  dismissRecent: (id: string) => void;
  setConnection: (state: ConnectionState, error?: string | null) => void;
  setOtros: (otros: Record<string, ActivosDeOtro>) => void;
  setViendo: (viendo: string, esAdmin: boolean) => void;
  setVerDe: (verDe: string) => void;
  reset: () => void;
}

function isActive(status: JobStatus): boolean {
  return !FINAL_STATUSES.includes(status);
}

export const useQueueStore = create<QueueState>((set) => ({
  active: {},
  recent: [],
  connection: "disconnected",
  viendo: "",
  esAdmin: false,
  otros: {},
  verDe: "",
  lastError: null,

  setSnapshot: (jobs) =>
    set(() => {
      const active: Record<string, ActiveJob> = {};
      const recent: ActiveJob[] = [];
      for (const job of jobs) {
        if (isActive(job.status)) active[job.job_id] = job;
        else recent.push(job);
      }
      recent.sort((a, b) => (b.finished_at ?? 0) - (a.finished_at ?? 0));
      return { active, recent: recent.slice(0, RECENT_LIMIT) };
    }),

  upsertJobs: (jobs) =>
    set((state) => {
      const active = { ...state.active };
      let recent = [...state.recent];
      for (const job of jobs) {
        if (isActive(job.status)) {
          active[job.job_id] = job;
        } else {
          // Pasó a estado final: quitar de active, añadir a recent
          delete active[job.job_id];
          recent = [job, ...recent.filter((j) => j.job_id !== job.job_id)];
        }
      }
      recent.sort((a, b) => (b.finished_at ?? 0) - (a.finished_at ?? 0));
      return { active, recent: recent.slice(0, RECENT_LIMIT) };
    }),

  applyProgress: (jobs) =>
    set((state) => {
      const active = { ...state.active };
      for (const job of jobs) {
        if (active[job.job_id]) {
          active[job.job_id] = job;
        } else if (isActive(job.status)) {
          active[job.job_id] = job;
        }
      }
      return { active };
    }),

  removeJobs: (ids) =>
    set((state) => {
      const active = { ...state.active };
      for (const id of ids) delete active[id];
      const recent = state.recent.filter((j) => !ids.includes(j.job_id));
      return { active, recent };
    }),

  clearRecent: () => set(() => ({ recent: [] })),

  dismissRecent: (id) =>
    set((state) => ({ recent: state.recent.filter((j) => j.job_id !== id) })),

  setOtros: (otros: Record<string, ActivosDeOtro>) => set(() => ({ otros })),
  setViendo: (viendo: string, esAdmin: boolean) =>
    set(() => ({ viendo, esAdmin })),
  // Al cambiar de cola se VACÍA lo que hay. El socket se reconecta con el
  // filtro nuevo y hasta que llegue su snapshot lo que quedaría en pantalla es
  // la lista de la persona anterior — y como el cambio tarda un instante, se
  // lee como "he pulsado Ana y me sale la mía".
  setVerDe: (verDe: string) =>
    set(() => ({ verDe, active: {}, recent: [], connection: "connecting" })),
  setConnection: (connection, error = null) =>
    set(() => ({ connection, lastError: error })),

  reset: () =>
    set(() => ({
      active: {}, recent: [], connection: "disconnected", lastError: null,
      viendo: "", esAdmin: false, otros: {},
    })),
}));

// Selectors
//
// Importante: un selector NO debe devolver array/objeto nuevo en cada llamada —
// Zustand usa equality referencial y eso causa loop de re-render. Para listas
// ordenadas, leer `state.active` (mismo ref hasta que cambia) y sortear con
// `useMemo` en el componente.

export const selectActiveCount = (state: QueueState): number =>
  Object.keys(state.active).length;
