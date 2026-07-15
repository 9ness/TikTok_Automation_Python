"use client";

/**
 * Estadísticas del mes + ranking de formatos.
 *
 * El ranking es la razón de ser de generar 3 versiones por producto: si no
 * sabes cuál vendió, hacer tres en vez de una solo cuesta el triple de
 * trabajo. Con esto, a las semanas se puede bajar a 1 vídeo por producto
 * SABIENDO cuál — que es lo que hace el operador de 100€/día.
 */

import type { MonthStats } from "@/lib/queries/calendar";

export function StatsRow({ stats }: { stats: MonthStats | undefined }) {
  const s = stats ?? {
    products: 0, uploaded: 0, sold: 0, revenue_eur: 0, conversion_pct: 0,
    by_format: {},
  };
  return (
    <div className="grid grid-cols-4 gap-2 rounded-xl border border-border/60 bg-card p-3 text-center">
      <Stat value={String(s.products)} label="productos" />
      <Stat value={String(s.uploaded)} label="subidos" tone="text-sky-500" />
      <Stat value={String(s.sold)} label="vendieron" tone="text-green-500" />
      <Stat
        value={s.revenue_eur ? `${s.revenue_eur.toFixed(0)}€` : "0€"}
        label={s.conversion_pct ? `${s.conversion_pct}% conv.` : "ingresos"}
        tone="text-purple-500"
      />
    </div>
  );
}

function Stat({ value, label, tone }: { value: string; label: string; tone?: string }) {
  return (
    <div>
      <p className={"text-lg font-bold leading-none " + (tone ?? "")}>{value}</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}

export function FormatRanking({ stats }: { stats: MonthStats | undefined }) {
  const by = stats?.by_format ?? {};
  const rows = Object.entries(by).sort((a, b) => b[1].sold - a[1].sold);
  const max = rows[0]?.[1].sold ?? 0;

  return (
    <div className="rounded-xl border border-border/60 bg-card p-3">
      <p className="text-xs font-semibold">🏆 Qué formato vende</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-[11px] text-muted-foreground">
          Aún sin datos. Marca qué versión vendió en cada producto y aquí verás
          cuál funciona — es lo que te dirá cuándo dejar de hacer 3 vídeos y
          hacer solo el que gana.
        </p>
      ) : (
        <div className="mt-2 space-y-1.5">
          {rows.map(([fmt, v]) => (
            <div key={fmt} className="flex items-center gap-2">
              <span className="w-40 shrink-0 truncate text-[11px]" title={fmt}>
                {fmt}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-green-500"
                  style={{ width: `${max ? (v.sold / max) * 100 : 0}%` }}
                />
              </div>
              <span className="w-8 shrink-0 text-right text-[11px] font-semibold text-green-500">
                {v.sold}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
