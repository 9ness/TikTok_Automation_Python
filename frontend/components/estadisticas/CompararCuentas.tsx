"use client";

import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { type MesStats, useEstadisticasCuentas } from "@/lib/queries/estadisticas";

/** Color fijo por cuenta (sigue a la cuenta aunque cambie el filtro). Validados
 *  para fondo claro y oscuro, y distinguibles con daltonismo. */
export const CUENTAS_COMPARAR = [
  { usuario: "ness", nombre: "Viva Shop", color: "#3987e5" },
  { usuario: "ana", nombre: "Ama Shop", color: "#d95926" },
  { usuario: "nestor2", nombre: "Casca Chollos", color: "#199e70" },
  { usuario: "nes_bugallo", nombre: "Cuenta árabe", color: "#c98500" },
];

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const nombreMes = (m: string) => `${MESES[Number(m.slice(5, 7)) - 1]} ${m.slice(2, 4)}`;
const eur = (n: number) =>
  n.toLocaleString("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: n >= 100 ? 0 : 2 });
const num = (n: number) => n.toLocaleString("es-ES", { maximumFractionDigits: 0 });
const pct = (n: number) => `${(n * 100).toLocaleString("es-ES", { maximumFractionDigits: 2 })} %`;

interface Suma {
  gmv: number;
  ventas: number;
  impresiones: number;
  clics: number;
  comision: number | null;
  meses: number;
}

function sumar(ms: MesStats[]): Suma {
  const conComision = ms.filter((m) => m.comision != null);
  return {
    gmv: ms.reduce((a, m) => a + m.gmv, 0),
    ventas: ms.reduce((a, m) => a + m.ventas, 0),
    impresiones: ms.reduce((a, m) => a + m.impresiones, 0),
    clics: ms.reduce((a, m) => a + m.clics, 0),
    comision: conComision.length ? conComision.reduce((a, m) => a + (m.comision ?? 0), 0) : null,
    meses: ms.length,
  };
}

const div = (a: number, b: number) => (b ? a / b : null);

/** Lo que se puede dibujar. Las tres últimas no dependen del tamaño de la cuenta:
 *  en euros Viva Shop aplasta a las demás, pero en conversión se comparan bien. */
const METRICAS: { id: string; nombre: string; valor: (s: Suma) => number | null; texto: (n: number) => string }[] = [
  { id: "gmv", nombre: "GMV", valor: (s) => s.gmv, texto: eur },
  { id: "ventas", nombre: "Ventas", valor: (s) => s.ventas, texto: num },
  { id: "comision", nombre: "Comisión", valor: (s) => s.comision, texto: eur },
  { id: "clics", nombre: "Clics", valor: (s) => s.clics, texto: num },
  { id: "conv", nombre: "Conversión", valor: (s) => div(s.ventas, s.clics), texto: pct },
  { id: "ticket", nombre: "Ticket medio", valor: (s) => div(s.gmv, s.ventas), texto: eur },
  { id: "eurClic", nombre: "€ por clic", valor: (s) => div(s.gmv, s.clics), texto: eur },
];

function Chip({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`shrink-0 rounded-md border px-2 py-1 text-xs sm:text-sm ${
        activo
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border/60 bg-card text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

/** Las cuentas de Néstor una al lado de otra: tabla del periodo y evolución por mes. */
export function CompararCuentas() {
  const qs = useEstadisticasCuentas(CUENTAS_COMPARAR.map((c) => c.usuario));
  const cargando = qs.some((q) => q.isLoading);
  const fallo = qs.some((q) => q.isError);
  const [periodo, setPeriodo] = useState<string | null>(null);
  const [metrica, setMetrica] = useState("gmv");

  const cuentas = useMemo(
    () => CUENTAS_COMPARAR.map((c, i) => ({ ...c, meses: qs[i]?.data?.meses ?? [] })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [qs.map((q) => q.dataUpdatedAt).join()],
  );
  const todosMeses = useMemo(
    () => [...new Set(cuentas.flatMap((c) => c.meses.map((m) => m.mes)))].sort(),
    [cuentas],
  );
  // Por defecto, el último mes en el que más cuentas tienen datos: comparar
  // un mes a medias con otro cerrado engaña.
  const porDefecto = useMemo(() => {
    let mejor = "todos";
    let n = 0;
    for (const mes of todosMeses) {
      const k = cuentas.filter((c) => c.meses.some((m) => m.mes === mes)).length;
      if (k >= n) {
        n = k;
        mejor = mes;
      }
    }
    return mejor;
  }, [cuentas, todosMeses]);
  const elegido = periodo ?? porDefecto;

  const filas = cuentas.map((c) => ({
    ...c,
    suma: sumar(elegido === "todos" ? c.meses : c.meses.filter((m) => m.mes === elegido)),
  }));

  const m = METRICAS.find((x) => x.id === metrica) ?? METRICAS[0]!;
  const serie = todosMeses.map((mes) => {
    const punto: Record<string, string | number | null> = { etiqueta: nombreMes(mes) };
    for (const c of cuentas) {
      const delMes = c.meses.filter((x) => x.mes === mes);
      punto[c.nombre] = delMes.length ? m.valor(sumar(delMes)) : null;
    }
    return punto;
  });
  const conDatos = cuentas.filter((c) => c.meses.length);
  const sinDatos = cuentas.filter((c) => !c.meses.length);

  if (cargando) return <Loader2 className="h-5 w-5 animate-spin" />;
  if (fallo) return <p className="text-sm text-red-500">No se pudieron cargar todas las cuentas.</p>;

  const celda = (n: number | null, f: (x: number) => string) => (n == null ? "—" : f(n));

  return (
    <div className="space-y-4">
      <section className="space-y-2 rounded-lg border border-border/60 bg-card/50 p-3 sm:p-4">
        <h2 className="text-sm font-semibold sm:text-base">Las cuentas, una al lado de otra</h2>
        <div className="flex gap-1 overflow-x-auto pb-1 sm:flex-wrap">
          <Chip activo={elegido === "todos"} onClick={() => setPeriodo("todos")}>Todo</Chip>
          {[...todosMeses].reverse().map((mes) => (
            <Chip key={mes} activo={elegido === mes} onClick={() => setPeriodo(mes)}>{nombreMes(mes)}</Chip>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-xs sm:text-sm">
            <thead>
              <tr className="border-b border-border/60 text-left text-muted-foreground">
                <th className="sticky left-0 bg-card py-1.5 pr-2 font-medium">Cuenta</th>
                {["GMV", "Ventas", "Comisión", "Impresiones", "Clics", "Conversión", "Ticket", "€/clic"].map((t) => (
                  <th key={t} className="px-2 py-1.5 text-right font-medium">{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.usuario} className="border-b border-border/30">
                  <td className="sticky left-0 whitespace-nowrap bg-card py-1.5 pr-2 font-medium">
                    <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: f.color }} />
                    {f.nombre}
                    {elegido === "todos" && f.suma.meses ? (
                      <span className="ml-1 text-[11px] font-normal text-muted-foreground">({f.suma.meses} m)</span>
                    ) : null}
                  </td>
                  {f.suma.meses ? (
                    <>
                      <td className="px-2 py-1.5 text-right font-semibold">{eur(f.suma.gmv)}</td>
                      <td className="px-2 py-1.5 text-right">{num(f.suma.ventas)}</td>
                      <td className="px-2 py-1.5 text-right">{celda(f.suma.comision, eur)}</td>
                      <td className="px-2 py-1.5 text-right">{num(f.suma.impresiones)}</td>
                      <td className="px-2 py-1.5 text-right">{num(f.suma.clics)}</td>
                      <td className="px-2 py-1.5 text-right">{celda(div(f.suma.ventas, f.suma.clics), pct)}</td>
                      <td className="px-2 py-1.5 text-right">{celda(div(f.suma.gmv, f.suma.ventas), eur)}</td>
                      <td className="px-2 py-1.5 text-right">{celda(div(f.suma.gmv, f.suma.clics), eur)}</td>
                    </>
                  ) : (
                    <td colSpan={8} className="px-2 py-1.5 text-muted-foreground">
                      {f.meses.length ? "Sin datos de este mes" : "Aún no hay datos guardados"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {elegido === "todos" ? (
          <p className="text-[11px] text-muted-foreground sm:text-xs">
            «Todo» suma lo que tenga cada cuenta, y no llevan los mismos meses: para comparar, mejor un mes concreto.
          </p>
        ) : null}
      </section>

      {conDatos.length ? (
        <section className="space-y-2 rounded-lg border border-border/60 bg-card/50 p-3 sm:p-4">
          <h2 className="text-sm font-semibold sm:text-base">Evolución por mes · {m.nombre}</h2>
          <div className="flex gap-1 overflow-x-auto pb-1 sm:flex-wrap">
            {METRICAS.map((x) => (
              <Chip key={x.id} activo={metrica === x.id} onClick={() => setMetrica(x.id)}>{x.nombre}</Chip>
            ))}
          </div>
          <div className="h-64 w-full sm:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={serie} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeOpacity={0.5} />
                <XAxis dataKey="etiqueta" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis
                  tick={{ fontSize: 11 }}
                  width={56}
                  stroke="hsl(var(--muted-foreground))"
                  tickFormatter={(v: number) => m.texto(v)}
                />
                <Tooltip
                  formatter={(v: number) => m.texto(v)}
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "hsl(var(--foreground))" }}
                  itemStyle={{ color: "hsl(var(--foreground))" }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12 }}
                  formatter={(v: string) => <span className="text-foreground">{v}</span>}
                />
                {conDatos.map((c) => (
                  <Line
                    key={c.usuario}
                    type="linear"
                    dataKey={c.nombre}
                    stroke={c.color}
                    strokeWidth={2}
                    dot={{ r: 4, fill: c.color, strokeWidth: 0 }}
                    activeDot={{ r: 6 }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-muted-foreground sm:text-xs">
            En euros Viva Shop aplasta a las demás: Conversión, Ticket medio y € por clic comparan mejor. El mes en curso va incompleto.
            {sinDatos.length ? ` Sin datos: ${sinDatos.map((c) => c.nombre).join(", ")}.` : ""}
          </p>
        </section>
      ) : null}
    </div>
  );
}
