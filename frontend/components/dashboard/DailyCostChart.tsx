"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DailyCostPoint } from "@/lib/types/stats";

export function DailyCostChart({ data }: { data: DailyCostPoint[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Coste diario del mes</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            Sin datos para este mes.
          </p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(d) => d.slice(8)}
                  fontSize={11}
                />
                <YAxis
                  fontSize={11}
                  tickFormatter={(v) => `$${v}`}
                />
                <Tooltip
                  formatter={(v: number) => [`$${v.toFixed(3)}`, "Coste"]}
                  labelFormatter={(label) => `Día ${label}`}
                />
                <Bar dataKey="cost" fill="hsl(var(--brand-cyan))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
