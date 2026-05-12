"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type {
  PrefixWord,
  PresidentsItem,
  TopCount,
} from "@/lib/types/creator-reward";

const MAX_ITEMS = 10;

const emptyItem = (): PresidentsItem => ({
  topic: "",
  prefix: "The",
  top_count: 5,
  include_history: true,
  include_hook: true,
});

export function PresidentsBatchEditor({
  items,
  onChange,
}: {
  items: PresidentsItem[];
  onChange: (next: PresidentsItem[]) => void;
}) {
  const [active, setActive] = useState(0);

  // Clamp active si el array encoge
  const activeIdx = Math.min(active, Math.max(0, items.length - 1));
  const current = items[activeIdx];

  function patch(partial: Partial<PresidentsItem>) {
    onChange(items.map((it, i) => (i === activeIdx ? { ...it, ...partial } : it)));
  }
  function remove() {
    if (items.length <= 1) return;
    onChange(items.filter((_, i) => i !== activeIdx));
    if (activeIdx >= items.length - 1) setActive(Math.max(0, items.length - 2));
  }
  function add() {
    if (items.length >= MAX_ITEMS) return;
    onChange([...items, emptyItem()]);
    setActive(items.length); // foco al nuevo
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">Vídeos a generar ({items.length})</h3>
        <Button
          size="sm"
          variant="outline"
          onClick={add}
          disabled={items.length >= MAX_ITEMS}
        >
          <Plus className="h-4 w-4" /> Añadir vídeo
        </Button>

        {items.length > 1 && (
          <div className="ml-2 flex flex-wrap items-center gap-1">
            {items.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setActive(i)}
                aria-label={`Vídeo ${i + 1}`}
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold transition-colors",
                  i === activeIdx
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground",
                )}
              >
                {i + 1}
              </button>
            ))}
          </div>
        )}
      </div>

      {current && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center justify-between">
              <span className="font-medium">🎬 Vídeo {activeIdx + 1}</span>
              <Button
                size="icon"
                variant="ghost"
                onClick={remove}
                aria-label={`Quitar vídeo ${activeIdx + 1}`}
                disabled={items.length <= 1}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Top</Label>
                <Select
                  value={String(current.top_count)}
                  onValueChange={(v) => patch({ top_count: Number(v) as TopCount })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[5, 4, 3].map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Prefijo</Label>
                <Select
                  value={current.prefix}
                  onValueChange={(v) => patch({ prefix: v as PrefixWord })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="The">The</SelectItem>
                    <SelectItem value="Top">Top</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Tema (vacío = aleatorio)</Label>
              <Input
                value={current.topic ?? ""}
                onChange={(e) => patch({ topic: e.target.value })}
                placeholder="worst / corruption / richest…"
              />
            </div>

            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <label className="flex items-center gap-2">
                <Switch
                  checked={current.include_history}
                  onCheckedChange={(v) => patch({ include_history: v })}
                />
                Añadir &quot;in US history&quot;
              </label>
              <label className="flex items-center gap-2">
                <Switch
                  checked={current.include_hook}
                  onCheckedChange={(v) => patch({ include_hook: v })}
                />
                Incluir hook
              </label>
            </div>

            <p className="text-xs text-muted-foreground">
              📢 {current.prefix} {current.top_count}{" "}
              {current.topic?.trim() || "[tema aleatorio]"}
              {current.include_history && " in US history"}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export { emptyItem };
