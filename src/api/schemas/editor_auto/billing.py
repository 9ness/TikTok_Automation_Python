"""Schemas Pydantic para planes / suscripciones / referidos del Editor Auto."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    daily_video_limit: int = 0
    monthly_video_limit: int | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    processing_window_start_hour: int = Field(8, ge=0, le=23)
    processing_window_end_hour: int = Field(18, ge=0, le=23)
    spacing_minutes: int = Field(0, ge=0, le=1440)
    queue_priority: int = 0
    queue_delay_minutes: int = Field(0, ge=0, le=1440)
    support_level: str = "email"
    features: list[str] = Field(default_factory=list)
    price_eur_monthly: float = 0.0
    price_eur_setup_once: float = 0.0
    is_active: bool = True
    is_promo: bool = False
    promo_slots_total: int | None = None
    sort_order: int = 100


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    daily_video_limit: int | None = None
    monthly_video_limit: int | None = None
    allowed_tools: list[str] | None = None
    processing_window_start_hour: int | None = Field(None, ge=0, le=23)
    processing_window_end_hour: int | None = Field(None, ge=0, le=23)
    spacing_minutes: int | None = Field(None, ge=0, le=1440)
    queue_priority: int | None = None
    queue_delay_minutes: int | None = Field(None, ge=0, le=1440)
    support_level: str | None = None
    features: list[str] | None = None
    price_eur_monthly: float | None = None
    price_eur_setup_once: float | None = None
    is_active: bool | None = None
    is_promo: bool | None = None
    promo_slots_total: int | None = None
    promo_slots_used: int | None = None
    sort_order: int | None = None


class PlanResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    daily_video_limit: int
    monthly_video_limit: int | None
    allowed_tools: list[str]
    processing_window_start_hour: int
    processing_window_end_hour: int
    spacing_minutes: int
    queue_priority: int
    queue_delay_minutes: int
    support_level: str
    features: list[str]
    price_eur_monthly: float
    price_eur_setup_once: float
    is_active: bool
    is_promo: bool
    promo_slots_total: int | None
    promo_slots_used: int
    sort_order: int
    created_at: str
    updated_at: str


class SubscriptionAssignRequest(BaseModel):
    """Asignar (o reasignar) un plan a un user."""
    plan_id: str
    status: str = "active"
    notes: str = ""
    started_at: str | None = None       # ISO; si None, ahora
    discount_pct_next_period: float = 0.0


class SubscriptionResponse(BaseModel):
    plan_id: str
    plan_slug: str
    plan_name: str
    status: str
    started_at: str
    current_period_start: str
    current_period_end: str | None
    discount_pct_next_period: float
    notes: str


class UsageResponse(BaseModel):
    daily_videos_used: int
    monthly_videos_used: int
    total_videos_ever: int
    last_reset_date: str
    month_period: str
    last_enqueue_at: str | None
    # Computados a partir del plan asignado para mostrar X/Y en la UI
    daily_limit: int | None = None
    monthly_limit: int | None = None


class ReferralUseResponse(BaseModel):
    referred_user_id: str
    referred_user_name: str
    used_at: str
    discount_pct_applied: float
    valid_until_period: str | None


class ReferralCodeResponse(BaseModel):
    code: str
    owner_user_id: str
    owner_user_name: str
    uses: list[ReferralUseResponse]
    created_at: str
    active_uses_count: int = 0
    accumulated_discount_pct_next_period: float = 0.0
