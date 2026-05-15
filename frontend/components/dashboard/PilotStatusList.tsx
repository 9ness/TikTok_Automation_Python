"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PilotUserSummary } from "@/lib/types/dashboard";

export function PilotStatusList({ users }: { users: PilotUserSummary[] }) {
  return (
    <Card>
      <CardHeader className="pb-2 sm:pb-4">
        <CardTitle className="text-base sm:text-lg">Pilot Program</CardTitle>
      </CardHeader>
      <CardContent>
        {users.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay usuarios.</p>
        ) : (
          <ul className="space-y-1.5 sm:space-y-2">
            {users.map((u) => (
              <li
                key={u.username}
                className="flex items-center justify-between gap-2 rounded-md border bg-card/50 p-1.5 sm:p-2"
              >
                <Link
                  href={`/tiktok-shop/users/${encodeURIComponent(u.username)}` as never}
                  className="min-w-0 flex-1"
                >
                  <p className="truncate text-sm font-medium">{u.username}</p>
                  <p className="truncate text-[10px] text-muted-foreground sm:text-xs">
                    {u.days_in_program}d · {u.shoppable_videos_published} shoppable ·{" "}
                    {u.weekly_shoppable_remaining}/5 esta sem.
                  </p>
                </Link>
                {u.status === "graduated" ? (
                  <Badge className="shrink-0 text-[10px] sm:text-xs">Graduado</Badge>
                ) : u.graduation_eligible ? (
                  <Badge variant="default" className="shrink-0 text-[10px] sm:text-xs">
                    Elegible
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="shrink-0 text-[10px] sm:text-xs">
                    Pilot
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
