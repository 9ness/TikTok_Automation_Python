"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface UsuarioFicha {
  username: string;
  nombre: string;
  rol: "admin" | "pro";
  tiene_pin: boolean;
}

export interface MeResponse {
  username: string | null;
  nombre?: string | null;
  rol?: "admin" | "pro" | null;
  available_users: string[];
  /** Ficha de cada usuario: sirve para saber quién tiene que CREAR su PIN
   *  la primera vez y quién solo tiene que entrar. */
  usuarios?: UsuarioFicha[];
  /** Quién abrió la sesión DE VERDAD cuando el admin está viendo la app como
   *  otro usuario. `null` en el caso normal. */
  admin_real?: string | null;
  /** ¿Puede usar el selector de cuenta? Lo decide el backend mirando el
   *  admin real, no el rol efectivo: al pasarse a Mauro (rol `pro`) el rol
   *  que llega aquí es `pro` y el selector tiene que seguir estando para
   *  poder volver. */
  puede_cambiar_usuario?: boolean;
}

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<MeResponse>(`/api/v1/auth/me`),
    staleTime: 60 * 1000,
    refetchOnWindowFocus: true,
  });
}

/** ¿Quien mira es un `pro` (Ana, Mauro) y no el administrador?
 *
 *  Sirve para esconder acciones que gastan cuota de IA y cuyo resultado es
 *  COMPARTIDO (los textos del producto): que las lance uno solo. No es
 *  seguridad — el backend corta por su cuenta (`_PREFIJOS_PRO`).
 *
 *  Mientras `useMe` carga devuelve `false`: enseñar el botón medio segundo y
 *  quitarlo es menos malo que esconderle el suyo al administrador. */
export function useEsPro(): boolean {
  return useMe().data?.rol === "pro";
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation<
    { username: string; exp: number },
    Error,
    { username: string; password: string }
  >({
    mutationFn: (body) =>
      api.post<{ username: string; exp: number }>(`/api/v1/auth/login`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}

/** Primera entrada: elegir el PIN. Solo vale si ese usuario no tiene aún. */
export function useCrearPin() {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean; username: string },
    Error,
    { username: string; pin: string; pin2: string }
  >({
    mutationFn: (body) =>
      api.post<{ ok: boolean; username: string }>(`/api/v1/auth/crear-pin`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}

/** ¿El admin está ahora mismo viendo la app como otra persona? */
export function useSuplantando(): string | null {
  return useMe().data?.admin_real ?? null;
}

/** Cambiar de cuenta sin pedir el PIN del otro (solo admin).
 *
 *  Pasar el propio username del admin es lo que le devuelve a su cuenta: es
 *  el mismo endpoint, no hay dos.
 *
 *  Tras el cambio se RECARGA la página entera a propósito. Todo lo que hay en
 *  caché (productos, progreso, cola, cuota) es de la persona anterior, y la
 *  mitad de las pantallas ni siquiera son visibles para el rol nuevo — vaciar
 *  query por query sería más frágil que empezar de cero. */
export function useCambiarUsuario() {
  return useMutation<
    { username: string; nombre: string; rol: string; admin_real: string | null },
    Error,
    { username: string }
  >({
    mutationFn: (body) =>
      api.post(`/api/v1/auth/cambiar-usuario`, body),
    onSuccess: () => {
      window.location.assign("/");
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => api.post<void>(`/api/v1/auth/logout`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}
