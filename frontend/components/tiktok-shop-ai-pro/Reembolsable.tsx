"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Caja } from "@/components/tiktok-shop-ai-pro/Paso";
import { ApiError } from "@/lib/api";
import {
  useActualizarReembolsable,
  useDesmarcarReembolsable,
  useMarcarReembolsable,
  useReembolsables,
} from "@/lib/queries/nichoPovBof";
import type { ReembolsoInfo } from "@/lib/types/nichoPovBof";

/** Muestras REEMBOLSABLES de «Muestras productos» (`mis_productos`).
 *
 *  Una muestra normal se pide gratis y basta con un vídeo; una reembolsable
 *  la devuelve la tienda solo si llega a X ventas antes de una fecha. Por eso
 *  tiene que verse de un vistazo y recordar que hay que revisarla.
 *
 *  Color propio: TEAL (no lo usa ningún color con significado de UI_NICHOS).
 *  Cambia de tono con el estado usando los colores que ya significan eso:
 *  esmeralda cumplido, rosa vencido, ámbar «toca revisar».
 */

export const SOURCE_REEMBOLSABLES = "mis_productos";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

function textoDias(r: ReembolsoInfo): string {
  if (r.dias_restantes < 0) return `venció hace ${-r.dias_restantes} d`;
  if (r.dias_restantes === 0) return "vence hoy";
  return `faltan ${r.dias_restantes} ${r.dias_restantes === 1 ? "día" : "días"}`;
}

function tono(r: ReembolsoInfo): { icono: string; clase: string; etiqueta: string } {
  if (r.estado === "cumplido")
    return {
      icono: "✅",
      clase: "border-emerald-500/50 bg-emerald-500/15 text-emerald-500",
      etiqueta: "Reembolso cumplido",
    };
  if (r.estado === "vencido")
    return {
      icono: "⛔",
      clase: "border-rose-500/50 bg-rose-500/15 text-rose-500",
      etiqueta: "Reembolso vencido",
    };
  if (r.toca_revisar)
    return {
      icono: "🔔",
      clase: "border-amber-500/60 bg-amber-500/15 text-amber-500",
      etiqueta: "Reembolsable · Revisar",
    };
  return {
    icono: "💸",
    clase: "border-teal-500/50 bg-teal-500/15 text-teal-500",
    etiqueta: "Reembolsable",
  };
}

/** «💸 Reembolsable · 1/3 ventas · faltan 45 días» */
export function BadgeReembolso({ info, className = "" }: { info: ReembolsoInfo; className?: string }) {
  const t = tono(info);
  return (
    <span
      title={
        `Muestra reembolsable: ${info.ventas} de ${info.ventas_objetivo} ventas antes del ` +
        `${info.fecha_limite}` + (info.notas ? ` · ${info.notas}` : "")
      }
      className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${t.clase} ${className}`}
    >
      <span className="shrink-0">{t.icono}</span>
      <span className="truncate">
        {t.etiqueta} · {info.ventas}/{info.ventas_objetivo} ventas
        {info.estado === "en_curso" || info.estado === "vencido" ? ` · ${textoDias(info)}` : ""}
      </span>
    </span>
  );
}

/** Diálogo para marcar / editar / desmarcar. */
function DialogoReembolso({
  abierto,
  onCerrar,
  folder,
  producto,
  titulo,
  info,
}: {
  abierto: boolean;
  onCerrar: () => void;
  folder: string;
  producto: string;
  titulo: string;
  info: ReembolsoInfo | null | undefined;
}) {
  const marcar = useMarcarReembolsable();
  const actualizar = useActualizarReembolsable();
  const desmarcar = useDesmarcarReembolsable();
  const [objetivo, setObjetivo] = useState("1");
  const [dias, setDias] = useState("");
  const [ventas, setVentas] = useState("0");
  const [notas, setNotas] = useState("");
  const [confirmarQuitar, setConfirmarQuitar] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    setObjetivo(String(info?.ventas_objetivo ?? 1));
    setDias(info ? String(Math.max(0, info.dias_restantes)) : "");
    setVentas(String(info?.ventas ?? 0));
    setNotas(info?.notas ?? "");
    setConfirmarQuitar(false);
  }, [abierto, info]);

  const ocupado = marcar.isPending || actualizar.isPending || desmarcar.isPending;
  const nObjetivo = Number.parseInt(objetivo, 10);
  const nDias = Number.parseInt(dias, 10);
  const nVentas = Number.parseInt(ventas || "0", 10);
  const valido = nObjetivo >= 1 && nDias >= 0 && nVentas >= 0;

  const guardar = () => {
    if (!valido) {
      toast.error("Pon ventas necesarias (1 o más) y los días que quedan.");
      return;
    }
    const fin = { onSuccess: () => { toast.success("Guardado"); onCerrar(); }, onError: (e: unknown) => toast.error(err(e)) };
    if (!info) {
      marcar.mutate(
        { folder, producto, ventas_objetivo: nObjetivo, dias: nDias, ventas: nVentas, notas },
        fin,
      );
      return;
    }
    actualizar.mutate(
      {
        folder,
        producto,
        ventas_objetivo: nObjetivo,
        ventas: nVentas,
        notas,
        // Solo se recalcula la fecha si se tocan los días: abrir y guardar no
        // debe mover la fecha límite.
        ...(nDias !== Math.max(0, info.dias_restantes) ? { dias: nDias } : {}),
      },
      fin,
    );
  };

  const campo = "w-full rounded-lg border border-border/60 bg-background px-2 py-1.5 text-xs outline-none focus:border-teal-500/60 sm:text-sm";

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-md max-h-[90vh] overflow-y-auto rounded-xl border-teal-500/40 p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle className="text-base text-teal-500">
            💸 {info ? "Muestra reembolsable" : "Marcar como reembolsable"}
          </DialogTitle>
          <DialogDescription className="break-words text-xs sm:text-sm">
            {producto} · {titulo || "Producto"}
          </DialogDescription>
        </DialogHeader>
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          La tienda devuelve la muestra si el producto llega a estas ventas antes de la fecha.
          Revísala cada pocos días; si no vende, haz más versiones o replica un viral.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-muted-foreground">Ventas necesarias</span>
            <input type="number" inputMode="numeric" min={1} value={objetivo} onChange={(e) => setObjetivo(e.target.value)} className={campo} />
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-muted-foreground">Días que quedan</span>
            <input type="number" inputMode="numeric" min={0} value={dias} placeholder="110" onChange={(e) => setDias(e.target.value)} className={campo} />
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-muted-foreground">Ventas que lleva</span>
            <input type="number" inputMode="numeric" min={0} value={ventas} onChange={(e) => setVentas(e.target.value)} className={campo} />
          </label>
          {info && (
            <div className="space-y-1">
              <span className="text-[11px] font-medium text-muted-foreground">Fecha límite</span>
              <p className="py-1.5 text-xs sm:text-sm">{info.fecha_limite}</p>
            </div>
          )}
        </div>
        <label className="block space-y-1">
          <span className="text-[11px] font-medium text-muted-foreground">Notas (opcional)</span>
          <textarea rows={2} maxLength={500} value={notas} onChange={(e) => setNotas(e.target.value)} className={`${campo} resize-none`} />
        </label>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:gap-0">
          {info &&
            (confirmarQuitar ? (
              <button
                type="button"
                disabled={ocupado}
                onClick={() =>
                  desmarcar.mutate(
                    { folder, producto },
                    { onSuccess: () => { toast.success("Vuelve a ser una muestra normal"); onCerrar(); }, onError: (e) => toast.error(err(e)) },
                  )
                }
                className="rounded-lg border border-rose-500/60 px-3 py-2 text-xs font-semibold text-rose-500 sm:mr-auto sm:text-sm"
              >
                ¿Seguro? Quitar
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmarQuitar(true)}
                className="rounded-lg border border-border/60 px-3 py-2 text-xs text-muted-foreground transition hover:text-rose-500 sm:mr-auto sm:text-sm"
              >
                Quitar reembolsable
              </button>
            ))}
          <button
            type="button"
            onClick={onCerrar}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs font-medium text-muted-foreground transition hover:text-foreground sm:text-sm"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={ocupado || !valido}
            onClick={guardar}
            className="rounded-lg bg-teal-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-teal-700 disabled:opacity-50 sm:text-sm"
          >
            {ocupado ? "Guardando…" : info ? "Guardar" : "Marcar reembolsable"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Lo que va en la tarjeta: el badge (si lo es) + acciones rápidas, o el
 *  botón para marcarlo. Solo se pinta en «Muestras productos». */
export function ReembolsoTarjeta({
  source,
  folder,
  producto,
  titulo,
  info,
}: {
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  info: ReembolsoInfo | null | undefined;
}) {
  const [abierto, setAbierto] = useState(false);
  const actualizar = useActualizarReembolsable();
  if (source !== SOURCE_REEMBOLSABLES || !folder) return null;

  const rapido = (cambios: { sumar_ventas?: number }, ok: string) =>
    actualizar.mutate(
      { folder, producto, ...cambios },
      { onSuccess: () => toast.success(ok), onError: (e) => toast.error(err(e)) },
    );

  const boton = "rounded-full border px-2 py-0.5 text-[10px] font-semibold transition disabled:opacity-50";
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      {info ? (
        <>
          <button type="button" onClick={() => setAbierto(true)} className="max-w-full" title="Editar">
            <BadgeReembolso info={info} />
          </button>
          {info.estado !== "cumplido" && (
            <button
              type="button"
              disabled={actualizar.isPending}
              onClick={() => rapido({ sumar_ventas: 1 }, "+1 venta apuntada")}
              className={`${boton} border-teal-500/50 text-teal-500 hover:bg-teal-500/10`}
            >
              +1 venta
            </button>
          )}
          {info.estado === "en_curso" && (
            <button
              type="button"
              disabled={actualizar.isPending}
              onClick={() => rapido({}, "Revisado, sin ventas nuevas")}
              className={`${boton} ${
                info.toca_revisar
                  ? "border-amber-500/60 text-amber-500 hover:bg-amber-500/10"
                  : "border-border/60 text-muted-foreground hover:text-foreground"
              }`}
            >
              Revisado, sin ventas
            </button>
          )}
        </>
      ) : (
        <button
          type="button"
          onClick={() => setAbierto(true)}
          className={`${boton} border-dashed border-teal-500/40 text-teal-500/80 hover:bg-teal-500/10`}
        >
          💸 ¿Reembolsable?
        </button>
      )}
      <DialogoReembolso
        abierto={abierto}
        onCerrar={() => setAbierto(false)}
        folder={folder}
        producto={producto}
        titulo={titulo}
        info={info}
      />
    </div>
  );
}

/** Caja arriba en «Muestras productos»: las reembolsables y cuántas toca
 *  revisar. Tocar una lleva a su carpeta. */
export function CajaReembolsables({
  source,
  onAbrir,
}: {
  source: string;
  onAbrir?: (folder: string) => void;
}) {
  const activo = source === SOURCE_REEMBOLSABLES;
  const q = useReembolsables(activo);
  const [verTodas, setVerTodas] = useState(false);
  if (!activo) return null;
  const d = q.data;
  if (!d || !d.total) {
    if (q.isLoading) return null;
    return (
      <p className="rounded-xl border border-dashed border-teal-500/30 px-3 py-2 text-[10px] text-muted-foreground">
        💸 Ninguna muestra reembolsable. Márcala desde su tarjeta («💸 ¿Reembolsable?») o al subirla.
      </p>
    );
  }
  const items = verTodas ? d.items : d.items.filter((i) => i.reembolso?.estado === "en_curso");
  return (
    <Caja
      icono="💸"
      titulo="Muestras reembolsables"
      hint={`X ventas antes de una fecha. Revísalas cada ${d.revisar_cada_dias} días; si no venden, más versiones o un viral.`}
      extra={
        d.toca_revisar ? (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-500">
            🔔 {d.toca_revisar} por revisar
          </span>
        ) : (
          `${d.en_curso} en curso`
        )
      }
    >
      <ul className="space-y-1">
        {items.map((i) => (
          <li key={`${i.folder}|${i.producto}`}>
            <button
              type="button"
              onClick={() => onAbrir?.(i.folder)}
              className="flex w-full flex-col items-start gap-0.5 rounded-lg border border-border/60 px-2 py-1.5 text-left transition hover:border-teal-500/50 sm:flex-row sm:items-center sm:gap-2"
            >
              <span className="flex min-w-0 items-baseline gap-1.5 text-[11px] sm:flex-1">
                <span className="shrink-0 rounded bg-muted px-1 font-mono text-[9px] text-muted-foreground">
                  {i.folder.replace(/^Mis Productos\s*/, "C")}·{i.producto}
                </span>
                <span className="truncate">{i.titulo || "sin título"}</span>
              </span>
              {i.reembolso && <BadgeReembolso info={i.reembolso} className="shrink-0" />}
            </button>
          </li>
        ))}
        {!items.length && (
          <li className="text-[10px] text-muted-foreground">Ninguna en curso.</li>
        )}
      </ul>
      {d.total > d.en_curso && (
        <button
          type="button"
          onClick={() => setVerTodas((v) => !v)}
          className="text-[10px] text-muted-foreground underline-offset-2 hover:underline"
        >
          {verTodas
            ? "Ver solo las en curso"
            : `Ver también ${d.cumplidos} cumplida(s) y ${d.vencidos} vencida(s)`}
        </button>
      )}
    </Caja>
  );
}
