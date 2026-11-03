"use client";

import { ExternalLink, KeyRound, Loader2, Power } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/lib/queries/auth";
import {
  type MaquinaNavegador,
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
 *
 *  `maquina="casa"` es el mismo montaje en el PC de casa del operador (WSL, por
 *  Tailscale; `deploy/navegador_casa/`): sale por la IP de casa y se abre en
 *  `/navegador-casa/`. Si el PC está apagado, lo dice en vez de dar error.
 */
const TEXTOS: Record<MaquinaNavegador, { titulo: string; ruta: string; desc: string }> = {
  vps: {
    titulo: "🖥️ Navegador remoto · VPS",
    ruta: "/navegador",
    desc: "Chrome dentro del servidor, para generar en Flow y Magnific sin el PC. Enciéndelo cuando lo necesites y ábrelo desde aquí, en el móvil o en cualquier ordenador.",
  },
  casa: {
    titulo: "🏠 Navegador remoto · PC de casa",
    ruta: "/navegador-casa",
    desc: "Chrome dentro del PC de casa (sin ventana en tu pantalla), con la conexión de casa. Sirve para repartir: unos agentes generan aquí y otros en el VPS. Necesita el PC encendido y con la sesión de Windows iniciada.",
  },
};

export function NavegadorRemoto({ maquina = "vps" }: { maquina?: MaquinaNavegador }) {
  const me = useMe();
  const esAdmin = me.data?.rol === "admin";
  const estado = useEstadoNavegador(esAdmin, maquina);
  const accion = useAccionNavegador(maquina);
  const t = TEXTOS[maquina];

  if (!esAdmin) return null;

  const e = estado.data;
  const cambiando = accion.isPending;

  /** Abre el visor ya con la contraseña puesta. La contraseña va tras el `#`
   *  (fragmento): el navegador no la manda al servidor, así que no queda en
   *  ningún registro. Se navega en la MISMA pestaña —sin `window.open`—: en la
   *  app del móvil una pestaña nueva salía en blanco («about:blank») y ofrecía
   *  abrirla con otra aplicación. El visor (`deploy/navegador/visor.html`) es
   *  propio porque el `vnc.html` de noVNC conectaba pero dejaba la pantalla gris
   *  en Android. */
  async function abrir() {
    try {
      const clave = await pedirClaveNavegador(maquina);
      window.location.href = `${t.ruta}/visor.html#password=${encodeURIComponent(clave)}`;
    } catch {
      toast.error("No se pudo abrir el navegador");
    }
  }

  async function copiarClave() {
    try {
      await navigator.clipboard.writeText(await pedirClaveNavegador(maquina));
      toast.success("Contraseña copiada — pégala al abrir el navegador");
    } catch {
      toast.error("No se pudo copiar la contraseña");
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {t.titulo}
          {e?.sin_conexion ? (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-500">
              PC sin conexión
            </span>
          ) : e ? (
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
          {t.desc}
          {e?.sin_conexion
            ? " Ahora no responde: enciende el PC e inicia sesión en Windows."
            : e?.encendido
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
              <Button size="sm" onClick={() => void abrir()}>
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Abrir navegador
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
              disabled={cambiando || estado.isLoading || !!e?.sin_conexion}
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
