"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";

import { useCampanas, type Campana, type CampanasEstado } from "@/lib/queries/cuotas";

/** Alto de la franja plegada. El hueco de `layout.tsx` lo suma a la barra de
 *  cuota con la variable `--alto-campana`, para no tapar lo primero de cada
 *  pantalla cuando la franja está y no dejar un hueco cuando no. */
const ALTO = "22px";

// Clases enteras (no montadas con plantillas) para que Tailwind las vea.
const COLORES: Record<string, { chip: string; celda: string; texto: string }> = {
  rose: { chip: "bg-rose-500/15 text-rose-500", celda: "bg-rose-500/30", texto: "text-rose-500" },
  violet: { chip: "bg-violet-500/15 text-violet-400", celda: "bg-violet-500/30", texto: "text-violet-400" },
  red: { chip: "bg-red-500/20 text-red-500", celda: "bg-red-500/45", texto: "text-red-500" },
  sky: { chip: "bg-sky-500/15 text-sky-500", celda: "bg-sky-500/35", texto: "text-sky-500" },
  emerald: { chip: "bg-emerald-500/15 text-emerald-500", celda: "bg-emerald-500/30", texto: "text-emerald-500" },
  amber: { chip: "bg-amber-500/15 text-amber-500", celda: "bg-amber-500/30", texto: "text-amber-500" },
};

const fechaCorta = (iso: string) => {
  const [, m, d] = iso.split("-");
  return `${Number(d)}/${Number(m)}`;
};

const dias = (n: number) => `${n} día${n === 1 ? "" : "s"}`;

/** Black Friday y Navidad de TikTok Shop, en una línea debajo del contador.
 *
 *  Plegada dice lo que toca (la campaña en curso o cuánto falta para la
 *  próxima) y se pone ámbar con ⚠️ cuando entra en el aviso de preparación: el
 *  contenido de una campaña tiene que estar publicado ANTES de que empiece.
 *  Sin avisos emergentes, igual que la barra de cuota. Al tocarla se despliega
 *  la línea de tiempo entera. Las fechas vienen del servidor
 *  (`src/cuotas/campanas.py`), la misma fuente que leen los agentes.
 */
export function FranjaCampanas() {
  const q = useCampanas();
  const [abierta, setAbierta] = useState(false);
  const e = q.data;
  const visible = !!e?.visible;

  useEffect(() => {
    document.documentElement.style.setProperty("--alto-campana", visible ? ALTO : "0px");
    return () => {
      document.documentElement.style.setProperty("--alto-campana", "0px");
    };
  }, [visible]);

  if (!e || !visible) return null;
  const aviso = e.avisos.length > 0;

  return (
    <div className="border-b border-border/60 bg-background/95 px-3 backdrop-blur">
      <button
        type="button"
        onClick={() => setAbierta((v) => !v)}
        style={{ height: ALTO }}
        className={`flex w-full items-center gap-1.5 text-left text-[10px] ${
          aviso ? "font-medium text-amber-500" : "text-muted-foreground"
        }`}
        title="Calendario de campañas de TikTok Shop"
      >
        <span className="min-w-0 flex-1 truncate">
          {aviso && "⚠️ "}
          <Resumen e={e} />
        </span>
        <ChevronDown
          className={`h-3 w-3 shrink-0 transition-transform ${abierta ? "rotate-180" : ""}`}
        />
      </button>
      {abierta && <Detalle e={e} />}
    </div>
  );
}

function Resumen({ e }: { e: CampanasEstado }) {
  const { activa, proxima } = e;
  if (activa) {
    const hasta =
      activa.dias_restantes === 0 ? "último día" : `hasta el ${fechaCorta(activa.fin)}`;
    return (
      <>
        {activa.emoji} <b>{activa.nombre}</b> · {hasta}
        {proxima && ` · luego ${proxima.emoji} ${proxima.corto} en ${dias(proxima.dias_para)}`}
      </>
    );
  }
  if (proxima) {
    return (
      <>
        {proxima.emoji} <b>{proxima.corto}</b> en {dias(proxima.dias_para)} (
        {fechaCorta(proxima.inicio)})
        {e.avisos.length > 0 ? " · toca preparar contenido" : ""}
      </>
    );
  }
  return null;
}

function Detalle({ e }: { e: CampanasEstado }) {
  const porId = Object.fromEntries(e.campanas.map((c) => [c.id, c])) as Record<string, Campana>;
  return (
    <div className="mb-2 space-y-2 rounded-lg border border-border/60 bg-card p-2 text-[11px]">
      {e.avisos.length > 0 && (
        <ul className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-600 dark:text-amber-400">
          {e.avisos.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}

      {/* Línea de tiempo: una fila por semana (de miércoles a martes, como el
          calendario oficial), una casilla por día con el color de su campaña. */}
      <div className="space-y-1">
        {e.semanas.map((s) => (
          <div key={s.n} className="flex items-center gap-1">
            <span className="w-7 shrink-0 text-[9px] text-muted-foreground">S{s.n}</span>
            <div className="grid min-w-0 flex-1 grid-cols-8 gap-0.5">
              {s.dias.map((d) => {
                const c = d.campana ? porId[d.campana] : null;
                const esHoy = d.fecha === e.hoy;
                const pasado = d.fecha < e.hoy;
                return (
                  <div
                    key={d.fecha}
                    title={`${d.dia} ${fechaCorta(d.fecha)}${c ? ` · ${c.nombre}` : ""}`}
                    className={`rounded px-0.5 py-0.5 text-center leading-tight ${
                      c ? COLORES[c.color]?.celda ?? "bg-muted" : "bg-muted/40"
                    } ${esHoy ? "ring-2 ring-foreground" : ""} ${pasado ? "opacity-40" : ""}`}
                  >
                    <div className="text-[8px] text-foreground/70">{d.dia}</div>
                    <div className={`text-[9px] ${d.destacado ? "font-black" : "font-medium"}`}>
                      {fechaCorta(d.fecha)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Qué es cada campaña y qué contenido pide. */}
      <ul className="space-y-1">
        {e.campanas.map((c) => {
          const col = COLORES[c.color];
          const pasada = c.dias_restantes < 0;
          const ahora = c.dias_para <= 0 && !pasada;
          return (
            <li
              key={c.id}
              className={`rounded-md border px-2 py-1 ${
                ahora ? "border-foreground/50" : "border-border/60"
              } ${pasada ? "opacity-40" : ""}`}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${col?.chip ?? ""}`}>
                  {c.emoji} {c.nombre}
                </span>
                {c.nivel && (
                  <span className="rounded border border-border/60 px-1 text-[9px] font-bold">
                    Nivel {c.nivel}
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground">
                  {c.inicio === c.fin
                    ? fechaCorta(c.inicio)
                    : `${fechaCorta(c.inicio)} – ${fechaCorta(c.fin)}`}
                  {ahora ? " · AHORA" : !pasada ? ` · en ${dias(c.dias_para)}` : ""}
                </span>
              </div>
              <p className="mt-0.5 break-words text-[10px] text-muted-foreground">{c.consejo}</p>
            </li>
          );
        })}
      </ul>

      {e.eventos && e.eventos.length > 0 && (
        <ul className="flex flex-wrap gap-1">
          {e.eventos.map((ev) => (
            <li
              key={ev.fecha + ev.tipo}
              title={ev.consejo}
              className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
            >
              {ev.emoji} {ev.nombre} {fechaCorta(ev.fecha)} · {ev.nivel}
            </li>
          ))}
        </ul>
      )}

      <p className="break-words text-[10px] leading-relaxed text-muted-foreground">
        Prioridad de TikTok: SS &gt; S &gt; A &gt; B.
      </p>

      <p className="break-words text-[10px] leading-relaxed text-muted-foreground">
        ⚖️ {e.regla_promocion}
      </p>
    </div>
  );
}
