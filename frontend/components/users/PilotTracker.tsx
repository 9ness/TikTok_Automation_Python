"use client";

import { Check, Clock, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { usePilotProgress } from "@/lib/queries/users";

export function PilotTracker({ username }: { username: string }) {
  const progress = usePilotProgress(username);

  if (progress.isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Pilot Program</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (progress.isError || !progress.data) {
    return null;
  }

  const p = progress.data;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Pilot Program</CardTitle>
        <Badge
          variant={
            p.graduation_status === "graduated"
              ? "default"
              : p.graduation_status === "eligible"
                ? "default"
                : "secondary"
          }
        >
          {labelFor(p.graduation_status)}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <Stat label="Días" value={p.days_in_program} />
          <Stat label="Followers" value={p.followers.toLocaleString()} />
          <Stat label="CHR" value={p.current_chr} />
          <Stat label="Órdenes" value={p.orders_count} />
        </div>

        {p.status === "pilot" && (
          <div className="rounded-md border bg-card/50 p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Shoppable esta semana</span>
              <span className="font-semibold">
                {p.weekly_shoppable_used}/5 usados
              </span>
            </div>
            <ProgressBar value={(p.weekly_shoppable_used / 5) * 100} />
            {p.weekly_reset_at && (
              <p className="mt-2 text-xs text-muted-foreground">
                Reset el {p.weekly_reset_at}
              </p>
            )}
          </div>
        )}

        {p.days_until_eligible !== null && p.days_until_eligible > 0 && (
          <div className="flex items-center gap-2 rounded-md border border-blue-500/30 bg-blue-500/10 p-3 text-sm">
            <Clock className="h-4 w-4 text-blue-600" />
            <span>
              {p.days_until_eligible} días hasta poder graduarse (todo lo demás OK).
            </span>
          </div>
        )}

        <div className="space-y-2">
          <p className="text-sm font-semibold">Vías de graduación</p>
          {p.requirements_met.map((req) => (
            <div
              key={req.name}
              className={cn(
                "rounded-md border p-3",
                req.met
                  ? "border-green-500/40 bg-green-500/5"
                  : "border-border bg-card/40",
              )}
            >
              <div className="flex items-start gap-2">
                {req.met ? (
                  <Check className="mt-0.5 h-4 w-4 text-green-600" />
                ) : (
                  <X className="mt-0.5 h-4 w-4 text-muted-foreground" />
                )}
                <div className="flex-1 text-sm">
                  <p className="font-medium">{req.label}</p>
                  {!req.met && req.missing.length > 0 && (
                    <ul className="mt-1 list-disc pl-4 text-xs text-muted-foreground">
                      {req.missing.map((m, i) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function labelFor(status: string): string {
  if (status === "graduated") return "Graduado";
  if (status === "eligible") return "Elegible para graduar";
  return "Pilot";
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-secondary">
      <div
        className="h-full bg-primary transition-all"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
