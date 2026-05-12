"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function CollapsibleCard({
  title,
  subtitle,
  defaultOpen = false,
  children,
  trailing,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  /** Slot a la derecha del header — ej. badge con resumen. */
  trailing?: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className={cn("overflow-hidden", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 p-3 text-left transition-colors hover:bg-accent/40"
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{title}</div>
            {subtitle && (
              <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
            )}
          </div>
        </div>
        {trailing && (
          <div
            className="shrink-0"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            {trailing}
          </div>
        )}
      </button>
      {open && <div className="border-t p-3">{children}</div>}
    </Card>
  );
}
