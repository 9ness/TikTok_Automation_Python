"use client";

/**
 * Rejilla del mes — el color de cada día dice qué pasó, de un vistazo.
 *
 * Inspirado en los calendarios de FIT9NESS y MasterPicks: cabecera con flechas,
 * 7 columnas L-D, y la señal DENTRO de la celda (ellos ponen las unidades
 * ganadas; aquí, los euros). Un mes se lee sin abrir nada.
 *
 * Semana europea (lunes primero) — `getDay()` de JS devuelve 0=domingo, así
 * que hay que rotar; si no, todo el mes queda desplazado un día.
 */

import type { CalendarEntry } from "@/lib/queries/calendar";

const DOW = ["L", "M", "X", "J", "V", "S", "D"];
const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** "2026-07" o "2026-07-15" → [año, mes] numéricos. `split()[i]` es
 * `string | undefined` con noUncheckedIndexedAccess, así que se parsea aquí
 * una vez en vez de esparcir `!` por el fichero. */
function parseYm(s: string): [number, number] {
  const parts = s.split("-");
  return [Number(parts[0] ?? 0), Number(parts[1] ?? 0)];
}

/** "2026-07" → [{date, day}...] con huecos al principio para cuadrar el lunes. */
function buildGrid(month: string): (string | null)[] {
  const [y, m] = parseYm(month);
  if (!y || !m) return [];
  const first = new Date(Date.UTC(y, m - 1, 1));
  const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
  // getUTCDay: 0=domingo … 6=sábado → a lunes-primero: 0=lunes … 6=domingo
  const offset = (first.getUTCDay() + 6) % 7;
  const cells: (string | null)[] = Array(offset).fill(null);
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(`${month}-${String(d).padStart(2, "0")}`);
  }
  return cells;
}

export function monthLabel(month: string): string {
  const [y, m] = parseYm(month);
  if (!y || !m) return month;
  return `${MESES[m - 1] ?? ""} ${y}`.toUpperCase();
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = parseYm(month);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

interface DayCell {
  total: number;
  uploaded: number;
  sold: number;
  revenue: number;
}

function summarize(entries: CalendarEntry[]): Map<string, DayCell> {
  const m = new Map<string, DayCell>();
  for (const e of entries) {
    const c = m.get(e.date) ?? { total: 0, uploaded: 0, sold: 0, revenue: 0 };
    c.total += 1;
    if (e.uploaded) c.uploaded += 1;
    if (e.sold) c.sold += 1;
    c.revenue += e.revenue_eur;
    m.set(e.date, c);
  }
  return m;
}

export function MonthGrid({
  month,
  entries,
  selected,
  onSelect,
  onPrev,
  onNext,
}: {
  month: string;
  entries: CalendarEntry[];
  selected: string;
  onSelect: (date: string) => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const cells = buildGrid(month);
  const byDate = summarize(entries);
  const today = todayIso();

  return (
    <div className="rounded-xl border border-border/60 bg-card p-3">
      {/* Cabecera: ‹ MES AÑO › */}
      <div className="mb-3 flex items-center justify-between">
        <button
          onClick={onPrev}
          className="rounded-lg border border-border px-2.5 py-1 text-sm text-muted-foreground hover:border-foreground/50 hover:text-foreground"
          aria-label="Mes anterior"
        >
          ‹
        </button>
        <span className="text-sm font-semibold tracking-wide">{monthLabel(month)}</span>
        <button
          onClick={onNext}
          className="rounded-lg border border-border px-2.5 py-1 text-sm text-muted-foreground hover:border-foreground/50 hover:text-foreground"
          aria-label="Mes siguiente"
        >
          ›
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center">
        {DOW.map((d) => (
          <div key={d} className="pb-1 text-[10px] font-medium text-muted-foreground">
            {d}
          </div>
        ))}

        {cells.map((date, i) => {
          if (!date) return <div key={`gap-${i}`} />;
          const day = Number(date.slice(-2));
          const c = byDate.get(date);
          const isToday = date === today;
          const isSel = date === selected;

          // Color = qué pasó. Vendió > subido sin vender > planificado > vacío.
          let tone = "border-transparent bg-muted/30 text-muted-foreground";
          if (c?.sold) tone = "border-green-500/50 bg-green-500/15 text-green-500";
          else if (c?.uploaded) tone = "border-sky-500/40 bg-sky-500/10 text-sky-500";
          else if (c?.total) tone = "border-amber-500/40 bg-amber-500/10 text-amber-500";

          return (
            <button
              key={date}
              onClick={() => onSelect(date)}
              className={
                "flex aspect-square flex-col items-center justify-center rounded-lg border p-0.5 transition " +
                tone +
                (isSel ? " ring-2 ring-purple-500" : "") +
                (isToday && !isSel ? " ring-1 ring-foreground/40" : "") +
                (c?.total ? " hover:brightness-125" : " hover:bg-muted/50")
              }
              title={
                c
                  ? `${c.total} producto(s) · ${c.uploaded} subido(s) · ${c.sold} vendido(s)`
                  : "Sin productos"
              }
            >
              <span className={"text-xs " + (c?.total ? "font-bold" : "")}>{day}</span>
              {c?.sold ? (
                <span className="text-[8px] font-semibold leading-none">
                  {c.revenue > 0 ? `+${c.revenue.toFixed(0)}€` : `${c.sold}✓`}
                </span>
              ) : c?.total ? (
                <span className="text-[8px] leading-none opacity-80">{c.total}</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {/* Leyenda — sin esto los colores no dicen nada */}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border/50 pt-2 text-[10px] text-muted-foreground">
        <Dot className="bg-green-500" /> vendió
        <Dot className="bg-sky-500" /> subido
        <Dot className="bg-amber-500" /> pendiente
        <span className="ml-auto">◻ hoy</span>
      </div>
    </div>
  );
}

function Dot({ className }: { className: string }) {
  return <span className={"inline-block h-2 w-2 rounded-full " + className} />;
}
