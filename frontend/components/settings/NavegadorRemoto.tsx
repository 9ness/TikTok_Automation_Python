"use client";

import { ExternalLink, KeyRound, Loader2, Power } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/lib/queries/auth";
import {
  pedirClaveNavegador,
  useAccionNavegador,
  useEstadoNavegador,
} from "@/lib/queries/navegador";

/** El Chrome del VPS (Flow / Magnific) sin tener el PC encendido.
 *
 *  Solo el administrador: ese Chrome lleva las cuentas abiertas. Enciende y
 *  apaga desde aquí (gasta ~1 GB de RAM mientras está encendido y se apaga solo
 *  tras un rato sin nadie), y «Abrir» va a `/navegador/`, que Caddy protege con
 *  el mismo login de la app.
 */
export function NavegadorRemoto() {
  const me = useMe();
  const esAdmin = me.data?.rol === "admin";
  const estado = useEstadoNavegador(esAdmin);
  const accion = useAccionNavegador();

  if (!esAdmin) return null;

  const e = estado.data;
  const cambiando = accion.isPending;

  async function copiarClave() {
    try {
      await navigator.clipboard.writeText(await pedirClaveNavegador());
      toast.success("Contraseña copiada — pégala al abrir el navegador");
    } catch {
      toast.error("No se pudo copiar la contraseña");
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          🖥️ Navegador remoto
          {e ? (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                e.encendido
                  ? "bg-emerald-500/15 text-emerald-500"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {e.encendido ? "Encendido" : "Apagado"}
            </span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          Chrome dentro del servidor, para generar en Flow y Magnific sin el PC. Enciéndelo
          cuando lo necesites y ábrelo desde aquí, en el móvil o en cualquier ordenador.
          {e?.encendido
            ? ` Usa unos ${e.chrome_mb} MB y se apaga solo tras ${e.autoapagado_min} min sin uso.`
            : " Apagado no gasta nada."}
        </p>

        {estado.isError ? (
          <p className="text-xs text-destructive">
            No se pudo consultar el estado (¿está activo el listener del servidor?).
          </p>
        ) : null}

        {e?.encendido && e.pestanas.length ? (
          <ul className="space-y-0.5 text-[11px] text-muted-foreground">
            {e.pestanas.map((p, i) => (
              <li key={i} className="truncate">
                🗂️ {p.host || "—"} · {p.titulo}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {e?.encendido ? (
            <>
              <Button asChild size="sm">
                <a
                  href="/navegador/vnc.html?path=navegador/websockify&autoconnect=1&resize=remote"
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Abrir navegador
                </a>
              </Button>
              <Button size="sm" variant="outline" onClick={() => void copiarClave()}>
                <KeyRound className="mr-1.5 h-3.5 w-3.5" /> Copiar contraseña
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={cambiando}
                onClick={() => accion.mutate("apagar")}
              >
                {cambiando ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Power className="mr-1.5 h-3.5 w-3.5" />
                )}
                Apagar
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              disabled={cambiando || estado.isLoading}
              onClick={() => accion.mutate("encender")}
            >
              {cambiando ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Power className="mr-1.5 h-3.5 w-3.5" />
              )}
              Encender navegador
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
