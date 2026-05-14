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
  ToolDescriptor,
  UserFolderCountsResponse,
  UserFoldersResponse,
} from "@/lib/types/editor-auto";

const USERS_ROOT = "/api/v1/editor-auto/users";
const TOOLS_ROOT = "/api/v1/editor-auto/tools";
const ENQUEUE_ROOT = "/api/v1/editor-auto/enqueue";
const STICKERS_ROOT = "/api/v1/editor-auto/stickers";
const EDITOR_ROOT = "/api/v1/editor-auto";

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
};

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

export function useDeleteEditorUser() {
  const qc = useQueryClient();
  return useMutation<void, Error, { id: string; hard?: boolean }>({
    mutationFn: ({ id, hard }) =>
      api.del<void>(`${USERS_ROOT}/${id}${hard ? "?hard=true" : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: editorAutoKeys.users() }),
  });
}

// ---------------------------------------------------------------------------
// Enqueue — sube vídeo + user_id
// ---------------------------------------------------------------------------
export function useEnqueueEditorAuto() {
  return useMutation<
    EditorAutoEnqueueResponse,
    Error,
    { userId: string; file: File; script?: string }
  >({
    mutationFn: ({ userId, file, script }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("user_id", userId);
      if (script && script.trim()) fd.append("script", script.trim());
      return api.post<EditorAutoEnqueueResponse>(ENQUEUE_ROOT, fd);
    },
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
        qc.invalidateQueries({ queryKey: editorAutoKeys.userFolders(userId) });
        qc.invalidateQueries({
          queryKey: editorAutoKeys.userFolderCounts(userId),
        });
        qc.invalidateQueries({
          queryKey: editorAutoKeys.globalFolderCounts(),
        });
      },
    },
  );
}
