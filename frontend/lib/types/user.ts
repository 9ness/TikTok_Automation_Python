/**
 * Tipos del módulo de usuarios TikTok. Reflejan
 * `src/api/schemas/user.py`.
 */

import type { Tier } from "./product";

export type UserStatus = "pilot" | "graduated";

export interface PilotProgramState {
  started_at: string;
  shoppable_videos_published: number;
  orders_generated: number;
  quiz_passed: boolean;
  graduation_eligible: boolean;
  weekly_shoppable_remaining: number;
  weekly_shoppable_reset_at: string | null;
}

export interface User {
  id: string;
  username: string;
  display_name: string;
  niche: string;
  language: string;
  country: string;
  status: UserStatus;
  followers_count: number;
  creator_health_rating: number;
  pilot_program: PilotProgramState;
  drive_folder: string | null;
  assigned_products: string[];
  default_voice_id: string | null;
  default_language: string;
  default_video_tier: Tier;
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserListResponse {
  items: User[];
  total: number;
  limit: number;
  offset: number;
}

export interface UserCreateInput {
  username: string;
  display_name: string;
  niche?: string;
  language?: string;
  country?: string;
  followers_count?: number;
  creator_health_rating?: number;
  default_voice_id?: string | null;
  default_language?: string;
  default_video_tier?: Tier;
}

export type UserUpdateInput = Partial<{
  display_name: string;
  niche: string;
  language: string;
  country: string;
  followers_count: number;
  creator_health_rating: number;
  status: UserStatus;
  default_voice_id: string | null;
  default_language: string;
  default_video_tier: Tier;
}>;

export interface PilotRequirement {
  name: "via_a_5000_followers" | "via_b_videos_quiz_chr" | "via_c_orders_30d";
  label: string;
  met: boolean;
  missing: string[];
}

export type PilotGraduationStatus = "eligible" | "not_eligible" | "graduated";

export interface PilotProgressResponse {
  username: string;
  status: UserStatus;
  days_in_program: number;
  shoppable_videos_count: number;
  current_chr: number;
  orders_count: number;
  followers: number;
  weekly_shoppable_used: number;
  weekly_shoppable_remaining: number;
  weekly_reset_at: string | null;
  quiz_passed: boolean;
  graduation_status: PilotGraduationStatus;
  days_until_eligible: number | null;
  requirements_met: PilotRequirement[];
}
