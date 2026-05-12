"""Schemas Pydantic para el endpoint del dashboard global."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VideoSummary(BaseModel):
    """Vídeo reciente para el feed del dashboard."""

    generation_id: str
    user_id: str
    product_id: str
    tier_used: str
    cost_total: float
    status: str  # GenerationStatus value
    created_at: str
    completed_at: str | None = None


class PilotUserSummary(BaseModel):
    username: str
    display_name: str
    status: Literal["pilot", "graduated"]
    days_in_program: int
    shoppable_videos_published: int
    weekly_shoppable_remaining: int
    graduation_eligible: bool


AlertSeverity = Literal["info", "warning", "error"]


class Alert(BaseModel):
    severity: AlertSeverity
    code: str  # "budget_warning", "budget_exceeded", "recent_failures", etc.
    message: str


class DashboardSummaryResponse(BaseModel):
    # TikTok Shop counters
    total_users: int
    total_products: int
    # Mes en curso
    total_videos_this_month: int
    total_cost_this_month: float
    # Cola
    active_jobs_count: int
    pending_jobs_count: int
    running_jobs_count: int
    # Recientes
    recent_videos: list[VideoSummary] = Field(default_factory=list)
    pilot_users_summary: list[PilotUserSummary] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
