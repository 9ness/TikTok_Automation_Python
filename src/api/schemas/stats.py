"""Schemas Pydantic para los endpoints de estadísticas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DailyCostPoint(BaseModel):
    date: str  # YYYY-MM-DD
    cost: float
    count: int = 0


class MonthlyStatsResponse(BaseModel):
    month: str  # YYYY-MM
    total_cost_usd: float
    total_videos_generated: int
    cost_by_module: dict[str, float] = Field(default_factory=dict)  # tiktok_shop, presidents, etc.
    cost_by_user: dict[str, float] = Field(default_factory=dict)
    cost_by_product: dict[str, float] = Field(default_factory=dict)
    cost_by_tier: dict[str, float] = Field(default_factory=dict)
    daily_breakdown: list[DailyCostPoint] = Field(default_factory=list)


class HistoricalStatsResponse(BaseModel):
    months: list[MonthlyStatsResponse]
    total_months: int


class BudgetStatusResponse(BaseModel):
    current_month_cost: float
    monthly_budget_usd: float | None = None  # null si no hay budget configurado
    percent_used: float | None = None
    status: Literal["ok", "warning", "exceeded", "no_budget"]
    days_remaining_in_month: int
    projected_month_end_cost: float
