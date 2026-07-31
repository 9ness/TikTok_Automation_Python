"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, LogIn } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useCrearPin, useLogin, useMe } from "@/lib/queries/auth";

/** Modal de login que tapa toda la pantalla cuando no hay sesión.
 *  Solo se renderiza si `/api/v1/auth/me` devuelve `username === null`
 *  (modo prod con AUTH_COOKIE_KEY configurado). En dev local sin auth
 *  el endpoint devuelve un username válido directamente y este modal
 *  nunca aparece. */
export function LoginGate({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const login = useLogin();
  const router = useRouter();
  const pathname = usePathname();
  const crearPin = useCrearPin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pin2, setPin2] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Un `pro` que abra la raíz (o cualquier sección que no es suya) acabaría
  // en una página vacía llena de 403. Se le lleva a lo suyo.
  const rol = me.data?.rol;
  useEffect(() => {
    if (!me.data?.username || rol !== "pro") return;
    if (!pathname.startsWith("/tiktok-shop-ai-pro")) {
      // typedRoutes exige la aserción: la ruta es literal y existe.
      router.replace("/tiktok-shop-ai-pro/nicho-pov-bof" as never);
    }
  }, [me.data?.username, rol, pathname, router]);

  // Mientras carga el `/me`, mostramos el layout normal — los hijos pueden
  // que también requieran auth pero los queries fallarán con 401 y los
  // toasts lo gestionarán. No queremos bloquear toda la UI por un flicker.
  if (me.isLoading) return <>{children}</>;
  // Sesión OK
  if (me.data?.username) return <>{children}</>;
  // Sin sesión → bloqueo total con form de login.

  // Quien no tiene PIN todavía es que entra por primera vez: en vez de
  // pedirle una contraseña que no existe, se le hace elegirla.
  const ficha = (me.data?.usuarios ?? []).find((u) => u.username === username);
  const primeraVez = Boolean(username) && ficha != null && !ficha.tiene_pin;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (primeraVez) {
        if (password !== pin2) {
          setError("Los dos PIN no coinciden.");
          return;
        }
        await crearPin.mutateAsync({
          username: username.trim(), pin: password, pin2,
        });
        setPassword("");
        setPin2("");
        return;
      }
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
            {primeraVez
              ? "Primera vez: elige tu PIN"
              : "¿Quién eres?"}
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
              {(me.data?.usuarios ?? []).length > 0
                ? (me.data?.usuarios ?? []).map((u) => (
                    <option key={u.username} value={u.username}>
                      {u.nombre}
                      {u.tiene_pin ? "" : " · crear PIN"}
                    </option>
                  ))
                : userOptions.map((u) => (
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
            {primeraVez ? "Elige tu PIN (mínimo 4)" : "PIN"}
          </Label>
          <Input
            id="password"
            type="password"
            inputMode="numeric"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={primeraVez ? "new-password" : "current-password"}
            required
          />
        </div>

        {primeraVez && (
          <div className="space-y-1.5">
            <Label htmlFor="pin2" className="text-xs">
              Repite el PIN
            </Label>
            <Input
              id="pin2"
              type="password"
              inputMode="numeric"
              value={pin2}
              onChange={(e) => setPin2(e.target.value)}
              autoComplete="new-password"
              required
            />
            <p className="text-[11px] text-muted-foreground">
              Se guarda en este dispositivo, no tendrás que escribirlo cada vez.
            </p>
          </div>
        )}

        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={
            login.isPending ||
            crearPin.isPending ||
            !username ||
            !password ||
            (primeraVez && !pin2)
          }
        >
          {login.isPending || crearPin.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <LogIn className="h-4 w-4" />
          )}
          {primeraVez ? "Crear PIN y entrar" : "Entrar"}
        </Button>
      </form>
    </div>
  );
}
