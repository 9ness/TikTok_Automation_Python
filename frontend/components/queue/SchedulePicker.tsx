"use client";

import { useEffect, useMemo, useState } from "react";
import { Calendar, Clock, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** Devuelve fecha local con offset positivo `addMinutes` para usar
 *  como default en datetime-local. */
function addMinutesLocalISO(addMinutes: number): string {
  const d = new Date(Date.now() + addMinutes * 60 * 1000);
  // datetime-local quiere "YYYY-MM-DDTHH:mm" en hora LOCAL (sin Z)
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/** Convierte el input local del datetime-local a un ISO 8601 string
 *  con offset de zona horaria — lo que el backend espera. */
function localInputToIso(localInput: string): string {
  // localInput formato "2026-01-15T02:30" — JS interpreta como hora local.
  const d = new Date(localInput);
  return d.toISOString();
}

const QUICK_PRESETS: { label: string; minutes: number }[] = [
  { label: "+30 min", minutes: 30 },
  { label: "+1 h", minutes: 60 },
  { label: "+3 h", minutes: 180 },
  { label: "Esta noche 02:00", minutes: -1 },  // calculado especial abajo
  { label: "Mañana 03:00", minutes: -2 },
];

function nightTonight2am(): Date {
  // Si ya pasamos las 02:00 hoy, devuelve mañana 02:00 (caso de uso real).
  const now = new Date();
  const target = new Date(
    now.getFullYear(), now.getMonth(), now.getDate(), 2, 0, 0,
  );
  if (target.getTime() <= now.getTime()) {
    target.setDate(target.getDate() + 1);
  }
  return target;
}

function tomorrow3am(): Date {
  const now = new Date();
  const t = new Date(
    now.getFullYear(), now.getMonth(), now.getDate() + 1, 3, 0, 0,
  );
  // Si ya estamos pasada esa fecha, suma otro día.
  if (t.getTime() <= now.getTime()) t.setDate(t.getDate() + 1);
  return t;
}

function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/**
 * Picker compacto para programar la ejecución de un job. Pensado para
 * usarse junto a botones "Encolar" o como acción "Reprogramar" en una
 * card de la cola.
 *
 * Cuando el user pulsa Aplicar, llama `onConfirm(isoString | null)` y
 * cierra el dialog. `null` significa desprogramar (ejecutar inmediato).
 */
export function SchedulePicker({
  open,
  onOpenChange,
  onConfirm,
  initialScheduledFor,
  title = "Programar ejecución",
  description,
  confirmLabel = "Programar",
  busy = false,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onConfirm: (isoString: string | null) => void;
  /** ISO 8601 o unix timestamp para pre-rellenar (al reprogramar) */
  initialScheduledFor?: string | number | null;
  title?: string;
  description?: string;
  confirmLabel?: string;
  busy?: boolean;
}) {
  const [value, setValue] = useState<string>(() => addMinutesLocalISO(60));

  // Cuando se abre, reseteamos al valor inicial.
  useEffect(() => {
    if (!open) return;
    if (initialScheduledFor != null) {
      const d =
        typeof initialScheduledFor === "number"
          ? new Date(initialScheduledFor * 1000)
          : new Date(initialScheduledFor);
      if (!isNaN(d.getTime())) {
        setValue(toLocalInput(d));
        return;
      }
    }
    setValue(addMinutesLocalISO(60));
  }, [open, initialScheduledFor]);

  const minValue = useMemo(() => addMinutesLocalISO(2), []);

  function applyQuick(p: { label: string; minutes: number }): void {
    if (p.minutes > 0) {
      setValue(addMinutesLocalISO(p.minutes));
    } else if (p.minutes === -1) {
      setValue(toLocalInput(nightTonight2am()));
    } else {
      setValue(toLocalInput(tomorrow3am()));
    }
  }

  function confirmNow(): void {
    if (!value) return;
    const d = new Date(value);
    if (isNaN(d.getTime())) return;
    if (d.getTime() <= Date.now()) {
      // Si el user metió una fecha pasada, lo tratamos como inmediato.
      onConfirm(null);
    } else {
      onConfirm(d.toISOString());
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-1rem)] max-h-[92vh] max-w-md overflow-y-auto p-3 sm:p-4">
        <DialogHeader className="space-y-1">
          <DialogTitle className="flex items-center gap-2 text-sm sm:text-base">
            <Clock className="h-4 w-4 text-amber-500" />
            {title}
          </DialogTitle>
          {description && (
            <DialogDescription className="text-[11px] sm:text-xs">
              {description}
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <Label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground sm:text-[11px]">
              Atajos rápidos
            </Label>
            <div className="mt-1 grid grid-cols-2 gap-1.5 sm:flex sm:flex-wrap">
              {QUICK_PRESETS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => applyQuick(p)}
                  className="rounded border border-amber-500/40 bg-amber-500/5 px-2 py-1.5 text-[11px] hover:bg-amber-500/15 active:bg-amber-500/25 sm:py-1"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground sm:text-[11px]">
              <Calendar className="mr-1 inline h-3 w-3" />
              Fecha y hora exactas (hora local)
            </Label>
            <Input
              type="datetime-local"
              value={value}
              min={minValue}
              onChange={(e) => setValue(e.target.value)}
              className="mt-1 h-10 text-sm sm:h-9"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              Recomendado: 00-08h hora Spain (madrugada) para evitar cola
              global de modelos AI.
            </p>
          </div>
        </div>

        <DialogFooter className="flex-col gap-1.5 sm:flex-row sm:gap-2">
          {initialScheduledFor != null && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onConfirm(null)}
              disabled={busy}
              className="h-9 w-full text-xs sm:h-8 sm:w-auto"
            >
              <X className="h-3.5 w-3.5" />
              Desprogramar
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={busy}
            className="h-9 w-full text-xs sm:h-8 sm:w-auto"
          >
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={confirmNow}
            disabled={busy || !value}
            className={cn(
              "h-9 w-full gap-1 bg-amber-600 text-xs hover:bg-amber-700 sm:h-8 sm:w-auto",
              busy && "opacity-60",
            )}
          >
            <Clock className="h-3.5 w-3.5" />
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Formatea unix timestamp a "hoy 02:30" / "mañana 03:00" / "vie 15 ene 02:30". */
export function formatScheduledFor(unixSec: number): string {
  const d = new Date(unixSec * 1000);
  const now = new Date();
  const sameDay =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow =
    d.getDate() === tomorrow.getDate() &&
    d.getMonth() === tomorrow.getMonth() &&
    d.getFullYear() === tomorrow.getFullYear();
  const pad = (n: number) => String(n).padStart(2, "0");
  const hhmm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (sameDay) return `hoy ${hhmm}`;
  if (isTomorrow) return `mañana ${hhmm}`;
  return d.toLocaleDateString("es-ES", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }) + ` ${hhmm}`;
}
