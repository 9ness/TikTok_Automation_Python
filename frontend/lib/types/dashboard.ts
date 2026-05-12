/** Tipos del endpoint /api/v1/dashboard/summary. */

export interface VideoSummary {
  generation_id: string;
  user_id: string;
  product_id: string;
  tier_used: string;
  cost_total: number;
  status: string;
  created_at: string;
  completed_at: string | null;
}

export interface PilotUserSummary {
  username: string;
  display_name: string;
  status: "pilot" | "graduated";
  days_in_program: number;
  shoppable_videos_published: number;
  weekly_shoppable_remaining: number;
  graduation_eligible: boolean;
}

export type AlertSeverity = "info" | "warning" | "error";

export interface Alert {
  severity: AlertSeverity;
  code: string;
  message: string;
}

export interface DashboardSummaryResponse {
  total_users: number;
  total_products: number;
  total_videos_this_month: number;
  total_cost_this_month: number;
  active_jobs_count: number;
  pending_jobs_count: number;
  running_jobs_count: number;
  recent_videos: VideoSummary[];
  pilot_users_summary: PilotUserSummary[];
  alerts: Alert[];
}
