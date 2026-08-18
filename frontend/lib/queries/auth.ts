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

export function useLogout() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => api.post<void>(`/api/v1/auth/logout`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}
