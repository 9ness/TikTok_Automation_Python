/** Tipos de los endpoints /api/v1/stats. */

export interface DailyCostPoint {
  date: string;
  cost: number;
  count: number;
}

export interface MonthlyStatsResponse {
  month: string;
  total_cost_usd: number;
  total_videos_generated: number;
  cost_by_module: Record<string, number>;
  cost_by_user: Record<string, number>;
  cost_by_product: Record<string, number>;
  cost_by_tier: Record<string, number>;
  daily_breakdown: DailyCostPoint[];
}

export interface HistoricalStatsResponse {
  months: MonthlyStatsResponse[];
  total_months: number;
}

export type BudgetStatusValue = "ok" | "warning" | "exceeded" | "no_budget";

export interface BudgetStatusResponse {
  current_month_cost: number;
  monthly_budget_usd: number | null;
  percent_used: number | null;
  status: BudgetStatusValue;
  days_remaining_in_month: number;
  projected_month_end_cost: number;
}
