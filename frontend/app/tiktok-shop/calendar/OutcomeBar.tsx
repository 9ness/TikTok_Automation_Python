"use client";

/**
 * Marcar qué pasó con un producto: subido / vendió / QUÉ versión vendió.
 *
 * Lo de "qué versión" no es un adorno: es lo único que convierte 3 vídeos al
 * día en aprendizaje. Sin esto, generar 3 versiones cuesta el triple y no
 * enseña nada.
 *
 * El estado se lleva en local además de en el servidor para que el clic se
 * sienta instantáneo (el refetch del día tarda) — mismo patrón que el
 * checkbox "probado" del calendario viejo, que parpadeaba sin esto.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { calendarKeys, useSetOutcome, type CalendarEntryDetail } from "@/lib/queries/calendar";

export function OutcomeBar({
  e,
  versionLabels,
}: {
  e: CalendarEntryDetail;
  /** Formatos de los vídeos-problema, en orden. Para elegir cuál vendió. */
  versionLabels: string[];
}) {
  const qc = useQueryClient();
  const m = useSetOutcome();
  const [uploaded, setUploaded] = useState(e.uploaded);
  const [sold, setSold] = useState(e.sold);
  const [version, setVersion] = useState<number | null>(e.sold_version);
  const [revenue, setRevenue] = useState(e.revenue_eur ? String(e.revenue_eur) : "");

  useEffect(() => {
    setUploaded(e.uploaded);
    setSold(e.sold);
    setVersion(e.sold_version);
    setRevenue(e.revenue_eur ? String(e.revenue_eur) : "");
  }, [e.uploaded, e.sold, e.sold_version, e.revenue_eur]);

  const push = (patch: Record<string, unknown>) => {
    m.mutate(
      { date: e.date, product_id: e.product_id, ...patch },
      {
        onSuccess: () => {
          // El mes cambia de color y las estadísticas se recalculan.
          qc.invalidateQueries({ queryKey: calendarKeys.day(e.date) });
          qc.invalidateQueries({ queryKey: ["calendar-month", e.date.slice(0, 7)] });
          qc.invalidateQueries({ queryKey: calendarKeys.stats });
        },
        onError: (err) => toast.error(err.message),
      },
    );
  };

  const toggleUploaded = () => {
    const v = !uploaded;
    setUploaded(v);
    push({ uploaded: v });
  };

  const toggleSold = () => {
    const v = !sold;
    setSold(v);
    // Vender implica haberlo subido — evita el estado imposible
    // "vendió pero no subido", que rompería la conversión (sold/uploaded).
    if (v && !uploaded) setUploaded(true);
    push(v && !uploaded ? { sold: v, uploaded: true } : { sold: v });
  };

  const pickVersion = (i: number) => {
    const v = version === i ? null : i;
    setVersion(v);
    if (v !== null) {
      setSold(true);
      if (!uploaded) setUploaded(true);
      push({ sold_version: v, sold: true, uploaded: true });
    } else {
      push({ sold_version: -1 });   // -1 = sin versión (el back lo ignora si no existe)
    }
  };

  const saveRevenue = () => {
    const n = Number(revenue.replace(",", "."));
    if (Number.isNaN(n)) return;
    push({ revenue_eur: n });
  };

  return (
    <div className="space-y-1.5 rounded-lg border border-border/60 bg-muted/20 p-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Toggle on={uploaded} onClick={toggleUploaded} tone="sky" label="📤 Subido" />
        <Toggle on={sold} onClick={toggleSold} tone="green" label="💰 Vendió" />
        {m.isPending && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        {sold && (
          <div className="ml-auto flex items-center gap-1">
            <input
              value={revenue}
              onChange={(ev) => setRevenue(ev.target.value)}
              onBlur={saveRevenue}
              onKeyDown={(ev) => ev.key === "Enter" && saveRevenue()}
              placeholder="€"
              className="w-16 rounded border border-border bg-background px-1.5 py-0.5 text-[11px]"
              title="Cuánto te llevaste"
            />
          </div>
        )}
      </div>

      {sold && versionLabels.length > 0 && (
        <div>
          <p className="text-[10px] text-muted-foreground">¿Qué versión vendió?</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {versionLabels.map((label, i) => (
              <button
                key={i}
                onClick={() => pickVersion(i)}
                title={label}
                className={
                  "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] transition " +
                  (version === i
                    ? "border-green-500 bg-green-500/20 font-semibold text-green-500"
                    : "border-border text-muted-foreground hover:border-foreground/50")
                }
              >
                {version === i && <Check className="h-2.5 w-2.5" />}
                V{i + 1} · {label.slice(0, 22)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Toggle({
  on, onClick, label, tone,
}: {
  on: boolean; onClick: () => void; label: string; tone: "sky" | "green";
}) {
  const active =
    tone === "sky"
      ? "border-sky-500 bg-sky-500/15 text-sky-500"
      : "border-green-500 bg-green-500/15 text-green-500";
  return (
    <button
      onClick={onClick}
      className={
        "rounded-md border px-2 py-1 text-[11px] font-medium transition " +
        (on ? active : "border-border text-muted-foreground hover:border-foreground/50")
      }
    >
      {label}
    </button>
  );
}
