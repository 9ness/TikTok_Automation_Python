"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PilotUserSummary } from "@/lib/types/dashboard";

export function PilotStatusList({ users }: { users: PilotUserSummary[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pilot Program</CardTitle>
      </CardHeader>
      <CardContent>
        {users.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay usuarios.</p>
        ) : (
          <ul className="space-y-2">
            {users.map((u) => (
              <li
                key={u.username}
                className="flex items-center justify-between gap-2 rounded-md border bg-card/50 p-2"
              >
                <Link
                  href={`/tiktok-shop/users/${encodeURIComponent(u.username)}` as never}
                  className="min-w-0 flex-1"
                >
                  <p className="truncate font-medium">{u.username}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {u.days_in_program}d · {u.shoppable_videos_published} shoppable ·{" "}
                    {u.weekly_shoppable_remaining}/5 esta sem.
                  </p>
                </Link>
                {u.status === "graduated" ? (
                  <Badge>Graduado</Badge>
                ) : u.graduation_eligible ? (
                  <Badge variant="default">Elegible</Badge>
                ) : (
                  <Badge variant="secondary">Pilot</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
