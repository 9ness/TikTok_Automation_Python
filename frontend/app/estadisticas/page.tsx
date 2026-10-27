"use client";

import { BarChart3, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useMe } from "@/lib/queries/auth";
import {
  type DiaStats,
  type MesStats,
  type ProductoMes,
  useEstadisticas,
} from "@/lib/queries/estadisticas";

/** Solo Néstor: son las ventas de su cuenta. El backend lo corta también. */
const USUARIOS = ["ness"];

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const eur = (n: number) =>
  n.toLocaleString("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: n >= 100 ? 0 : 2 });
const num = (n: number) => n.toLocaleString("es-ES", { maximumFractionDigits: 0 });
const pct = (n: number) => `${(n * 100).toLocaleString("es-ES", { maximumFractionDigits: 2 })} %`;
const nombreMes = (m: string) => `${MESES[Number(m.slice(5, 7)) - 1]} ${m.slice(2, 4)}`;
const fecha = (f?: string) => (f ? f.split("-").reverse().join("/") : "—");

/** Correlación de Pearson (−1…1). Con menos de 3 puntos no dice nada. */
function correlacion(xs: number[], ys: number[]): number | null {
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  xs.forEach((x, i) => {
    const y = ys[i] ?? 0;
    sxy += (x - mx) * (y - my);
    sxx += (x - mx) ** 2;
    syy += (y - my) ** 2;
  });
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
}

function Dato({ label, valor, sub }: { label: string; valor: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card p-3">
      <p className="text-[11px] text-muted-foreground sm:text-xs">{label}</p>
      <p className="text-lg font-bold sm:text-xl">{valor}</p>
      {sub ? <p className="text-[11px] text-muted-foreground">{sub}</p> : null}
    </div>
  );
}

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2 rounded-lg border border-border/60 bg-card/50 p-3 sm:p-4">
      <h2 className="text-sm font-semibold sm:text-base">{titulo}</h2>
      {children}
    </section>
  );
}

export default function EstadisticasPage() {
  const me = useMe();
  const permitido = USUARIOS.includes(me.data?.username ?? "");
  const q = useEstadisticas(permitido);
  const [mesProductos, setMesProductos] = useState<string>("todos");

  const meses: MesStats[] = useMemo(() => q.data?.meses ?? [], [q.data]);
  const dias: DiaStats[] = useMemo(() => q.data?.dias ?? [], [q.data]);

  const filas = meses.map((m) => ({
    ...m,
    etiqueta: nombreMes(m.mes),
    ctr: m.impresiones ? m.clics / m.impresiones : 0,
    conv: m.clics ? m.ventas / m.clics : 0,
    ticket: m.ventas ? m.gmv / m.ventas : 0,
    eurClic: m.clics ? m.gmv / m.clics : 0,
  }));

  // Ventas por cada 100 clics de los tres últimos meses: la base de la previsión.
  const ultimos = filas.slice(-3);
  const clics3 = ultimos.reduce((a, m) => a + m.clics, 0);
  const conv3 = clics3 ? ultimos.reduce((a, m) => a + m.ventas, 0) / clics3 : 0;
  const ticket3 = (() => {
    const v = ultimos.reduce((a, m) => a + m.ventas, 0);
    return v ? ultimos.reduce((a, m) => a + m.gmv, 0) / v : 0;
  })();
  const corrMeses = correlacion(filas.map((m) => m.clics), filas.map((m) => m.ventas));
  const conClics = dias.filter((d) => d.clics != null && d.ventas != null);
  const corrDias = correlacion(conClics.map((d) => d.clics!), conClics.map((d) => d.ventas!));
  const conVisitas = dias.filter((d) => d.impresiones != null && d.clics != null);
  const corrVisitasClics = correlacion(conVisitas.map((d) => d.impresiones!), conVisitas.map((d) => d.clics!));
  const ult14 = conClics.slice(-14);
  const clicsDia = ult14.length ? ult14.reduce((a, d) => a + (d.clics ?? 0), 0) / ult14.length : 0;

  const productos = useMemo(() => {
    const por = new Map<string, ProductoMes & { meses: number }>();
    for (const m of meses) {
      if (mesProductos !== "todos" && m.mes !== mesProductos) continue;
      for (const p of m.productos ?? []) {
        const k = `${p.titulo}|${p.pais}`;
        const prev = por.get(k);
        por.set(k, prev
          ? { ...prev, gmv: prev.gmv + p.gmv, ventas: prev.ventas + p.ventas, meses: prev.meses + 1 }
          : { ...p, meses: 1 });
      }
    }
    return [...por.values()].sort((a, b) => b.gmv - a.gmv);
  }, [meses, mesProductos]);

  const tipos = useMemo(() => {
    const por = new Map<string, { gmv: number; ventas: number; n: number }>();
    for (const p of productos) {
      const t = p.tipo || "Otros";
      const prev = por.get(t) ?? { gmv: 0, ventas: 0, n: 0 };
      por.set(t, { gmv: prev.gmv + p.gmv, ventas: prev.ventas + p.ventas, n: prev.n + 1 });
    }
    return [...por.entries()].sort((a, b) => b[1].gmv - a[1].gmv);
  }, [productos]);
  const totalTipos = tipos.reduce((a, [, v]) => a + v.gmv, 0);

  const paises = useMemo(() => {
    const por = new Map<string, number>();
    for (const p of productos) por.set(p.pais, (por.get(p.pais) ?? 0) + p.gmv);
    return [...por.entries()].sort((a, b) => b[1] - a[1]);
  }, [productos]);

  const origenes = useMemo(() => {
    const tot = new Map<string, { pedidos: number; importe: number; comision: number; esImporte: number; noAptos: number }>();
    for (const m of meses) {
      for (const [k, v] of Object.entries(m.origen ?? {})) {
        const prev = tot.get(k) ?? { pedidos: 0, importe: 0, comision: 0, esImporte: 0, noAptos: 0 };
        tot.set(k, {
          pedidos: prev.pedidos + v.pedidos,
          importe: prev.importe + v.importe,
          comision: prev.comision + v.comision,
          esImporte: prev.esImporte + (v.es_importe ?? 0),
          noAptos: prev.noAptos + (v.no_aptos ?? 0),
        });
      }
    }
    return [...tot.entries()].sort((a, b) => b[1].importe - a[1].importe);
  }, [meses]);
  const totalOrigen = origenes.reduce((a, [, v]) => a + v.importe, 0);

  if (me.isLoading) return <Loader2 className="m-6 h-5 w-5 animate-spin" />;
  if (!permitido) {
    return <p className="p-6 text-sm text-muted-foreground">Esta pantalla solo está disponible para ness.</p>;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-3 sm:p-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-lg font-bold sm:text-2xl">
          <BarChart3 className="h-5 w-5" /> Estadísticas
        </h1>
        <p className="text-xs text-muted-foreground sm:text-sm">
          {q.data?.cuenta ? `Cuenta ${q.data.cuenta} · ` : ""}Última actualización:{" "}
          <span className="font-semibold text-foreground">{fecha(q.data?.actualizado)}</span>
        </p>
      </header>

      {q.isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
      {q.isError ? <p className="text-sm text-red-500">No se pudieron cargar las estadísticas.</p> : null}
      {!q.isLoading && !meses.length ? (
        <p className="text-sm text-muted-foreground">Aún no hay datos guardados.</p>
      ) : null}

      {filas.length ? (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Dato label="GMV total" valor={eur(filas.reduce((a, m) => a + m.gmv, 0))}
              sub={`${nombreMes(filas[0]?.mes ?? "")} – ${nombreMes(filas.at(-1)?.mes ?? "")}`} />
            <Dato label="Ventas" valor={num(filas.reduce((a, m) => a + m.ventas, 0))} />
            <Dato label="Comisión estimada" valor={eur(filas.reduce((a, m) => a + (m.comision ?? 0), 0))} />
            <Dato label="Ventas por 100 clics" valor={(conv3 * 100).toLocaleString("es-ES", { maximumFractionDigits: 2 })}
              sub="media últimos 3 meses" />
          </div>

          <Seccion titulo="Mes a mes">
            <div className="h-56 sm:h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={filas} margin={{ top: 5, right: 0, left: -15, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="etiqueta" fontSize={11} />
                  <YAxis yAxisId="e" fontSize={11} />
                  <YAxis yAxisId="c" orientation="right" fontSize={11} />
                  <Tooltip formatter={(v: number, n: string) => [n === "GMV €" ? eur(v) : num(v), n]} />
                  <Bar yAxisId="e" dataKey="gmv" name="GMV €" fill="hsl(var(--brand-cyan))" radius={[4, 4, 0, 0]} />
                  <Line yAxisId="c" dataKey="clics" name="Clics" stroke="#f59e0b" strokeWidth={2} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-right text-xs sm:text-sm">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="text-left">Mes</th><th>GMV</th><th>Ventas</th><th>Impresiones</th>
                    <th>Clics</th><th>CTR</th><th>Conversión</th><th>€/clic</th><th>Ticket</th><th>Comisión</th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((m) => (
                    <tr key={m.mes} className="border-t border-border/40">
                      <td className="text-left font-medium">{m.etiqueta}</td>
                      <td>{eur(m.gmv)}</td><td>{num(m.ventas)}</td><td>{num(m.impresiones)}</td>
                      <td>{num(m.clics)}</td><td>{pct(m.ctr)}</td><td>{pct(m.conv)}</td>
                      <td>{eur(m.eurClic)}</td><td>{eur(m.ticket)}</td>
                      <td>{m.comision != null ? eur(m.comision) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground sm:text-xs">
              CTR = clics / impresiones del producto. Conversión = ventas / clics. Ticket = GMV / venta.
            </p>
          </Seccion>

          <Seccion titulo="Clics → ventas (previsión)">
            <ul className="list-disc space-y-1 pl-4 text-xs sm:text-sm">
              <li>
                Cada <b>100 clics</b> dan unas <b>{(conv3 * 100).toLocaleString("es-ES", { maximumFractionDigits: 1 })} ventas</b>{" "}
                y unos <b>{eur(conv3 * 100 * ticket3)}</b> de GMV (media de los 3 últimos meses).
              </li>
              {corrMeses != null ? (
                <li>Correlación clics–ventas por mes: <b>{corrMeses.toFixed(2)}</b> (1 = van a la par).</li>
              ) : null}
              {corrDias != null ? (
                <li>Correlación clics–ventas por día: <b>{corrDias.toFixed(2)}</b>.</li>
              ) : null}
              {corrVisitasClics != null ? (
                <li>Correlación impresiones–clics por día: <b>{corrVisitasClics.toFixed(2)}</b>.</li>
              ) : null}
              {clicsDia ? (
                <li>
                  Al ritmo de los últimos {ult14.length} días ({num(clicsDia)} clics/día): unas{" "}
                  <b>{(clicsDia * 30 * conv3).toLocaleString("es-ES", { maximumFractionDigits: 0 })} ventas</b> y{" "}
                  <b>{eur(clicsDia * 30 * conv3 * ticket3)}</b> en 30 días.
                </li>
              ) : null}
            </ul>
          </Seccion>

          {dias.length ? (
            <Seccion titulo="Día a día">
              <div className="h-56 sm:h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={dias} margin={{ top: 5, right: 0, left: -15, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis dataKey="fecha" tickFormatter={(f: string) => `${f.slice(8)}/${f.slice(5, 7)}`} fontSize={10} />
                    <YAxis yAxisId="i" fontSize={10} />
                    <YAxis yAxisId="c" orientation="right" fontSize={10} />
                    <Tooltip labelFormatter={(f: string) => fecha(f)} />
                    <Bar yAxisId="c" dataKey="ventas" name="Ventas" fill="#10b981" />
                    <Line yAxisId="i" dataKey="impresiones" name="Impresiones" stroke="hsl(var(--brand-cyan))" dot={false} />
                    <Line yAxisId="c" dataKey="clics" name="Clics" stroke="#f59e0b" dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <p className="text-[11px] text-muted-foreground sm:text-xs">
                Impresiones (eje izquierdo) · clics y ventas (eje derecho).
              </p>
            </Seccion>
          ) : null}

          {origenes.length ? (
            <Seccion titulo="De dónde vienen las ventas">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {origenes.map(([k, v]) => (
                  <Dato key={k} label={k} valor={eur(v.importe)}
                    sub={`${num(v.pedidos)} pedidos · ${totalOrigen ? pct(v.importe / totalOrigen) : "—"} · España ${v.importe ? pct(v.esImporte / v.importe) : "—"}${v.noAptos ? ` · ${num(v.noAptos)} no aptos` : ""}`} />
                ))}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-right text-xs sm:text-sm">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="text-left">Mes</th>
                      {origenes.map(([k]) => <th key={k}>{k}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {meses.filter((m) => m.origen).map((m) => (
                      <tr key={m.mes} className="border-t border-border/40">
                        <td className="text-left font-medium">{nombreMes(m.mes)}</td>
                        {origenes.map(([k]) => {
                          const v = m.origen?.[k];
                          return <td key={k}>{v ? <>{eur(v.importe)} <span className="text-muted-foreground">({v.pedidos})</span></> : "—"}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[11px] text-muted-foreground sm:text-xs">
                Pedidos de afiliados{q.data?.rango_pedidos ? ` (${q.data.rango_pedidos})` : ""}: importe pagado y, entre
                paréntesis, pedidos. Los «No apto» (pago fallido, devolución) no suman. Una venta cuenta en el mes del pedido aunque el vídeo sea de antes.
              </p>
              {q.data?.contenidos?.length ? (
                <>
                  <p className="pt-1 text-xs font-semibold">Vídeos y carruseles que más venden</p>
                  <ol className="space-y-1">
                    {q.data.contenidos.slice(0, 25).map((c, i) => (
                      <li key={`${c.tipo}|${c.caption}`} className="flex items-start gap-2 border-t border-border/40 pt-1 text-xs sm:text-sm">
                        <span className="w-5 shrink-0 text-muted-foreground">{i + 1}</span>
                        <span className="min-w-0 flex-1 break-words">
                          <span className={`mr-1 rounded px-1 text-[10px] ${c.tipo === "Carrusel" ? "bg-fuchsia-500/15 text-fuchsia-600" : "bg-sky-500/15 text-sky-600"}`}>{c.tipo}</span>
                          {c.caption || "(sin texto)"}
                        </span>
                        <span className="shrink-0 text-right font-medium">
                          {eur(c.importe)}<br /><span className="text-muted-foreground">{c.pedidos} ped.</span>
                        </span>
                      </li>
                    ))}
                  </ol>
                </>
              ) : null}
            </Seccion>
          ) : null}

          <Seccion titulo="Productos que más venden">
            <div className="flex flex-wrap gap-1">
              {["todos", ...meses.map((m) => m.mes)].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMesProductos(m)}
                  className={`rounded-md border px-2 py-1 text-xs ${mesProductos === m ? "border-violet-500 bg-violet-500/15" : "border-border/60"}`}
                >
                  {m === "todos" ? "Todos" : nombreMes(m)}
                </button>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <p className="text-xs font-semibold">Por tipo</p>
                {tipos.map(([t, v]) => (
                  <div key={t} className="text-xs sm:text-sm">
                    <div className="flex justify-between gap-2">
                      <span className="truncate">{t} <span className="text-muted-foreground">({v.ventas} ventas)</span></span>
                      <span className="font-medium">{eur(v.gmv)}</span>
                    </div>
                    <div className="h-1.5 rounded bg-muted">
                      <div className="h-1.5 rounded bg-violet-500" style={{ width: `${totalTipos ? (v.gmv / totalTipos) * 100 : 0}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold">Por país</p>
                {paises.map(([p, g]) => (
                  <div key={p} className="flex justify-between text-xs sm:text-sm">
                    <span>{p}</span><span className="font-medium">{eur(g)}</span>
                  </div>
                ))}
              </div>
            </div>
            <ol className="space-y-1">
              {productos.slice(0, 40).map((p, i) => (
                <li key={`${p.titulo}|${p.pais}`} className="flex items-start gap-2 border-t border-border/40 pt-1 text-xs sm:text-sm">
                  <span className="w-5 shrink-0 text-muted-foreground">{i + 1}</span>
                  <span className="min-w-0 flex-1 break-words">
                    {p.titulo}
                    <span className="ml-1 text-muted-foreground">· {p.pais}{p.tipo ? ` · ${p.tipo}` : ""}</span>
                  </span>
                  <span className="shrink-0 text-right font-medium">
                    {eur(p.gmv)}<br /><span className="text-muted-foreground">{p.ventas} v.</span>
                  </span>
                </li>
              ))}
            </ol>
          </Seccion>

          {q.data?.notas?.length ? (
            <Seccion titulo="Conclusiones">
              <ul className="list-disc space-y-1 pl-4 text-xs sm:text-sm">
                {q.data.notas.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </Seccion>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
