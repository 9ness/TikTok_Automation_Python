/**
 * Calendario por FECHAS reales + resultados + estadísticas.
 *
 * OJO al separar mes/día: `useMonth` NO trae datos de producto (por eso el mes
 * carga igual de rápido con 17 productos que con 2.000); `useDay` sí los trae,
 * pero un día son pocos. Si algún día se necesita algo del producto en la
 * rejilla del mes, hay que guardarlo en la entrada — no llamar al producto.
 */

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface CalendarEntry {
  date: string;
  product_id: string;
  slug: string;
  name: string;
  score: number;
  ads_verdict: string;
  influencer_count: number;
  commission_eur: number;
  uploaded: boolean;
  sold: boolean;
  sold_version: number | null;
  sold_format: string;
  revenue_eur: number;
  note: string;
}

/** Solo en la vista de UN día: cuenta lo que el producto tiene generado. */
export interface CalendarEntryDetail extends CalendarEntry {
  problem_videos_count: number;
  presets_count: number;
  carousels_count: number;
  hooks_count: number;
  pack_ready: boolean;
}

export interface MonthStats {
  month?: string;
  products: number;
  uploaded: number;
  sold: number;
  revenue_eur: number;
  conversion_pct: number;
  by_format: Record<string, { sold: number }>;
}

export interface MonthData {
  month: string;
  exists: boolean;
  entries: CalendarEntry[];
  stats: MonthStats;
}

export const calendarKeys = {
  months: ["calendar-months"] as const,
  month: (m: string) => ["calendar-month", m] as const,
  day: (d: string) => ["calendar-day", d] as const,
  stats: ["calendar-stats"] as const,
};

export function useCalendarMonths() {
  return useQuery<string[]>({
    queryKey: calendarKeys.months,
    queryFn: () => api.get<string[]>("/api/v1/tiktok-shop/calendar/months"),
    staleTime: 60_000,
    retry: false,
  });
}

export function useMonth(month: string) {
  return useQuery<MonthData>({
    queryKey: calendarKeys.month(month),
    queryFn: () => api.get<MonthData>(`/api/v1/tiktok-shop/calendar/month/${month}`),
    enabled: !!month,
    retry: false,
  });
}

export function useDay(date: string, enabled = true) {
  return useQuery<CalendarEntryDetail[]>({
    queryKey: calendarKeys.day(date),
    queryFn: () =>
      api.get<CalendarEntryDetail[]>(`/api/v1/tiktok-shop/calendar/day/${date}`),
    enabled: enabled && !!date,
    retry: false,
  });
}

export function useSetOutcome() {
  return useMutation<
    CalendarEntry,
    Error,
    {
      date: string;
      product_id: string;
      uploaded?: boolean;
      sold?: boolean;
      sold_version?: number | null;
      revenue_eur?: number;
      note?: string;
    }
  >({
    mutationFn: (body) =>
      api.post<CalendarEntry>("/api/v1/tiktok-shop/calendar/outcome", body),
  });
}

export interface StatsData extends MonthStats {
  months: string[];
  per_month: MonthStats[];
}

export function useCalendarStats(months?: string[]) {
  const qs = months?.length ? `?months=${months.join(",")}` : "";
  return useQuery<StatsData>({
    queryKey: [...calendarKeys.stats, qs],
    queryFn: () => api.get<StatsData>(`/api/v1/tiktok-shop/calendar/stats${qs}`),
    retry: false,
  });
}

export function useRemoveCalendarEntries() {
  return useMutation<
    { removed: number },
    Error,
    { date?: string; month?: string; product_ids?: string[] }
  >({
    mutationFn: ({ date, month, product_ids }) => {
      const p = new URLSearchParams();
      if (date) p.set("date", date);
      if (month) p.set("month", month);
      if (product_ids?.length) p.set("product_ids", product_ids.join(","));
      return api.del<{ removed: number }>(
        `/api/v1/tiktok-shop/calendar/entries?${p.toString()}`,
      );
    },
  });
}
