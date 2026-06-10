"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  EditorAutoEnqueueResponse,
  EditorUser,
  EditorUserCreateInput,
  EditorUserUpdateInput,
  EnqueueFromEntradaInput,
  EnqueueFromEntradaResponse,
  FolderName,
  GlobalFolderCountsResponse,
  MoveFileInput,
  MoveFileResponse,
  OutputEditProject,
  Plan,
  PlanCreateInput,
  PlanUpdateInput,
  ReferralCode,
  Subscription,
  SubscriptionAssignInput,
  ToolDescriptor,
  UserFolderCountsResponse,
  UserFoldersResponse,
  WebAccount,
  WebAccountRole,
} from "@/lib/types/editor-auto";

const USERS_ROOT = "/api/v1/editor-auto/users";
const TOOLS_ROOT = "/api/v1/editor-auto/tools";
const ENQUEUE_ROOT = "/api/v1/editor-auto/enqueue";
const STICKERS_ROOT = "/api/v1/editor-auto/stickers";
const EDITOR_ROOT = "/api/v1/editor-auto";
const PLANS_ROOT = "/api/v1/editor-auto/plans";
const REFERRALS_ROOT = "/api/v1/editor-auto/referrals";

export const editorAutoKeys = {
  all: ["editor-auto"] as const,
  users: () => [...editorAutoKeys.all, "users"] as const,
  user: (id: string) => [...editorAutoKeys.all, "user", id] as const,
  tools: () => [...editorAutoKeys.all, "tools"] as const,
  arrows: () => [...editorAutoKeys.all, "stickers", "arrows"] as const,
  userFolders: (id: string) => [...editorAutoKeys.all, "user", id, "folders"] as const,
  userFolderCounts: (id: string) =>
    [...editorAutoKeys.all, "user", id, "folder-counts"] as const,
  globalFolderCounts: () =>
    [...editorAutoKeys.all, "folder-counts", "global"] as const,
  plans: () => [...editorAutoKeys.all, "plans"] as const,
  plan: (id: string) => [...editorAutoKeys.all, "plan", id] as const,
  referrals: () => [...editorAutoKeys.all, "referrals"] as const,
  userSubscription: (id: string) =>
    [...editorAutoKeys.all, "user", id, "subscription"] as const,
};

// ---------------------------------------------------------------------------
// Plans CRUD
// ---------------------------------------------------------------------------
export function useEditorPlans(only_active = false) {
  return useQuery<Plan[]>({
    queryKey: [...editorAutoKeys.plans(), { only_active }],
    queryFn: () =>
      api.get<Plan[]>(`${PLANS_ROOT}${only_active ? "?only_active=true" : ""}`),
  });
}

export function useEditorPlan(id: string | null | undefined) {
  return useQuery<Plan>({
    queryKey: editorAutoKeys.plan(id ?? ""),
    queryFn: () => api.get<Plan>(`${PLANS_ROOT}/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateEditorPlan() {
  const qc = useQueryClient();
  return useMutation<Plan, Error, PlanCreateInput>({
    mutationFn: (input) => api.post<Plan>(PLANS_ROOT, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: editorAutoKeys.plans() }),
  });
}

export function useUpdateEditorPlan(id: string) {
  const qc = useQueryClient();
  return useMutation<Plan, Error, PlanUpdateInput>({
    mutationFn: (input) =>
      fetch(`${api.baseUrl}${PLANS_ROOT}/${id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(process.env.NEXT_PUBLIC_API_KEY
            ? { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY }
            : {}),
        },
        credentials: "include",
        body: JSON.stringify(input),
      }).then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json() as Promise<Plan>;
      }),
    onSuccess: (data) => {
      qc.setQueryData(editorAutoKeys.plan(id), data);
      qc.invalidateQueries({ queryKey: editorAutoKeys.plans() });
    },
  });
}

export function useDeleteEditorPlan() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api.del<void>(`${PLANS_ROOT}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: editorAutoKeys.plans() }),
  });
}

// ---------------------------------------------------------------------------
// User subscription
// ---------------------------------------------------------------------------
export function useAssignSubscription(userId: string) {
  const qc = useQueryClient();
  return useMutation<Subscription, Error, SubscriptionAssignInput>({
    mutationFn: (input) =>
      fetch(`${api.baseUrl}${USERS_ROOT}/${userId}/subscription`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(process.env.NEXT_PUBLIC_API_KEY
            ? { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY }
            : {}),
        },
        credentials: "include",
        body: JSON.stringify(input),
      }).then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json() as Promise<Subscription>;
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorAutoKeys.user(userId) });
      qc.invalidateQueries({ queryKey: editorAutoKeys.users() });
      qc.invalidateQueries({ queryKey: editorAutoKeys.plans() });
    },
  });
}

export function useClearSubscription(userId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () =>
      api.del<void>(`${USERS_ROOT}/${userId}/subscription`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorAutoKeys.user(userId) });
      qc.invalidateQueries({ queryKey: editorAutoKeys.users() });
    },
  });
}

// ---------------------------------------------------------------------------
// Referrals
// ---------------------------------------------------------------------------
export function useEditorReferrals() {
  return useQuery<ReferralCode[]>({
    queryKey: editorAutoKeys.referrals(),
    queryFn: () => api.get<ReferralCode[]>(REFERRALS_ROOT),
  });
}

export function useGenerateReferralForUser() {
  const qc = useQueryClient();
  return useMutation<ReferralCode, Error, string>({
    mutationFn: (userId) =>
      api.post<ReferralCode>(`${REFERRALS_ROOT}/users/${userId}/generate`, {}),
    onSuccess: (_data, userId) => {
      qc.invalidateQueries({ queryKey: editorAutoKeys.user(userId) });
      qc.invalidateQueries({ queryKey: editorAutoKeys.users() });
      qc.invalidateQueries({ queryKey: editorAutoKeys.referrals() });
    },
  });
}

// ---------------------------------------------------------------------------
// Stickers · flechas
// ---------------------------------------------------------------------------
export interface ArrowSticker {
  filename: string;
  size_bytes: number;
  ext: string;
}
export interface ArrowStickersResponse {
  folder: string;
  files: ArrowSticker[];
}

export function useArrowStickers() {
  return useQuery<ArrowStickersResponse>({
    queryKey: editorAutoKeys.arrows(),
    queryFn: () => api.get<ArrowStickersResponse>(`${STICKERS_ROOT}/arrows`),
    staleTime: 60 * 1000,
  });
}

/** URL absoluta para servir el sticker en el preview del frontend.
 *
 * - Si la extensión es MOV (ProRes con alpha — los navegadores no la
 *   decodifican) pide al backend que lo transcodifique a APNG (`?as=apng`),
 *   cacheado en disco. APNG tiene alpha nativo y se renderiza con `<img>`
 *   en todos los browsers modernos.
 * - WebM/GIF/PNG/APNG se sirven tal cual (el navegador los reproduce).
 *
 * Incluye `?api_key=` si está configurada (las etiquetas `<img src=>` no
 * admiten headers custom — mismo patrón que las fuentes).
 *
 * Devuelve `{ url, asImage }`: `asImage=true` cuando el preview debe ir
 * en `<img>` (APNG/GIF/PNG transcoded o nativos); `false` para WebM nativo
 * que va en `<video>`.
 */
export function arrowStickerPreview(filename: string): {
  url: string;
  asImage: boolean;
} {
  const lower = filename.toLowerCase();
  const isMov = lower.endsWith(".mov");
  const isWebm = lower.endsWith(".webm");
  const params = new URLSearchParams();
  if (isMov) params.set("as", "apng");
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  if (apiKey) params.set("api_key", apiKey);
  const qs = params.toString();
  const path = `${STICKERS_ROOT}/arrows/${encodeURIComponent(filename)}`;
  return {
    url: `${api.baseUrl}${path}${qs ? `?${qs}` : ""}`,
    // WebM nativo va en <video>; cualquier otro (incl. MOV→APNG, GIF, PNG,
    // APNG nativo) va en <img>.
    asImage: !isWebm,
  };
}

// ---------------------------------------------------------------------------
// Tools registry (read-only, casi inmutable)
// ---------------------------------------------------------------------------
export function useEditorAutoTools() {
  return useQuery<ToolDescriptor[]>({
    queryKey: editorAutoKeys.tools(),
    queryFn: () => api.get<ToolDescriptor[]>(TOOLS_ROOT),
    staleTime: 5 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Users CRUD
// ---------------------------------------------------------------------------
export function useEditorUsers(include_deleted = false) {
  return useQuery<EditorUser[]>({
    queryKey: [...editorAutoKeys.users(), { include_deleted }],
    queryFn: () =>
      api.get<EditorUser[]>(
        `${USERS_ROOT}${include_deleted ? "?include_deleted=true" : ""}`,
      ),
  });
}

export function useEditorUser(id: string | null | undefined) {
  return useQuery<EditorUser>({
    queryKey: editorAutoKeys.user(id ?? ""),
    queryFn: () => api.get<EditorUser>(`${USERS_ROOT}/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateEditorUser() {
  const qc = useQueryClient();
  return useMutation<EditorUser, Error, EditorUserCreateInput>({
    mutationFn: (input) => api.post<EditorUser>(USERS_ROOT, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: editorAutoKeys.users() }),
  });
}

export function useUpdateEditorUser(id: string) {
  const qc = useQueryClient();
  return useMutation<EditorUser, Error, EditorUserUpdateInput>({
    mutationFn: (input) =>
      // FastAPI patch via fetch directo (api helper no expone PATCH; usamos
      // POST con override clásico no — mejor: extender el helper sería más
      // limpio, pero por ahora usamos fetch crudo aquí).
      fetch(`${api.baseUrl}${USERS_ROOT}/${id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(process.env.NEXT_PUBLIC_API_KEY
            ? { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY }
            : {}),
        },
        credentials: "include",
        body: JSON.stringify(input),
      }).then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json() as Promise<EditorUser>;
      }),
    onSuccess: (data) => {
      qc.setQueryData(editorAutoKeys.user(id), data);
      qc.invalidateQueries({ queryKey: editorAutoKeys.users() });
    },
  });
}

export interface ReleaseDayResult {
  shared: string[];
  share_errors: string[];
  emails: string[];
  email: { ok: boolean; sent: number; error: string | null } | null;
  warning?: string;
}

/** "Marcar día listo": comparte la carpeta salida + email "vídeos listos". */
export function useReleaseDay(id: string) {
  return useMutation<ReleaseDayResult, Error, { count?: number } | void>({
    mutationFn: (input) =>
      api.post<ReleaseDayResult>(`${USERS_ROOT}/${id}/release-day`, input ?? {}),
  });
}

export function useDeleteEditorUser() {
  const qc = useQueryClient();
  return useMutation<void, Error, { id: string; hard?: boolean }>({
    mutationFn: ({ id, hard }) =>
      api.del<void>(`${USERS_ROOT}/${id}${hard ? "?hard=true" : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: editorAutoKeys.users() }),
  });
}

// ---------------------------------------------------------------------------
// Cuentas web (nebulabs-media) — gestión por email desde el panel
// ---------------------------------------------------------------------------
const WEB_ACCOUNTS_ROOT = `${USERS_ROOT}/web-accounts`;

function patchJSON<T>(url: string, body: unknown): Promise<T> {
  return fetch(`${api.baseUrl}${url}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(process.env.NEXT_PUBLIC_API_KEY
        ? { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY }
        : {}),
    },
    credentials: "include",
    body: JSON.stringify(body),
  }).then(async (r) => {
    if (!r.ok) throw new Error(await r.text());
    return r.json() as Promise<T>;
  });
}

export interface EditorSettings {
  send_cutoff_hour: number;
  send_cutoff_minute: number;
  manual_approval: boolean;
}

const WEB_ADMIN_ROOT = "/api/v1/editor-auto/web/admin";

/** Ajustes globales del Editor Auto (hora:minuto de cierre de envíos…). */
export function useEditorSettings() {
  return useQuery<EditorSettings>({
    queryKey: [...editorAutoKeys.all, "settings"] as const,
    queryFn: () => api.get<EditorSettings>(`${USERS_ROOT}/settings`),
  });
}

/** Cambia la hora:minuto de cierre diaria de envíos. */
export function useUpdateCutoff() {
  const qc = useQueryClient();
  return useMutation<EditorSettings, Error, { hour: number; minute: number }>({
    mutationFn: ({ hour, minute }) =>
      patchJSON<EditorSettings>(`${USERS_ROOT}/settings/cutoff`, {
        send_cutoff_hour: hour,
        send_cutoff_minute: minute,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: [...editorAutoKeys.all, "settings"] }),
  });
}

/** Activa/desactiva la aprobación manual antes de mostrar vídeos al cliente. */
export function useToggleApproval() {
  const qc = useQueryClient();
  return useMutation<EditorSettings, Error, boolean>({
    mutationFn: (enabled) =>
      patchJSON<EditorSettings>(`${USERS_ROOT}/settings/approval`, {
        manual_approval: enabled,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: [...editorAutoKeys.all, "settings"] }),
  });
}

export interface PendingApproval {
  user_id: string;
  user_name: string;
  day: string;
  source: string | null;
  filename: string;
  score: number | null;
}

/** Vídeos terminados (≥90) pendientes de aprobación del admin. */
export function usePendingApprovals() {
  return useQuery<{ pending: PendingApproval[]; count: number }>({
    queryKey: [...editorAutoKeys.all, "pending-approvals"] as const,
    queryFn: () => api.get(`${WEB_ADMIN_ROOT}/pending`),
    refetchInterval: 20_000,
  });
}

export interface PipelineItem {
  day: string;
  source: string | null;
  filename: string | null;
  score: number | null;
  state: string;
  label: string;
}

/** Pipeline de edición de un usuario WEB: en proceso vs entregados. El
 *  estado real vive en la cola (jobs), no en carpetas. */
export function useWebUserPipeline(userId: string | null | undefined, isWeb: boolean) {
  return useQuery<{
    in_process: PipelineItem[];
    ready: PipelineItem[];
    n_in_process: number;
    n_ready: number;
    gate: boolean;
  }>({
    queryKey: [...editorAutoKeys.all, "web-pipeline", userId] as const,
    queryFn: () => api.get(`${WEB_ADMIN_ROOT}/user-pipeline?user_id=${userId}`),
    enabled: Boolean(userId) && isWeb,
    refetchInterval: 15_000,
  });
}

/** Aprueba (o revoca) un vídeo para que el cliente lo vea. */
export function useApproveVideo() {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean; approved: boolean },
    Error,
    { user_id: string; day: string; filename: string; approve?: boolean }
  >({
    mutationFn: (b) =>
      api.post(`${WEB_ADMIN_ROOT}/approve`, { approve: true, ...b }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: [...editorAutoKeys.all, "pending-approvals"] }),
  });
}

/** Re-edita un vídeo (nuevo intento) si el resultado no convence. */
export function useRequeueVideo() {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean; job_id: string },
    Error,
    { user_id: string; day: string; source: string; filename?: string }
  >({
    mutationFn: (b) => api.post(`${WEB_ADMIN_ROOT}/requeue`, b),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: [...editorAutoKeys.all, "pending-approvals"] }),
  });
}

/** URL del stream de un vídeo de salida para el reproductor admin (auth por query). */
export function adminStreamUrl(userId: string, day: string, file: string): string {
  const key = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const qs = new URLSearchParams({ user_id: userId, day, file, key }).toString();
  return `${api.baseUrl}${WEB_ADMIN_ROOT}/stream?${qs}`;
}

/** Todas las cuentas registradas en la web (para el selector de vinculación). */
export function useWebAccounts(enabled = true) {
  return useQuery<WebAccount[]>({
    queryKey: [...editorAutoKeys.all, "web-accounts"] as const,
    queryFn: () => api.get<WebAccount[]>(`${WEB_ACCOUNTS_ROOT}/all`),
    enabled,
  });
}

/** Crea (y vincula) un EditorUser a partir de una cuenta web por email. */
export function useProvisionFromWeb() {
  const qc = useQueryClient();
  return useMutation<EditorUser, Error, { email: string }>({
    mutationFn: ({ email }) =>
      api.post<EditorUser>(`${WEB_ACCOUNTS_ROOT}/provision`, { email }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorAutoKeys.users() });
      qc.invalidateQueries({ queryKey: [...editorAutoKeys.all, "web-accounts"] });
    },
  });
}

/** Cambia rol/plan/ban de una cuenta web. Invalida la lista de users para
 *  refrescar el `web_account` embebido en la tarjeta. */
export function useUpdateWebAccount() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: editorAutoKeys.users() });
    qc.invalidateQueries({ queryKey: [...editorAutoKeys.all, "web-accounts"] });
  };
  return {
    setRole: useMutation<WebAccount, Error, { email: string; role: WebAccountRole }>({
      mutationFn: ({ email, role }) =>
        patchJSON<WebAccount>(`${WEB_ACCOUNTS_ROOT}/${encodeURIComponent(email)}/role`, { role }),
      onSuccess: invalidate,
    }),
    setPlan: useMutation<WebAccount, Error, { email: string; plan_id: string | null }>({
      mutationFn: ({ email, plan_id }) =>
        patchJSON<WebAccount>(`${WEB_ACCOUNTS_ROOT}/${encodeURIComponent(email)}/plan`, { plan_id }),
      onSuccess: invalidate,
    }),
    setBan: useMutation<WebAccount, Error, { email: string; banned: boolean }>({
      mutationFn: ({ email, banned }) =>
        patchJSON<WebAccount>(`${WEB_ACCOUNTS_ROOT}/${encodeURIComponent(email)}/ban`, { banned }),
      onSuccess: invalidate,
    }),
  };
}

// ---------------------------------------------------------------------------
// Enqueue — sube vídeo + user_id
// ---------------------------------------------------------------------------
export function useEnqueueEditorAuto() {
  return useMutation<
    EditorAutoEnqueueResponse,
    Error,
    { userId: string; file: File; script?: string; onProgress?: (pct: number) => void }
  >({
    // XHR (no fetch) para tener progreso REAL de subida — fetch no expone
    // `upload.onprogress`. Así el operador ve avanzar la barra y no parece
    // colgado en vídeos pesados.
    mutationFn: ({ userId, file, script, onProgress }) =>
      new Promise<EditorAutoEnqueueResponse>((resolve, reject) => {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("user_id", userId);
        if (script && script.trim()) fd.append("script", script.trim());
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${api.baseUrl}${ENQUEUE_ROOT}`);
        const key = process.env.NEXT_PUBLIC_API_KEY;
        if (key) xhr.setRequestHeader("X-API-Key", key);
        xhr.withCredentials = true;
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && onProgress) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText) as EditorAutoEnqueueResponse);
            } catch {
              reject(new Error("Respuesta inválida del servidor"));
            }
          } else {
            let msg = `Error ${xhr.status}`;
            try {
              const j = JSON.parse(xhr.responseText);
              const d = j.detail ?? j.message;
              msg = typeof d === "string" ? d : (d?.message ?? msg);
            } catch {
              /* keep default */
            }
            reject(new Error(msg));
          }
        };
        xhr.onerror = () => reject(new Error("Error de red durante la subida"));
        xhr.send(fd);
      }),
  });
}

// ---------------------------------------------------------------------------
// Carpetas del usuario — entrada / cola / recuperacion / salida
// ---------------------------------------------------------------------------
/** Lista completa de las 4 carpetas con metadatos por archivo. */
export function useUserFolders(userId: string | null | undefined) {
  return useQuery<UserFoldersResponse>({
    queryKey: editorAutoKeys.userFolders(userId ?? ""),
    queryFn: () =>
      api.get<UserFoldersResponse>(
        `${USERS_ROOT}/${encodeURIComponent(userId!)}/folders`,
      ),
    enabled: Boolean(userId),
    // refetchInterval lo decide cada componente con setRefetchInterval si quiere
  });
}

/** Solo los 4 conteos. Más barato — pensado para badge de lista. */
export function useUserFolderCounts(userId: string | null | undefined) {
  return useQuery<UserFolderCountsResponse>({
    queryKey: editorAutoKeys.userFolderCounts(userId ?? ""),
    queryFn: () =>
      api.get<UserFolderCountsResponse>(
        `${USERS_ROOT}/${encodeURIComponent(userId!)}/folders/counts`,
      ),
    enabled: Boolean(userId),
    refetchInterval: 30_000,
  });
}

/** Conteos agregados de TODOS los usuarios — badge global de la sidebar. */
export function useGlobalFolderCounts() {
  return useQuery<GlobalFolderCountsResponse>({
    queryKey: editorAutoKeys.globalFolderCounts(),
    queryFn: () =>
      api.get<GlobalFolderCountsResponse>(`${EDITOR_ROOT}/folders/counts`),
    refetchInterval: 30_000,
    retry: 1,
  });
}

/** URL absoluta para servir un MP4 al `<video>` del preview. Auth dual. */
export function userFilePreviewUrl(
  userId: string,
  folder: FolderName,
  filename: string,
): string {
  const params = new URLSearchParams({ folder, filename });
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  if (apiKey) params.set("api_key", apiKey);
  return `${api.baseUrl}${USERS_ROOT}/${encodeURIComponent(userId)}/folders/file/preview?${params.toString()}`;
}

export function useMoveUserFile(userId: string) {
  const qc = useQueryClient();
  return useMutation<MoveFileResponse, Error, MoveFileInput>({
    mutationFn: (input) =>
      api.post<MoveFileResponse>(
        `${USERS_ROOT}/${encodeURIComponent(userId)}/folders/move`,
        input,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorAutoKeys.userFolders(userId) });
      qc.invalidateQueries({ queryKey: editorAutoKeys.userFolderCounts(userId) });
      qc.invalidateQueries({ queryKey: editorAutoKeys.globalFolderCounts() });
    },
  });
}

export function useDeleteUserFile(userId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, { folder: FolderName; filename: string }>({
    mutationFn: ({ folder, filename }) => {
      const qs = new URLSearchParams({ folder, filename }).toString();
      return api.del<void>(
        `${USERS_ROOT}/${encodeURIComponent(userId)}/folders/file?${qs}`,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorAutoKeys.userFolders(userId) });
      qc.invalidateQueries({ queryKey: editorAutoKeys.userFolderCounts(userId) });
      qc.invalidateQueries({ queryKey: editorAutoKeys.globalFolderCounts() });
    },
  });
}

/** Encola un vídeo que ya está en `entrada/`. Backend mueve a `cola/`
 *  y crea el job — más eficiente que upload tradicional. */
export function useEnqueueFromEntrada(userId: string) {
  const qc = useQueryClient();
  return useMutation<EnqueueFromEntradaResponse, Error, EnqueueFromEntradaInput>(
    {
      mutationFn: (input) =>
        api.post<EnqueueFromEntradaResponse>(
          `${USERS_ROOT}/${encodeURIComponent(userId)}/folders/enqueue`,
          input,
        ),
      onSuccess: () => {
        // El move entrada→cola + creación del job corren en SEGUNDO PLANO
        // (vídeos pesados tardan). Refrescamos ya y otra vez con retraso
        // para que el archivo salga de entrada/ y aparezca el job en la cola
        // cuando el move termine, sin que el operador tenga que recargar.
        const refresh = () => {
          qc.invalidateQueries({ queryKey: editorAutoKeys.userFolders(userId) });
          qc.invalidateQueries({ queryKey: editorAutoKeys.userFolderCounts(userId) });
          qc.invalidateQueries({ queryKey: editorAutoKeys.globalFolderCounts() });
        };
        refresh();
        setTimeout(refresh, 8000);
        setTimeout(refresh, 30000);
      },
    },
  );
}

// ---------------------------------------------------------------------------
// Google Drive Sharing — fase 2 (Service Account)
// ---------------------------------------------------------------------------
import type {
  CreateShareInput,
  CreateShareResponse,
  SharingStatus,
  UserSharesResponse,
} from "@/lib/types/editor-auto";

const SHARING_STATUS_KEY = ["editor-auto", "sharing", "status"] as const;
const userSharesKey = (id: string) =>
  ["editor-auto", "user", id, "shares"] as const;

/** ¿Está configurado el SA en el server? La UI lo consulta para
 *  mostrar/ocultar la sección de sharing (si no, instrucciones de setup). */
export function useSharingStatus() {
  return useQuery<SharingStatus>({
    queryKey: SHARING_STATUS_KEY,
    queryFn: () => api.get<SharingStatus>(`${EDITOR_ROOT}/sharing/status`),
    staleTime: 5 * 60 * 1000,
  });
}

export function useUserShares(userId: string | null | undefined) {
  return useQuery<UserSharesResponse>({
    queryKey: userSharesKey(userId ?? ""),
    queryFn: () =>
      api.get<UserSharesResponse>(
        `${USERS_ROOT}/${encodeURIComponent(userId!)}/shares`,
      ),
    enabled: Boolean(userId),
  });
}

export function useCreateUserShare(userId: string) {
  const qc = useQueryClient();
  return useMutation<CreateShareResponse, Error, CreateShareInput>({
    mutationFn: (input) =>
      api.post<CreateShareResponse>(
        `${USERS_ROOT}/${encodeURIComponent(userId)}/shares`,
        input,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userSharesKey(userId) });
    },
  });
}

export function useRevokeUserShare(userId: string) {
  const qc = useQueryClient();
  return useMutation<
    void,
    Error,
    { permission_id: string; folder: FolderName }
  >({
    mutationFn: ({ permission_id, folder }) => {
      const qs = new URLSearchParams({ folder }).toString();
      return api.del<void>(
        `${USERS_ROOT}/${encodeURIComponent(
          userId,
        )}/shares/${encodeURIComponent(permission_id)}?${qs}`,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userSharesKey(userId) });
    },
  });
}

/** Elimina un email de la lista `known_share_emails` del usuario.
 *  No revoca permisos activos en Drive — solo lo quita de la agenda. */
export function useForgetKnownEmail(userId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, { email: string }>({
    mutationFn: ({ email }) =>
      api.del<void>(
        `${USERS_ROOT}/${encodeURIComponent(userId)}/known-emails/${encodeURIComponent(email)}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userSharesKey(userId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Editor de retoque manual — proyecto editable + re-render
// ---------------------------------------------------------------------------
export function useOutputEditProject(
  userId: string | null | undefined,
  filename: string | null | undefined,
) {
  return useQuery<OutputEditProject>({
    queryKey: [...editorAutoKeys.all, "editproject", userId ?? "", filename ?? ""],
    queryFn: () =>
      api.get<OutputEditProject>(
        `${USERS_ROOT}/${encodeURIComponent(userId!)}/output/editproject?filename=${encodeURIComponent(filename!)}`,
      ),
    enabled: Boolean(userId && filename),
    staleTime: 0,
    gcTime: 0,
  });
}

export function useManualRender(userId: string) {
  const qc = useQueryClient();
  return useMutation<
    { status: string; job_id: string; filename: string },
    Error,
    { filename: string; keep_intervals: [number, number][] }
  >({
    mutationFn: (input) =>
      api.post(
        `${USERS_ROOT}/${encodeURIComponent(userId)}/output/manual-render`,
        input,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorAutoKeys.userFolders(userId) });
    },
  });
}
