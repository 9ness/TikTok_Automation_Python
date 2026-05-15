"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Paleta de marca: cyan + violet (gradient) y dos auxiliares en armonía.
const COLORS = [
  "hsl(var(--brand-cyan))",
  "hsl(var(--brand-violet))",
  "hsl(var(--brand-glow))",
  "hsl(var(--muted-foreground))",
];

// Labels amigables — el backend devuelve los key del enum (`tiktok_shop`,
// `creator_reward`, `editor_auto`). Mapeamos a nombre humano + emoji.
const MODULE_LABELS: Record<string, string> = {
  tiktok_shop: "🛒 TikTok Shop",
  creator_reward: "🏆 Creator Reward",
  editor_auto: "✂️ Editor Auto",
};

function _label(key: string): string {
  return MODULE_LABELS[key] ?? key;
}

export function CostByModuleChart({
  data,
}: {
  data: Record<string, number>;
}) {
  const entries = Object.entries(data)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, label: _label(name), value }));
  const total = entries.reduce((acc, e) => acc + e.value, 0);

  return (
    <Card>
      <CardHeader className="pb-2 sm:pb-4">
        <CardTitle className="text-base sm:text-lg">Coste por módulo</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground sm:py-12">
            Sin coste registrado este mes.
          </p>
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            {/* Pie compacto a la izquierda en desktop, arriba en mobile */}
            <div
              className="h-40 w-full sm:h-48 sm:w-48"
              data-testid="cost-by-module-chart"
            >
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={entries}
                    dataKey="value"
                    nameKey="label"
                    cx="50%"
                    cy="50%"
                    innerRadius="50%"
                    outerRadius="90%"
                    paddingAngle={2}
                  >
                    {entries.map((_entry, idx) => (
                      <Cell
                        key={`cell-${idx}`}
                        fill={COLORS[idx % COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number) => [`$${v.toFixed(3)}`, "coste"]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* Leyenda con totales — siempre legible, sin solapar el pie */}
            <ul className="flex flex-1 flex-col gap-1.5 text-sm">
              {entries.map((e, idx) => {
                const pct = total > 0 ? (e.value / total) * 100 : 0;
                return (
                  <li
                    key={e.name}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span
                        aria-hidden
                        className="h-2.5 w-2.5 shrink-0 rounded-sm"
                        style={{ background: COLORS[idx % COLORS.length] }}
                      />
                      <span className="truncate">{e.label}</span>
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      ${e.value.toFixed(2)}
                      <span className="ml-1 text-[10px] opacity-60">
                        {pct.toFixed(0)}%
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
