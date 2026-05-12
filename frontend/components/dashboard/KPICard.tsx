"use client";

import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function KPICard({
  label,
  value,
  icon: Icon,
  hint,
  loading,
  accent,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  loading?: boolean;
  accent?: "default" | "warning" | "destructive" | "success";
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              {label}
            </p>
            {loading ? (
              <Skeleton className="h-7 w-20" />
            ) : (
              <p className="text-2xl font-semibold tabular-nums">{value}</p>
            )}
            {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
          </div>
          <div
            className={cn(
              "rounded-md p-2",
              accent === "warning" && "bg-amber-500/10 text-amber-600",
              accent === "destructive" && "bg-destructive/10 text-destructive",
              accent === "success" && "bg-green-500/10 text-green-600",
              (!accent || accent === "default") && "bg-secondary text-foreground/70",
            )}
          >
            <Icon className="h-4 w-4" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
