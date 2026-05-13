"use client";

import { useState } from "react";
import { Loader2, LogIn } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useLogin, useMe } from "@/lib/queries/auth";

/** Modal de login que tapa toda la pantalla cuando no hay sesión.
 *  Solo se renderiza si `/api/v1/auth/me` devuelve `username === null`
 *  (modo prod con AUTH_COOKIE_KEY configurado). En dev local sin auth
 *  el endpoint devuelve un username válido directamente y este modal
 *  nunca aparece. */
export function LoginGate({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Mientras carga el `/me`, mostramos el layout normal — los hijos pueden
  // que también requieran auth pero los queries fallarán con 401 y los
  // toasts lo gestionarán. No queremos bloquear toda la UI por un flicker.
  if (me.isLoading) return <>{children}</>;
  // Sesión OK
  if (me.data?.username) return <>{children}</>;
  // Sin sesión → bloqueo total con form de login.

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login.mutateAsync({ username: username.trim(), password });
      setPassword("");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Error de login.",
      );
    }
  }

  const userOptions = me.data?.available_users ?? [];

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/95 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border bg-card p-6 shadow-xl"
      >
        <header className="space-y-1 text-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/brand/logo.png"
            alt="NebulabsAI"
            width={48}
            height={48}
            className="mx-auto rounded-md"
          />
          <h1 className="brand-gradient-text text-lg font-bold tracking-tight">
            NebulabsAI
          </h1>
          <p className="text-xs text-muted-foreground">
            Inicia sesión para continuar
          </p>
        </header>

        <div className="space-y-1.5">
          <Label htmlFor="username" className="text-xs">
            Usuario
          </Label>
          {userOptions.length > 0 ? (
            <select
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              required
            >
              <option value="">— elige usuario —</option>
              {userOptions.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          ) : (
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="ness"
              autoComplete="username"
              required
            />
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password" className="text-xs">
            Contraseña
          </Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={login.isPending || !username || !password}
        >
          {login.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <LogIn className="h-4 w-4" />
          )}
          Entrar
        </Button>
      </form>
    </div>
  );
}
