"use client";

import {
  AlertCircle,
  Boxes,
  DollarSign,
  Film,
  Loader2,
  Users,
} from "lucide-react";

import { AlertsPanel } from "@/components/dashboard/AlertsPanel";
import { BudgetCard } from "@/components/dashboard/BudgetCard";
import { CostByModuleChart } from "@/components/dashboard/CostByModuleChart";
import { DailyCostChart } from "@/components/dashboard/DailyCostChart";
import { KPICard } from "@/components/dashboard/KPICard";
import { PilotStatusList } from "@/components/dashboard/PilotStatusList";
import { RecentVideosGrid } from "@/components/dashboard/RecentVideosGrid";
import { Card, CardContent } from "@/components/ui/card";
import { useDashboardSummary } from "@/lib/queries/dashboard";
import { useMonthlyStats } from "@/lib/queries/stats";

export default function HomePage() {
  const summary = useDashboardSummary();
  const monthly = useMonthlyStats();

  const month = new Intl.DateTimeFormat("es-ES", {
    month: "long",
    year: "numeric",
  }).format(new Date());

  return (
    <div className="container mx-auto space-y-4 p-3 sm:space-y-6 sm:p-6 md:p-10">
      <header>
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Dashboard</h1>
        <p className="text-xs capitalize text-muted-foreground sm:text-sm">{month}</p>
      </header>

      {summary.isError && (
        <Card>
          <CardContent className="flex items-center gap-3 p-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <div>
              <p className="font-medium">Error cargando dashboard</p>
              <p className="text-sm text-muted-foreground">
                {summary.error?.message ?? "Sin detalles"}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* KPIs principales */}
      <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-5">
        <KPICard
          label="Usuarios"
          value={summary.data?.total_users ?? "—"}
          icon={Users}
          loading={summary.isLoading}
        />
        <KPICard
          label="Productos"
          value={summary.data?.total_products ?? "—"}
          icon={Boxes}
          loading={summary.isLoading}
        />
        <KPICard
          label="Vídeos este mes"
          value={summary.data?.total_videos_this_month ?? "—"}
          icon={Film}
          loading={summary.isLoading}
        />
        <KPICard
          label="Coste este mes"
          value={
            summary.data
              ? `$${summary.data.total_cost_this_month.toFixed(2)}`
              : "—"
          }
          icon={DollarSign}
          loading={summary.isLoading}
        />
        <KPICard
          label="Jobs activos"
          value={summary.data?.active_jobs_count ?? "—"}
          icon={Loader2}
          hint={
            summary.data
              ? `${summary.data.pending_jobs_count} pending · ${summary.data.running_jobs_count} running`
              : undefined
          }
          loading={summary.isLoading}
        />
      </div>

      {summary.data?.alerts && summary.data.alerts.length > 0 && (
        <AlertsPanel alerts={summary.data.alerts} />
      )}

      <div className="grid gap-3 sm:gap-4 md:grid-cols-2">
        <BudgetCard />
        <RecentVideosGrid videos={summary.data?.recent_videos ?? []} />
      </div>

      <div className="grid gap-3 sm:gap-4 md:grid-cols-2">
        <CostByModuleChart data={monthly.data?.cost_by_module ?? {}} />
        <DailyCostChart data={monthly.data?.daily_breakdown ?? []} />
      </div>

      <PilotStatusList users={summary.data?.pilot_users_summary ?? []} />
    </div>
  );
}
