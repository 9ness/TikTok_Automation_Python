"use client";

import Link from "next/link";
import { Boxes, Users as UsersIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { User } from "@/lib/types/user";

export function UserCard({ user }: { user: User }) {
  return (
    <Link
      href={`/tiktok-shop/users/${encodeURIComponent(user.username)}` as never}
      className="block"
    >
      <Card
        className={cn(
          "h-full transition-shadow hover:shadow-md",
          user.deleted && "opacity-50",
        )}
      >
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate font-semibold">{user.username}</h3>
              <p className="truncate text-xs text-muted-foreground">{user.display_name}</p>
            </div>
            <Badge variant={user.status === "graduated" ? "default" : "secondary"}>
              {user.status === "graduated" ? "Graduado" : "Pilot"}
            </Badge>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{user.niche}</span>
            <span>·</span>
            <span>
              {user.language}/{user.country}
            </span>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-1">
              <UsersIcon className="h-3 w-3" />
              {user.followers_count.toLocaleString()} followers
            </span>
            <span className="flex items-center gap-1">
              <Boxes className="h-3 w-3" />
              {user.assigned_products.length} productos
            </span>
          </div>

          {user.status === "pilot" && (
            <div className="text-xs text-muted-foreground">
              Shoppable esta semana: {user.pilot_program.weekly_shoppable_remaining}/5
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
