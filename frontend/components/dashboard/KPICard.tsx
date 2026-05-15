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
      <CardContent className="p-2.5 sm:p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-0.5 sm:space-y-1">
            <p className="truncate text-[10px] uppercase tracking-wider text-muted-foreground sm:text-xs">
              {label}
            </p>
            {loading ? (
              <Skeleton className="h-6 w-16 sm:h-7 sm:w-20" />
            ) : (
              <p className="text-lg font-semibold tabular-nums sm:text-2xl">{value}</p>
            )}
            {hint && (
              <p className="truncate text-[10px] text-muted-foreground sm:text-xs">
                {hint}
              </p>
            )}
          </div>
          <div
            className={cn(
              "shrink-0 rounded-md p-1.5 sm:p-2",
              accent === "warning" && "bg-amber-500/10 text-amber-600",
              accent === "destructive" && "bg-destructive/10 text-destructive",
              accent === "success" && "bg-green-500/10 text-green-600",
              (!accent || accent === "default") && "bg-secondary text-foreground/70",
            )}
          >
            <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
