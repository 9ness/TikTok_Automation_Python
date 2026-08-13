"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  useAjustarCuota,
  useCuotaHoy,
  useCuotaMes,
  type CuotaTipo,
} from "@/lib/queries/cuotas";

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
  const [verHistorial, setVerHistorial] = useState(false);
  // Sin avisos emergentes al cruzar el umbral: el color de la barra y el ⚠️
  // ya lo dicen, y saltaban en medio de lo que estuvieras haciendo.
  if (!cuota.data) return null;
  const { videos, carruseles } = cuota.data;

  return (
    <div className="border-b border-border/60 bg-background/95 px-3 py-1.5 backdrop-blur">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex h-5 w-full items-center gap-3 text-left"
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
          <button
            type="button"
            onClick={() => setVerHistorial((v) => !v)}
            className="w-full rounded-md border border-border/60 px-2 py-1 text-[11px] text-muted-foreground transition hover:text-foreground"
          >
            📅 {verHistorial ? "Ocultar historial" : "Historial del mes"}
          </button>
          {verHistorial && <Historial />}
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
        {datos.avisar && "⚠️ "}
        {etiqueta} {datos.usados}/{datos.tope}
        {datos.avisar && !datos.lleno && ` · quedan ${datos.tope - datos.usados}`}
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
      {/* Sin `min`: se admiten negativos. Poner -3 resta tres, que es la única
          forma de deshacer un marcado de más cuando ya no está marcado. */}
      <input
        type="number"
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

/** Calendario del mes: cuántos vídeos y carruseles se publicaron cada día.
 *
 *  El contador diario se reinicia a medianoche y hasta ahora lo de ayer se
 *  perdía de vista. Cada día guarda su propia clave en Redis, así que el
 *  historial ya estaba: solo faltaba enseñarlo.
 */
function Historial() {
  const [desfase, setDesfase] = useState(0);
  const mes = useMemo(() => {
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() + desfase);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  }, [desfase]);
  const datos = useCuotaMes(mes, true);
  const hoy = new Date().toISOString().slice(0, 10);
  // Cuántas casillas vacías van antes del día 1 para que caiga en su columna.
  const hueco = useMemo(() => {
    const primero = new Date(`${mes}-01T00:00:00`).getDay();
    return (primero + 6) % 7; // domingo (0) pasa a ser la última columna
  }, [mes]);

  return (
    <div className="space-y-1.5 rounded-md border border-border/60 p-2">
      <div className="flex items-center justify-between text-[11px]">
        <button
          type="button"
          onClick={() => setDesfase((d) => d - 1)}
          className="rounded px-1.5 text-muted-foreground transition hover:text-foreground"
        >
          ‹
        </button>
        <span className="font-semibold">{mes}</span>
        <button
          type="button"
          disabled={desfase >= 0}
          onClick={() => setDesfase((d) => Math.min(0, d + 1))}
          className="rounded px-1.5 text-muted-foreground transition hover:text-foreground disabled:opacity-30"
        >
          ›
        </button>
      </div>

      {datos.data && (
        <p className="text-[10px] text-muted-foreground">
          Total del mes: <b className="text-foreground">{datos.data.total.videos}</b> vídeos ·{" "}
          <b className="text-foreground">{datos.data.total.carruseles}</b> carruseles
        </p>
      )}

      {/* Calendario de verdad: una casilla por día y las columnas por día de
          la semana, para ver de un vistazo en qué días de la semana se publica
          y cuáles se quedaron en blanco. */}
      <div className="grid grid-cols-7 gap-0.5 text-center text-[9px] text-muted-foreground">
        {["L", "M", "X", "J", "V", "S", "D"].map((d, i) => (
          <span key={`${d}${i}`}>{d}</span>
        ))}
        {/* Huecos hasta que empieza el mes. La semana arranca en LUNES, que es
            como se mira aquí; `getDay()` devuelve 0 para el domingo. */}
        {Array.from({ length: hueco }).map((_, i) => (
          <span key={`h${i}`} />
        ))}
        {(datos.data?.dias ?? []).map((d) => {
          const algo = d.videos || d.carruseles;
          const esHoy = d.fecha === hoy;
          return (
            <div
              key={d.fecha}
              title={`${d.fecha}: ${d.videos} vídeos · ${d.carruseles} carruseles`}
              className={`rounded border p-0.5 leading-tight ${
                esHoy
                  ? "border-foreground/60"
                  : algo
                    ? "border-border/60"
                    : "border-transparent bg-muted/30"
              }`}
            >
              <div className={`text-[9px] ${esHoy ? "font-bold" : "text-muted-foreground"}`}>
                {Number(d.fecha.slice(8))}
              </div>
              {algo ? (
                <>
                  <div className="text-[9px] font-semibold text-emerald-500">{d.videos}</div>
                  <div className="text-[9px] font-semibold text-sky-500">{d.carruseles}</div>
                </>
              ) : (
                <div className="text-[9px] text-muted-foreground/40">·</div>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[9px] text-muted-foreground">
        <span className="text-emerald-500">verde</span> vídeos ·{" "}
        <span className="text-sky-500">azul</span> carruseles
      </p>
    </div>
  );
}
