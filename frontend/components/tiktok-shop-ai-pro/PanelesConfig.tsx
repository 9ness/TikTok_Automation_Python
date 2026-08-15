"use client";

import { Loader2, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  useActivarCuentaEchoTik,
  useBorrarCuentaEchoTik,
  useEchoTikCuentas,
  useEchoTikEstado,
  useGuardarCuentaEchoTik,
  useGuardarEchoTik,
  useGuardarHashtags,
  useHashtags,
} from "@/lib/queries/nichoPovBof";

/** Ajustes que se tocan de uvas a peras: los hashtags del caption y las cuentas
 *  de EchoTik. Viven en su propia pantalla y no dentro de cada nicho, que es
 *  donde estorbaban: el trabajo de todos los días es la carpeta de productos.
 */
export function HashtagsPanel() {
  const tagsQuery = useHashtags();
  const guardar = useGuardarHashtags();
  const [nuevo, setNuevo] = useState("");
  const tags = tagsQuery.data ?? [];

  function aplicar(siguientes: string[]) {
    guardar.mutate(siguientes, {
      onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
    });
  }

  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <p className="text-xs font-semibold">🏷️ Hashtags del caption</p>
      <p className="text-[11px] text-muted-foreground">
        Se pegan al final de TODOS los captions al copiarlos. Cámbialos según
        la campaña.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px]"
          >
            {t}
            <button
              type="button"
              aria-label={`Quitar ${t}`}
              onClick={() => aplicar(tags.filter((x) => x !== t))}
              className="text-muted-foreground transition hover:text-destructive"
            >
              ×
            </button>
          </span>
        ))}
        {tags.length === 0 && !tagsQuery.isLoading && (
          <span className="text-[11px] text-muted-foreground">Ninguno.</span>
        )}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const t = nuevo.trim();
          if (!t) return;
          aplicar([...tags, t]);
          setNuevo("");
        }}
        className="flex gap-1.5"
      >
        <input
          value={nuevo}
          onChange={(e) => setNuevo(e.target.value)}
          placeholder="#rebajasdeverano"
          className="min-w-0 flex-1 rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs"
        />
        <button
          type="submit"
          disabled={guardar.isPending || !nuevo.trim()}
          className="rounded-md border border-border/60 px-3 py-1.5 text-xs font-medium transition hover:border-foreground/30 disabled:opacity-50"
        >
          Añadir
        </button>
      </form>
    </section>
  );
}

/** Ver la foto de un producto en grande y descargarla suelta.
 *
 *  Muestra TAMBIÉN la captura con título cuando existe: es la forma rápida de
 *  cazar un emparejado raro (pasó con una carpeta donde la foto limpia de un
 *  producto estaba guardada con el número de otro). */


/** Fecha corta ("28 ago"), o "" si no hay. Las horas no importan aquí: lo que
 *  se mira es si ya pasó el mes. */
function diaCorto(ts: number | null | undefined): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
  });
}

/** Credenciales de EchoTik, cambiables sin redespliegue. */
export function EchoTikPanel() {
  const estado = useEchoTikEstado();
  const guardar = useGuardarEchoTik();
  const cuentas = useEchoTikCuentas();
  const guardarCuenta = useGuardarCuentaEchoTik();
  const activarCuenta = useActivarCuentaEchoTik();
  const borrarCuenta = useBorrarCuentaEchoTik();
  const [abierto, setAbierto] = useState(false);
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");

  const puedeGuardar = usuario.trim().length >= 4 && password.trim().length >= 8;
  const listaCuentas = cuentas.data ?? [];
  // Cuenta también la que está en uso: si le quedan llamadas, es una cuenta
  // con llamadas libres. Excluirla decía "0 con llamadas libres" con la única
  // cuenta en verde justo debajo.
  const libres = listaCuentas.filter((c) => c.disponible).length;

  const d = estado.data;
  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="text-sm font-semibold">🔑 API de EchoTik (enlaces)</span>
        <span className="text-[11px] text-muted-foreground">
          {d
            ? d.configurado
              ? `${d.usuario_mascara} · ${d.origen === "guardadas" ? "guardadas aquí" : "del .env"}`
              : "sin configurar"
            : "…"}
        </span>
      </button>

      {d?.mensaje && !guardar.isPending && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-500">
          {d.mensaje}
        </p>
      )}

      {abierto && (
        <div className="space-y-2">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Se aplican al instante, sin desplegar nada. Al guardar se gasta UNA
            llamada comprobando que funcionan; si no funcionan, no se guardan.
          </p>
          <input
            type="text"
            inputMode="numeric"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            placeholder="usuario (el número largo)"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="contraseña"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs"
          />
          <button
            type="button"
            disabled={guardar.isPending || !puedeGuardar}
            onClick={() =>
              guardar.mutate(
                { usuario: usuario.trim(), password: password.trim(), probar: true },
                {
                  onSuccess: (r) => {
                    if (r.ok) {
                      toast.success(r.mensaje);
                      setUsuario("");
                      setPassword("");
                      setAbierto(false);
                    } else {
                      toast.error(r.mensaje);
                    }
                  },
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : String(e)),
                },
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
          >
            {guardar.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Comprobando…
              </>
            ) : (
              "Usar ahora (gasta 1 llamada)"
            )}
          </button>

          {/* Guardar SIN activar: para ir apuntando cuentas de respaldo según
              se van creando, sin tocar la que está funcionando ni gastarle
              una llamada a la nueva. */}
          <button
            type="button"
            disabled={guardarCuenta.isPending || !puedeGuardar}
            onClick={() =>
              guardarCuenta.mutate(
                { usuario: usuario.trim(), password: password.trim(), nota: "" },
                {
                  onSuccess: (r) => {
                    toast.success(r.mensaje || "Cuenta guardada");
                    setUsuario("");
                    setPassword("");
                  },
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : String(e)),
                },
              )
            }
            className="w-full rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
          >
            Guardar de respaldo (sin usarla, 0 llamadas)
          </button>
        </div>
      )}

      {/* Banco de cuentas. El plan gratis da 100 llamadas AL MES: una cuenta
          seca no se tira, se aparta y se vuelve a ella cuando le renueva. */}
      {listaCuentas.length > 0 && (
        <div className="space-y-1.5 border-t border-border/60 pt-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-muted-foreground">
              Cuentas guardadas · {libres} con llamadas libres
            </p>
            {/* Añadir estaba escondido detrás del título del panel y no se
                encontraba. Aquí, pegado a la lista, es donde se busca. */}
            {!abierto && (
              <button
                type="button"
                onClick={() => setAbierto(true)}
                className="shrink-0 rounded-md border border-border/60 px-2 py-1 text-[11px] transition hover:border-emerald-500 hover:text-emerald-500"
              >
                + Añadir cuenta
              </button>
            )}
          </div>
          {listaCuentas.map((c) => {
            const renueva = diaCorto(c.renueva_at);
            return (
              <div
                key={c.usuario}
                className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 ${
                  c.activa
                    ? "border-emerald-500/60 bg-emerald-500/10"
                    : "border-border/60"
                }`}
              >
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    c.disponible ? "bg-emerald-500" : "bg-amber-500"
                  }`}
                  title={c.disponible ? "Con llamadas" : "Agotada este ciclo"}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">
                    {c.usuario_mascara}
                    {c.activa && (
                      <span className="ml-1 text-[10px] font-normal text-emerald-500">
                        en uso
                      </span>
                    )}
                  </p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {c.primer_uso_at
                      ? `${c.llamadas}/100 · ${
                          c.disponible
                            ? `renueva ~${renueva}`
                            : `libre ~${renueva}`
                        }`
                      : "sin estrenar"}
                  </p>
                </div>
                {!c.activa && (
                  <button
                    type="button"
                    disabled={activarCuenta.isPending}
                    onClick={() =>
                      activarCuenta.mutate(c.usuario, {
                        onSuccess: (r) => toast.success(r.mensaje || "Activada"),
                        onError: (e) =>
                          toast.error(e instanceof ApiError ? e.message : String(e)),
                      })
                    }
                    className="shrink-0 rounded-md border border-border/60 px-2 py-1 text-[11px] transition hover:border-emerald-500 hover:text-emerald-500 disabled:opacity-50"
                  >
                    Usar
                  </button>
                )}
                <button
                  type="button"
                  disabled={borrarCuenta.isPending}
                  onClick={() =>
                    borrarCuenta.mutate(c.usuario, {
                      onSuccess: () => toast.success("Cuenta borrada"),
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    })
                  }
                  className="shrink-0 rounded-md p-1 text-muted-foreground transition hover:text-destructive disabled:opacity-50"
                  aria-label={`Borrar ${c.usuario_mascara}`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
