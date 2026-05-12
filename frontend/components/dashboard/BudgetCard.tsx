"use client";

import { TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBudgetStatus } from "@/lib/queries/stats";
import { cn } from "@/lib/utils";

export function BudgetCard() {
  const budget = useBudgetStatus();

  if (budget.isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Presupuesto mensual</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!budget.data) return null;
  const b = budget.data;

  if (b.status === "no_budget") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Presupuesto mensual</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          No hay presupuesto configurado. Define{" "}
          <code className="rounded bg-muted px-1 font-mono">
            TIKTOK_SHOP_MONTHLY_BUDGET_USD
          </code>{" "}
          en el .env del backend.
          <p className="mt-2">
            Coste actual del mes:{" "}
            <span className="font-semibold">${b.current_month_cost.toFixed(2)}</span>
          </p>
        </CardContent>
      </Card>
    );
  }

  const pct = Math.min(100, b.percent_used ?? 0);
  const overBy =
    b.status === "exceeded" && b.monthly_budget_usd
      ? b.current_month_cost - b.monthly_budget_usd
      : 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Presupuesto mensual</CardTitle>
        <Badge variant={badgeVariant(b.status)}>{labelFor(b.status)}</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-semibold tabular-nums">
            ${b.current_month_cost.toFixed(2)}
          </span>
          <span className="text-sm text-muted-foreground">
            / ${b.monthly_budget_usd?.toFixed(2)}
          </span>
        </div>

        <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
          <div
            className={cn(
              "h-full transition-all",
              b.status === "ok" && "bg-primary",
              b.status === "warning" && "bg-amber-500",
              b.status === "exceeded" && "bg-destructive",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {b.percent_used?.toFixed(0)}% usado · {b.days_remaining_in_month}{" "}
            días restantes
          </span>
          <span className="flex items-center gap-1">
            <TrendingUp className="h-3 w-3" />
            Proyección: ${b.projected_month_end_cost.toFixed(2)}
          </span>
        </div>

        {overBy > 0 && (
          <p className="text-xs text-destructive">
            Excedido en ${overBy.toFixed(2)}.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function badgeVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "exceeded") return "destructive";
  if (status === "warning") return "secondary";
  return "default";
}

function labelFor(status: string): string {
  if (status === "exceeded") return "Excedido";
  if (status === "warning") return "Cerca del límite";
  return "OK";
}
