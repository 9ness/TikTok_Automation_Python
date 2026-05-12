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

export function CostByModuleChart({
  data,
}: {
  data: Record<string, number>;
}) {
  const entries = Object.entries(data)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Coste por módulo</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            Sin coste registrado este mes.
          </p>
        ) : (
          <div className="h-64" data-testid="cost-by-module-chart">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={entries}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, value }) => `${name}: $${(value as number).toFixed(2)}`}
                >
                  {entries.map((_entry, idx) => (
                    <Cell
                      key={`cell-${idx}`}
                      fill={COLORS[idx % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => `$${v.toFixed(3)}`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
