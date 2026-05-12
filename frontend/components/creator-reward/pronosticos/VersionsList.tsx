"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Star } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { PronosticosVersionItem } from "@/lib/types/creator-reward";
import { cn } from "@/lib/utils";

export function VersionsList({
  versions,
  selectedIds,
  onToggle,
  scriptOverrides,
  onScriptChange,
}: {
  versions: PronosticosVersionItem[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  scriptOverrides: Record<string, string>;
  onScriptChange: (id: string, text: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (versions.length === 0) {
    return (
      <p className="rounded-md border bg-card/50 p-6 text-center text-sm text-muted-foreground">
        Sin versiones disponibles para esta fecha.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {versions.map((v) => {
        const isSelected = selectedIds.has(v.id);
        const isExpanded = expanded === v.id;
        const editedScript = scriptOverrides[v.id] ?? v.script;
        const wordCount = editedScript.trim().split(/\s+/).filter(Boolean).length;

        return (
          <li key={v.id}>
            <Card
              className={cn(
                "overflow-hidden transition-colors",
                isSelected && "border-primary bg-primary/5",
              )}
            >
              <div className="flex items-center gap-3 p-3">
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => onToggle(v.id)}
                  aria-label={`Seleccionar versión ${v.id}`}
                  className="h-4 w-4"
                />
                <button
                  type="button"
                  onClick={() => setExpanded(isExpanded ? null : v.id)}
                  className="flex flex-1 items-start gap-2 text-left"
                  aria-label={`Expandir versión ${v.id}`}
                >
                  {isExpanded ? (
                    <ChevronDown className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  ) : (
                    <ChevronRight className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">v{v.id}</span>
                      {v.is_selected && (
                        <Badge variant="default" className="gap-1">
                          <Star className="h-3 w-3" /> Selected
                        </Badge>
                      )}
                      {v.trigger && <Badge variant="outline">{v.trigger}</Badge>}
                      {v.mode && <Badge variant="secondary">{v.mode}</Badge>}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {v.word_count ?? wordCount} palabras ·{" "}
                      ~{v.estimated_duration_s?.toFixed(0) ?? "?"}s · {v.picks_count} picks
                      {v.competition_focus && ` · ${v.competition_focus}`}
                    </p>
                  </div>
                </button>
              </div>
              {isExpanded && (
                <CardContent className="space-y-2 border-t pt-3">
                  <p className="text-xs text-muted-foreground">
                    Editor de guion (efímero, no se guarda en Redis).
                  </p>
                  <Textarea
                    value={editedScript}
                    onChange={(e) => onScriptChange(v.id, e.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                  />
                  <p className="text-xs text-muted-foreground">
                    {wordCount} palabras{" "}
                    {editedScript.trim() !== v.script.trim() && "· ✏️ editado"}
                  </p>
                </CardContent>
              )}
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
