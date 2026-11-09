"use client";

import { BarChart3 } from "lucide-react";
import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEstadisticasEditor, useMargenEditor, useRecuperarClientes } from "@/lib/queries/editor-auto";

/**
 * Estadísticas del Editor Auto y de nebulabsmedia.com, guardadas en LOCAL
 * (SQLite del VPS, nada en Redis ni en servicios de pago):
 *  - embudo de la web (visitas sin cookies → registro → prueba → pago),
 *  - conversión prueba → pago de las altas de los últimos 90 días,
 *  - coste y tiempo por vídeo (dólares de IA y segundos de render),
 *  - una fila por cliente.
 */

const NOMBRE_PASO: Record<string, string> = {
  visita: "Visitas",
  precios: "Vieron precios",
  registro_visto: "Abrieron registro",
  registro: "Se registraron",
  prueba_empezada: "Empezaron la prueba",
  video_enviado: "Mandaron vídeos",
  video_listo: "Recibieron vídeo",
  descarga: "Descargaron",
  pago: "Pagaron",
};

const usd = (n: number | null | undefined) =>
  n == null ? "—" : `${n < 0.1 ? n.toFixed(3) : n.toFixed(2)} $`;
const seg = (s: number | null | undefined) =>
  s == null ? "—" : s < 90 ? `${Math.round(s)} s` : `${(s / 60).toFixed(1)} min`;

function hace(dias: number) {
  const d = new Date();
  d.setDate(d.getDate() - dias + 1);
  return d.toISOString().slice(0, 10);
}

const RANGOS = [
  { dias: 7, label: "7 días" },
  { dias: 30, label: "30 días" },
  { dias: 90, label: "90 días" },
];

const NOMBRE_REGLA: Record<string, string> = {
  sin_empezar: "Sin empezar",
  prueba_gastada: "Prueba gastada",
  plan_parado: "Plan parado",
};

function AvisosRecuperar() {
  const { data } = useRecuperarClientes();
  if (!data) return null;
  const enviados = Object.values(data.enviados ?? {}).reduce((a, b) => a + b, 0);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Avisos para recuperar clientes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs sm:text-sm">
        <p className={data.envio_activo ? "text-emerald-600" : "text-amber-600"}>
          {data.envio_activo
            ? "Envío ACTIVO: se mandan una vez al día (máx. 20)."
            : "Modo simulación: no se manda nada. Así quedaría hoy."}
          <span className="ml-1 text-muted-foreground">
            Enviados {enviados} · bajas {data.bajas ?? 0}
          </span>
        </p>
        {data.error && <p className="text-red-500">{data.error}</p>}
        {data.candidatos.length === 0 ? (
          <p className="text-muted-foreground">Nadie a quien avisar hoy.</p>
        ) : (
          data.candidatos.map((c) => (
            <div key={c.email + c.regla} className="flex items-baseline justify-between gap-2 border-t py-1 first:border-t-0">
              <span className="min-w-0 truncate">{c.usuario ?? c.email}</span>
              <span className="shrink-0 text-muted-foreground">
                {NOMBRE_REGLA[c.regla] ?? c.regla} · {c.motivo}
              </span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

const eur = (n: number | null | undefined) => (n == null ? "—" : `${n.toFixed(2)} €`);

function Margen({ desde }: { desde: string }) {
  const { data } = useMargenEditor(desde);
  if (!data) return null;
  const t = data.total;
  const color = (pct: number | null) =>
    pct == null ? "" : pct < 0 ? "text-red-500" : pct < data.supuestos.alerta_pct ? "text-amber-600" : "text-emerald-600";
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Margen</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs sm:text-sm">
        <p>
          Ingreso {eur(t.ingreso_eur)} · coste {eur(t.coste_eur)} ·{" "}
          <span className={`font-semibold ${color(t.margen_pct)}`}>
            margen {eur(t.margen_eur)}
            {t.margen_pct != null && ` (${t.margen_pct} %)`}
          </span>
        </p>
        {data.alertas.map((a) => (
          <p key={a} className="break-words text-amber-600">⚠ {a}</p>
        ))}
        {data.clientes.map((c) => (
          <div key={c.usuario} className="flex items-baseline justify-between gap-2 border-t py-1 first:border-t-0">
            <span className="min-w-0 truncate">
              {c.usuario} <span className="text-muted-foreground">· {c.plan}</span>
            </span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {c.videos} víd. · {eur(c.ingreso_eur)} − {eur(c.coste_eur)} ={" "}
              <span className={color(c.margen_pct)}>{eur(c.margen_eur)}</span>
            </span>
          </div>
        ))}
        {data.prueba.usuarios > 0 && (
          <p className="text-muted-foreground">
            Pruebas gratis: {data.prueba.usuarios} cuentas, {data.prueba.videos} vídeos, {eur(data.prueba.coste_eur)}
          </p>
        )}
        {data.otros.length > 0 && (
          <p className="text-muted-foreground">
            Sin cuenta web: {data.otros.length} usuarios, {eur(data.otros.reduce((s, o) => s + o.coste_eur, 0))}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Precio fundador prorrateado a los días pagados. Coste = IA ({data.supuestos.eur_por_usd} €/$) + render a{" "}
          {data.supuestos.eur_min_render} €/min (estimado).
        </p>
      </CardContent>
    </Card>
  );
}

function Cifra({ titulo, valor, nota }: { titulo: string; valor: string; nota?: string }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-xs text-muted-foreground">{titulo}</div>
      <div className="mt-1 text-lg font-semibold sm:text-xl">{valor}</div>
      {nota && <div className="mt-0.5 text-xs text-muted-foreground">{nota}</div>}
    </div>
  );
}

export default function EstadisticasEditorPage() {
  const [dias, setDias] = useState(30);
  const { data, isLoading, error } = useEstadisticasEditor(hace(dias));

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-6 w-6 text-sky-500" />
          <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Estadísticas del Editor</h1>
        </div>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Web, prueba gratis, pagos y lo que cuesta cada vídeo. Se guardan en el VPS (sin cookies
          ni servicios de pago). Empezaron a contarse el 9/11/2026.
        </p>
        <div className="flex flex-wrap gap-2">
          {RANGOS.map((r) => (
            <button
              key={r.dias}
              type="button"
              onClick={() => setDias(r.dias)}
              className={`rounded-md border px-3 py-1 text-xs sm:text-sm ${
                dias === r.dias ? "border-sky-500 bg-sky-500/10 text-sky-600" : "text-muted-foreground"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </header>

      {isLoading && <Skeleton className="h-64 w-full" />}
      {error && (
        <p className="text-sm text-red-500">No se pudieron leer las estadísticas: {String(error)}</p>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Cifra titulo="Vídeos editados" valor={String(data.coste.videos)}
              nota={data.coste.fallidos ? `${data.coste.fallidos} fallidos` : undefined} />
            <Cifra titulo="Coste por vídeo" valor={usd(data.coste.coste_medio_usd)}
              nota={`total ${usd(data.coste.coste_usd)}`} />
            <Cifra titulo="Tiempo por vídeo" valor={seg(data.coste.seg_medio)}
              nota={`máx. ${seg(data.coste.seg_max)}`} />
            <Cifra titulo="Prueba → pago" valor={data.conversion.pct_pago == null ? "—" : `${data.conversion.pct_pago} %`}
              nota={`${data.conversion.pago} de ${data.conversion.altas} altas (90 días)`} />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Embudo</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {(() => {
                const max = Math.max(1, ...data.embudo.map((p) => p.n));
                return data.embudo.map((p) => (
                  <div key={p.paso} className="space-y-1">
                    <div className="flex items-baseline justify-between gap-2 text-xs sm:text-sm">
                      <span className="truncate">{NOMBRE_PASO[p.paso] ?? p.paso}</span>
                      <span className="shrink-0 tabular-nums">
                        {p.n}
                        {p.desde_anterior != null && (
                          <span className="ml-2 text-muted-foreground">{p.desde_anterior} %</span>
                        )}
                      </span>
                    </div>
                    <div className="h-2 rounded bg-muted">
                      <div className="h-2 rounded bg-sky-500" style={{ width: `${(100 * p.n) / max}%` }} />
                    </div>
                  </div>
                ));
              })()}
              <p className="pt-1 text-xs text-muted-foreground">
                Visitas = personas distintas por día. El resto, cuentas distintas. El % es respecto al
                paso anterior con datos.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Clientes</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              {data.clientes.length === 0 ? (
                <p className="text-sm text-muted-foreground">Aún no hay cuentas apuntadas (se leen cada 2 h).</p>
              ) : (
                <table className="w-full min-w-[560px] text-xs sm:text-sm">
                  <thead className="text-left text-muted-foreground">
                    <tr>
                      <th className="py-1 pr-2">Cliente</th>
                      <th className="py-1 pr-2">Alta</th>
                      <th className="py-1 pr-2">Plan</th>
                      <th className="py-1 pr-2 text-right">Vídeos</th>
                      <th className="py-1 pr-2 text-right">€/vídeo IA</th>
                      <th className="py-1 pr-2 text-right">Tiempo</th>
                      <th className="py-1 text-right">Último</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.clientes.map((c) => (
                      <tr key={c.cuenta} className="border-t">
                        <td className="max-w-[140px] truncate py-1 pr-2">{c.usuario ?? "(sin vincular)"}</td>
                        <td className="py-1 pr-2">{c.alta ?? "—"}</td>
                        <td className="py-1 pr-2">
                          {c.rol === "admin" ? "admin" : c.plan ?? (
                            <span className="text-amber-600">prueba · {c.prueba_restante ?? 0}</span>
                          )}
                        </td>
                        <td className="py-1 pr-2 text-right tabular-nums">{c.videos}</td>
                        <td className="py-1 pr-2 text-right tabular-nums">{usd(c.coste_por_video)}</td>
                        <td className="py-1 pr-2 text-right tabular-nums">{seg(c.seg_medio)}</td>
                        <td className="py-1 text-right">{c.ultimo_video ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          <Margen desde={hace(dias)} />

          <AvisosRecuperar />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Coste según herramientas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs sm:text-sm">
              {data.coste.por_herramientas.length === 0 && (
                <p className="text-muted-foreground">Sin vídeos en este rango.</p>
              )}
              {data.coste.por_herramientas.map((h) => (
                <div key={h.herramientas} className="flex items-baseline justify-between gap-2 border-t py-1 first:border-t-0">
                  <span className="break-words">{h.herramientas}</span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {h.videos} · {usd(h.coste_medio_usd)} · {seg(h.seg_medio)}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
