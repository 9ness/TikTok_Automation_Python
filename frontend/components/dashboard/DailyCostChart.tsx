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
      <CardHeader className="pb-2 sm:pb-4">
        <CardTitle className="text-base sm:text-lg">Coste diario del mes</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground sm:py-12">
            Sin datos para este mes.
          </p>
        ) : (
          <div className="h-44 sm:h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 5, right: 8, left: -10, bottom: 0 }}>
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
