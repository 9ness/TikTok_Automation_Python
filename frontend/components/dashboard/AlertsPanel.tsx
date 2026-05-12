"use client";

import { AlertTriangle, Info, XOctagon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { Alert as DashboardAlert, AlertSeverity } from "@/lib/types/dashboard";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES: Record<AlertSeverity, string> = {
  info: "border-blue-500/40 bg-blue-500/5 text-blue-700 dark:text-blue-300",
  warning: "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300",
  error: "border-destructive/40 bg-destructive/10 text-destructive",
};

export function AlertsPanel({ alerts }: { alerts: DashboardAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Alertas ({alerts.length})
        </h3>
        <ul className="space-y-2">
          {alerts.map((a, i) => (
            <li
              key={`${a.code}-${i}`}
              className={cn(
                "flex items-start gap-2 rounded-md border p-3 text-sm",
                SEVERITY_STYLES[a.severity],
              )}
            >
              {a.severity === "error" && <XOctagon className="mt-0.5 h-4 w-4" />}
              {a.severity === "warning" && (
                <AlertTriangle className="mt-0.5 h-4 w-4" />
              )}
              {a.severity === "info" && <Info className="mt-0.5 h-4 w-4" />}
              <div className="flex-1">
                <p className="font-medium">{a.message}</p>
                <p className="font-mono text-xs opacity-70">{a.code}</p>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
