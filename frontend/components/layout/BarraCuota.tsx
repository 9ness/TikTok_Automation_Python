"use client";

import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useAjustarCuota, useCuotaHoy, type CuotaTipo } from "@/lib/queries/cuotas";

/** Lo que se puede publicar hoy en la cuenta, en una sola línea.
 *
 *  Va en el marco y no dentro de un nicho porque el tope es de la CUENTA de
 *  TikTok: da igual con qué nicho se grabara el vídeo. Se reinicia solo a
 *  medianoche (hora de España) y es por usuario.
 *
 *  Ocupa una línea a propósito: se mira de reojo mientras se trabaja, no es una
 *  pantalla. Al tocarla se abre el ajuste manual, para los días en que ya has
 *  subido cosas fuera de la app.
 */
export function BarraCuota() {
  const cuota = useCuotaHoy();
  const [abierto, setAbierto] = useState(false);

  if (!cuota.data) return null;
  const { videos, carruseles } = cuota.data;

  return (
    <div className="border-b border-border/60 bg-background/80 px-3 py-1.5 backdrop-blur">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center gap-3 text-left"
        title="Tocar para ajustar a mano lo subido hoy"
      >
        <Medidor etiqueta="Vídeos" datos={videos} />
        <Medidor etiqueta="Carruseles" datos={carruseles} />
      </button>

      {abierto && (
        <div className="mt-2 space-y-2 rounded-lg border border-border/60 bg-card p-2">
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Se cuenta lo que marcas como <b>Subido</b> en cada nicho. Si hoy has
            subido cosas fuera de la app, apúntalas aquí y se suman al total.
          </p>
          <Ajuste tipo="videos" etiqueta="Vídeos ya subidos hoy" datos={videos} />
          <Ajuste tipo="carruseles" etiqueta="Carruseles ya subidos hoy" datos={carruseles} />
        </div>
      )}
    </div>
  );
}

function Medidor({ etiqueta, datos }: { etiqueta: string; datos: CuotaTipo }) {
  const pct = Math.min(100, Math.round((datos.usados / Math.max(1, datos.tope)) * 100));
  // Ámbar ANTES del tope: el operador quiere frenar con margen, no al llegar.
  const color = datos.lleno
    ? "bg-red-500"
    : datos.avisar
      ? "bg-amber-500"
      : "bg-emerald-500";
  const texto = datos.lleno
    ? "text-red-500"
    : datos.avisar
      ? "text-amber-500"
      : "text-muted-foreground";

  return (
    <span className="flex min-w-0 flex-1 items-center gap-1.5">
      <span className={`shrink-0 text-[10px] font-medium ${texto}`}>
        {etiqueta} {datos.usados}/{datos.tope}
      </span>
      <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
        <span
          className={`block h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </span>
    </span>
  );
}

function Ajuste({
  tipo,
  etiqueta,
  datos,
}: {
  tipo: "videos" | "carruseles";
  etiqueta: string;
  datos: CuotaTipo;
}) {
  const ajustar = useAjustarCuota();
  const [valor, setValor] = useState(String(datos.ajuste));

  return (
    <div className="flex items-center gap-2">
      <span className="min-w-0 flex-1 truncate text-[11px]">{etiqueta}</span>
      <input
        type="number"
        min={0}
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        className="w-16 rounded-md border border-border/60 bg-background px-2 py-1 text-xs"
      />
      <button
        type="button"
        disabled={ajustar.isPending}
        onClick={() =>
          ajustar.mutate(
            { tipo, valor: Number(valor) || 0 },
            {
              onSuccess: () => toast.success("Contador ajustado"),
              onError: (e) =>
                toast.error(e instanceof ApiError ? e.message : String(e)),
            },
          )
        }
        className="shrink-0 rounded-md border border-border/60 px-2 py-1 text-[11px] transition hover:border-foreground/40 disabled:opacity-50"
      >
        Guardar
      </button>
      <span className="shrink-0 text-[10px] text-muted-foreground">
        +{datos.marcados} marcados
      </span>
    </div>
  );
}
