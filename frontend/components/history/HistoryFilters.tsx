"use client";

import { Filter, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { GenerationStatusValue } from "@/lib/types/generation";

export interface HistoryFiltersValue {
  username: string;
  productId: string;
  status: GenerationStatusValue | "__all__";
}

const ALL = "__all__" as const;

const STATUSES: GenerationStatusValue[] = [
  "pending",
  "generating",
  "completed",
  "failed",
  "manual_pending",
  "manual_completed",
];

export function HistoryFilters({
  value,
  onChange,
  onReset,
}: {
  value: HistoryFiltersValue;
  onChange: (next: HistoryFiltersValue) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-md border bg-card/50 p-4">
      <Filter className="mb-2 h-4 w-4 text-muted-foreground" />
      <Field label="Usuario">
        <Input
          value={value.username}
          onChange={(e) => onChange({ ...value, username: e.target.value })}
          placeholder="@user"
          className="h-9 w-40"
        />
      </Field>
      <Field label="Product ID">
        <Input
          value={value.productId}
          onChange={(e) => onChange({ ...value, productId: e.target.value })}
          placeholder="abc123"
          className="h-9 w-40"
        />
      </Field>
      <Field label="Status">
        <Select
          value={value.status}
          onValueChange={(v) =>
            onChange({ ...value, status: v as HistoryFiltersValue["status"] })
          }
        >
          <SelectTrigger className="h-9 w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todos</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Button variant="ghost" size="sm" onClick={onReset}>
        <X className="h-4 w-4" /> Limpiar
      </Button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}
