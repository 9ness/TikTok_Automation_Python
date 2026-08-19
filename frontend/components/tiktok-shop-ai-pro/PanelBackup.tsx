"use client";

import { HardDrive, Loader2, Package, RefreshCw, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  useBackupCheck,
  useBackupSync,
  useCompartirPaquete,
  useMontarPaquete,
  usePaquete,
  useUltimaCopia,
} from "@/lib/queries/nichoPovBof";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { BackupCheckResponse } from "@/lib/types/nichoPovBof";

/** Copia del Drive del curso a nuestro Drive.
 *
 *  Vive fuera de las pantallas de nicho porque no es trabajo diario: corre sola
 *  una vez al día y aquí solo se consulta o se fuerza. Lo que de verdad se mira
 *  es cuántos ficheros ha BORRADO el origen, que es lo único que avisa de que
 *  el admin de aquel Drive ha hecho limpieza.
 */
export function PanelBackup() {
  const [backup, setBackup] = useState<BackupCheckResponse | null>(null);
  const backupCheck = useBackupCheck();
  const backupSync = useBackupSync();
  const ultimaCopia = useUltimaCopia();
  const paquete = usePaquete();
  const montarPaquete = useMontarPaquete();
  const compartir = useCompartirPaquete();
  const [correo, setCorreo] = useState("");
  const openQueue = useDrawerStore((s) => s.openQueue);

  function checkBackup() {
    backupCheck.mutate(undefined, {
      onSuccess: (r) => {
        setBackup(r);
        toast.success(
          r.has_changes
            ? `${r.n_added} nuevos · ${r.n_modified} modificados · ${r.n_deleted} borrados`
            : "Sin cambios desde la última copia",
        );
      },
      onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
    });
  }

  function syncBackup(force: boolean) {
    backupSync.mutate(
      { force_full: force },
      {
        onSuccess: () => {
          toast.success("Copia en la cola");
          openQueue();
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-center gap-2">
        <HardDrive className="h-4 w-4 shrink-0 text-sky-500" />
        <p className="text-sm font-semibold">Copia de seguridad</p>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        El Drive de origen es de un tercero y se borra sin aviso. La copia corre
        sola una vez al día; aquí puedes comprobar qué ha cambiado o forzarla.
      </p>

      {ultimaCopia.data?.ts ? (
        <div className="space-y-0.5 rounded-lg border border-border/60 bg-muted/40 p-2 text-[11px]">
          <p className="text-muted-foreground">
            Copia automática:{" "}
            <span className="font-medium text-foreground">
              {new Date(ultimaCopia.data.ts * 1000).toLocaleString("es-ES", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>{" "}
            · {ultimaCopia.data.copied ?? 0} fichero(s) guardados
          </p>
          {(ultimaCopia.data.n_deleted ?? 0) > 0 && (
            <p className="font-semibold text-amber-500">
              ⚠️ el curso borró {ultimaCopia.data.n_deleted} fichero(s) del origen
              — los tuyos siguen en la copia
            </p>
          )}
        </div>
      ) : null}

      {backup && (
        <div className="space-y-1 rounded-lg border border-border/60 bg-muted/40 p-2 text-[11px]">
          <p className="text-muted-foreground">
            Última copia:{" "}
            <span className="font-medium text-foreground">
              {backup.last_snapshot ?? "ninguna"}
            </span>
          </p>
          {backup.has_changes ? (
            <>
              <p>
                <span className="font-semibold text-emerald-500">+{backup.n_added}</span>{" "}
                nuevos ·{" "}
                <span className="font-semibold text-amber-500">~{backup.n_modified}</span>{" "}
                modificados ·{" "}
                <span className="font-semibold text-red-500">-{backup.n_deleted}</span>{" "}
                borrados en origen
              </p>
              <p className="text-muted-foreground">
                {Math.round(backup.change_ratio * 100)}% del archivo (
                {backup.n_total_source} ficheros).{" "}
                {backup.would_be_full
                  ? "Se hará copia COMPLETA nueva."
                  : "Se copiará solo la diferencia."}
              </p>
            </>
          ) : (
            <p className="text-emerald-500">Sin cambios — no hay nada que copiar.</p>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={checkBackup}
          disabled={backupCheck.isPending}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
        >
          {backupCheck.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Comprobar cambios
        </button>
        <button
          type="button"
          onClick={() => syncBackup(false)}
          disabled={backupSync.isPending}
          className="flex items-center justify-center gap-1.5 rounded-lg bg-sky-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-600 disabled:opacity-50"
        >
          {backupSync.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <HardDrive className="h-3.5 w-3.5" />
          )}
          Sincronizar
        </button>
      </div>
      <button
        type="button"
        onClick={() => syncBackup(true)}
        disabled={backupSync.isPending}
        className="w-full rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
      >
        Forzar copia completa nueva
      </button>

      {/* El paquete: lo que se le DEVUELVE al dueño del Drive si lo pierde.
          Nuestro archivo son la copia completa más un delta por día, y eso no
          se le puede pasar a nadie: hay que juntarlo en una sola carpeta con
          el árbol tal y como estaba. */}
      <div className="space-y-2 rounded-lg border border-border/60 p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-xs font-semibold">
              <Package className="h-3.5 w-3.5 text-muted-foreground" /> Paquete para
              devolver
            </p>
            <p className="text-[11px] text-muted-foreground">
              Una sola carpeta con TODO el material y su estructura original.
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              montarPaquete.mutate(undefined, {
                onSuccess: () => {
                  toast.success("Montando el paquete — va por la cola");
                  openQueue();
                },
                onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
              })
            }
            disabled={montarPaquete.isPending}
            className="shrink-0 rounded-lg border border-border/60 px-2.5 py-1.5 text-[11px] font-semibold transition hover:border-foreground/30 disabled:opacity-50"
          >
            {montarPaquete.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              "Montar"
            )}
          </button>
        </div>

        {paquete.data?.carpeta ? (
          <p className="break-words text-[11px] text-emerald-500">
            📦 {paquete.data.carpeta.split("/").pop()} ·{" "}
            {paquete.data.ficheros?.toLocaleString("es-ES")} ficheros ·{" "}
            {((paquete.data.bytes ?? 0) / 2 ** 30).toFixed(2)} GB
          </p>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            Todavía no hay paquete montado.
          </p>
        )}

        <div className="flex gap-1.5">
          <input
            type="email"
            inputMode="email"
            value={correo}
            onChange={(e) => setCorreo(e.target.value)}
            placeholder="correo@gmail.com"
            className="min-w-0 flex-1 rounded-lg border border-border/60 bg-background px-2 py-1.5 text-xs"
          />
          <button
            type="button"
            onClick={() =>
              compartir.mutate(
                { correo, rol: "reader" },
                {
                  onSuccess: (r) => {
                    toast.success(`Compartido con ${r.correo}`);
                    setCorreo("");
                  },
                  onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
                },
              )
            }
            disabled={compartir.isPending || !correo.includes("@") || !paquete.data?.carpeta}
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {compartir.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            Compartir
          </button>
        </div>
      </div>
    </section>
  );
}
