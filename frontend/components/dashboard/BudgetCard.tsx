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
        <CardHeader className="pb-2 sm:pb-4">
          <CardTitle className="text-base sm:text-lg">Presupuesto mensual</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-muted-foreground sm:text-sm">
          <p className="flex items-baseline justify-between gap-2">
            <span>Coste actual del mes:</span>
            <span className="text-lg font-semibold tabular-nums text-foreground sm:text-xl">
              ${b.current_month_cost.toFixed(2)}
            </span>
          </p>
          <p>
            Sin presupuesto configurado. Define{" "}
            <code className="rounded bg-muted px-1 font-mono text-[10px] sm:text-xs">
              TIKTOK_SHOP_MONTHLY_BUDGET_USD
            </code>{" "}
            en <code>.env</code>.
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
      <CardHeader className="flex flex-row items-center justify-between pb-2 sm:pb-4">
        <CardTitle className="text-base sm:text-lg">Presupuesto mensual</CardTitle>
        <Badge variant={badgeVariant(b.status)}>{labelFor(b.status)}</Badge>
      </CardHeader>
      <CardContent className="space-y-2 sm:space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-xl font-semibold tabular-nums sm:text-2xl">
            ${b.current_month_cost.toFixed(2)}
          </span>
          <span className="text-xs text-muted-foreground sm:text-sm">
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
