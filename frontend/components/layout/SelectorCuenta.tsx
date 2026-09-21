"use client";

/**
 * Avatar circular junto al logo que abre "cambiar de cuenta" — como el de una
 * red social.
 *
 * Para qué: Ana y Mauro se atascan y hay que ver SU pantalla (sus productos,
 * su progreso, su cola) para desatascarles. Pedirles el PIN cada vez no es
 * práctico, así que el admin entra en su cuenta desde aquí.
 *
 * Quién lo ve: SOLO el admin. Y no se decide por el rol que llega en `/me`
 * —al pasarse a Mauro ese rol es `pro`— sino por `puede_cambiar_usuario`, que
 * el backend calcula mirando quién abrió la sesión de verdad. Si no, el admin
 * se quedaría encerrado en la cuenta de Mauro sin botón para volver.
 *
 * Esto es solo la cara visible: quien corta de verdad es
 * `POST /api/v1/auth/cambiar-usuario`, que exige admin.
 */

import { useState } from "react";
import { Check, Loader2, UserCog } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCambiarUsuario, useMe } from "@/lib/queries/auth";
import { cn } from "@/lib/utils";

/** Inicial para el círculo: la del nombre bonito si lo hay. */
function inicial(nombre: string | null | undefined, username: string): string {
  return (nombre || username || "?").trim().charAt(0).toUpperCase();
}

export function SelectorCuenta({ size = "md" }: { size?: "sm" | "md" }) {
  const me = useMe();
  const cambiar = useCambiarUsuario();
  const [abierto, setAbierto] = useState(false);

  const username = me.data?.username;
  if (!username || !me.data?.puede_cambiar_usuario) return null;

  const adminReal = me.data.admin_real ?? null;
  const suplantando = Boolean(adminReal);
  // `usuarios` trae nombre y rol; `available_users` es solo la lista de
  // nombres y la devuelve cualquier versión de la API. Se usa de respaldo
  // porque un diálogo VACÍO no dice qué ha fallado: pasó en la APK, donde
  // salía el título y nada debajo.
  const usuarios =
    me.data.usuarios && me.data.usuarios.length > 0
      ? me.data.usuarios
      : (me.data.available_users ?? []).map((u) => ({
          username: u,
          nombre: u,
          rol: u === adminReal ? "admin" : "pro",
          tiene_pin: true,
        }));
  const dim = size === "sm" ? "h-8 w-8 text-xs" : "h-9 w-9 text-sm";

  return (
    <>
      <button
        type="button"
        onClick={() => setAbierto(true)}
        title={
          suplantando
            ? `Viendo como ${me.data.nombre || username} — toca para volver`
            : "Cambiar de cuenta"
        }
        aria-label="Cambiar de cuenta"
        className={cn(
          "relative flex shrink-0 items-center justify-center rounded-full font-bold uppercase",
          "text-white transition-transform hover:scale-105",
          // Anillo ÁMBAR mientras se suplanta: es la única señal permanente de
          // "no estás en tu cuenta", y tiene que verse sin abrir nada.
          suplantando
            ? "bg-amber-500 ring-2 ring-amber-400 ring-offset-2 ring-offset-card"
            : "bg-gradient-to-br from-brand-cyan to-brand-violet ring-1 ring-border",
          dim,
        )}
      >
        {inicial(me.data.nombre, username)}
      </button>

      <Dialog open={abierto} onOpenChange={setAbierto}>
        {/* Ancho y alto acotados a la viewport: este diálogo se abre también
            desde la cabecera móvil. */}
        <DialogContent className="w-[calc(100vw-2rem)] max-w-sm max-h-[90vh] overflow-y-auto rounded-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <UserCog className="h-4 w-4 text-brand-cyan" strokeWidth={2} />
              Cambiar de cuenta
            </DialogTitle>
            <DialogDescription className="text-xs">
              {suplantando ? (
                <>
                  Estás viendo la app como{" "}
                  <span className="font-semibold text-amber-500">
                    {me.data.nombre || username}
                  </span>
                  . Tu sesión sigue siendo la de {adminReal}.
                </>
              ) : (
                <>Entras en su cuenta tal cual: verás sus productos, su progreso y su cola.</>
              )}
            </DialogDescription>
          </DialogHeader>

          <ul className="space-y-1.5">
            {usuarios.map((u) => {
              const actual = u.username === username;
              const esElAdmin = u.username === adminReal;
              return (
                <li key={u.username}>
                  <button
                    type="button"
                    disabled={actual || cambiar.isPending}
                    onClick={() => cambiar.mutate({ username: u.username })}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors",
                      actual
                        ? "border-brand-cyan/50 bg-accent/60"
                        : "hover:bg-accent/60 disabled:opacity-50",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold uppercase text-white",
                        actual
                          ? "bg-gradient-to-br from-brand-cyan to-brand-violet"
                          : "bg-muted-foreground/70",
                      )}
                    >
                      {inicial(u.nombre, u.username)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">
                        {u.nombre}
                      </span>
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {u.rol === "admin" ? "Administrador" : "Tiktok Shop AI Pro"}
                        {esElAdmin && !actual ? " · tu cuenta" : ""}
                      </span>
                    </span>
                    {actual ? (
                      <Check className="h-4 w-4 shrink-0 text-brand-cyan" strokeWidth={2.5} />
                    ) : cambiar.isPending &&
                      cambiar.variables?.username === u.username ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>

          {usuarios.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No llegó la lista de cuentas. Cierra y vuelve a abrir la app; si
              sigue igual, borra la caché de la aplicación.
            </p>
          )}

          {cambiar.isError && (
            <p className="text-xs text-destructive">{cambiar.error.message}</p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
