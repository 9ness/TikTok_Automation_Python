/**
 * Hooks para sincronizar shortcuts (cuenta + producto pinneados) en
 * Redis. Antes vivían solo en localStorage del navegador — ahora se
 * sincronizan entre PC y móvil del mismo operador.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api } from "@/lib/api";

const ROOT = "/api/v1/tiktok-shop/shortcuts";

export interface Shortcut {
  id: string;
  operator: string;
  user_id: string;
  product_id: string;
  created_at: string;
}

export interface ShortcutListResponse {
  items: Shortcut[];
  total: number;
}

export interface CreateShortcutInput {
  user_id: string;
  product_id: string;
}

export const shortcutKeys = {
  all: ["shortcuts"] as const,
  list: () => [...shortcutKeys.all, "list"] as const,
};

export function useShortcuts(
  options?: Omit<UseQueryOptions<ShortcutListResponse>, "queryKey" | "queryFn">,
) {
  return useQuery<ShortcutListResponse>({
    queryKey: shortcutKeys.list(),
    queryFn: () => api.get<ShortcutListResponse>(ROOT),
    staleTime: 30_000,
    ...options,
  });
}

export function useCreateShortcut() {
  const qc = useQueryClient();
  return useMutation<Shortcut, Error, CreateShortcutInput>({
    mutationFn: (input) => api.post<Shortcut>(ROOT, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: shortcutKeys.list() });
    },
  });
}

export function useDeleteShortcut() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (shortcutId) => {
      await api.del<void>(`${ROOT}/${shortcutId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: shortcutKeys.list() });
    },
  });
}

/**
 * Migración one-shot: lee shortcuts del viejo localStorage y los sube
 * al server. Después borra el key local. Llamar una vez al cargar el
 * componente que use shortcuts.
 *
 * Se identifica con un flag separado para no re-importar repetidamente
 * (ej. si el server-side ya tiene la lista correcta).
 */
const LEGACY_LS_KEY = "tiktok_shop_generate.shortcuts";
const MIGRATION_FLAG = "tiktok_shop_shortcuts_migrated_v1";

export async function migrateLocalShortcutsIfNeeded(): Promise<number> {
  if (typeof window === "undefined") return 0;
  if (window.localStorage.getItem(MIGRATION_FLAG) === "done") return 0;
  let migrated = 0;
  try {
    const raw = window.localStorage.getItem(LEGACY_LS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        for (const s of parsed) {
          if (
            s &&
            typeof s.userId === "string" &&
            typeof s.productId === "string"
          ) {
            try {
              await api.post(ROOT, {
                user_id: s.userId,
                product_id: s.productId,
              });
              migrated++;
            } catch {
              /* falla silenciosa — server podría rechazar duplicados, no es
                 grave; el dedupe del backend ya garantiza idempotencia */
            }
          }
        }
      }
    }
  } catch {
    /* silencia */
  }
  // Marcar como migrado tanto si había datos como si no, para no
  // intentar de nuevo. Mantenemos el LS key viejo por compat 1 semana,
  // luego un futuro commit puede borrarlo.
  try {
    window.localStorage.setItem(MIGRATION_FLAG, "done");
  } catch {
    /* silencia */
  }
  return migrated;
}
