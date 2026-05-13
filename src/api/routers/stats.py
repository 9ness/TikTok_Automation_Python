"""Endpoints de estadísticas globales (costes, uso por mes/módulo).

Datos:
- Costes monetarios → solo TikTok Shop tiene métricas en `cost.total` por
  generación. Creator Reward NO trackea coste por job (sus pipelines no
  consumen Atlas Cloud — Presidentes/Pronósticos usan OpenAI+MiniMax con
  coste implícito; Copyright/Subs Auto son CPU local).
- Conteo de vídeos → cuenta TODAS las generaciones de TT Shop. Para CR
  contamos jobs `COMPLETED` de la cola.

`cost_by_module` actualmente solo tiene `tiktok_shop` (los demás 0). Se
extiende cuando añadamos cost tracking en CR.
"""

from __future__ import annotations

import calendar
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import (
    get_current_user,
    get_generation_repo,
    get_queue,
)
from src.api.exceptions import ValidationError
from src.api.schemas.stats import (
    BudgetStatusResponse,
    DailyCostPoint,
    HistoricalStatsResponse,
    MonthlyStatsResponse,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus
from src.tiktok_shop.models import VideoGeneration
from src.tiktok_shop.repos import GenerationRepo
from src import cost_tracking


router = APIRouter(
    prefix="/api/v1/stats",
    tags=["stats"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/jobs")
def list_jobs_with_costs(
    month: Annotated[str | None, Query(description="YYYY-MM")] = None,
    program: Annotated[str | None, Query(description="creator_reward | tiktok_shop")] = None,
    mode: Annotated[str | None, Query(description="presidents | pronosticos | copyright | subs_auto | tiktok_shop")] = None,
    user: Annotated[str | None, Query()] = None,
    product_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> dict:
    """Lista jobs (con su breakdown de coste) filtrados + agregado summary.

    Lee del módulo `src/cost_tracking.py`, que persiste cada job
    finalizado en Redis con su lista de líneas (OpenAI, MiniMax, Atlas).
    """
    jobs = cost_tracking.list_jobs(
        month=month,
        program=program,
        mode=mode,
        user=user,
        product_id=product_id,
        limit=limit,
    )
    summary = cost_tracking.aggregate_summary(jobs)
    return {
        "month": month or _current_month_str(),
        "filters": {
            "program": program,
            "mode": mode,
            "user": user,
            "product_id": product_id,
        },
        "summary": summary,
        "jobs": jobs,
    }


def _current_month_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _validate_month(month: str) -> str:
    if len(month) != 7 or month[4] != "-":
        raise ValidationError(
            f"Mes debe estar en formato YYYY-MM: '{month}'",
            details={"month": month},
        )
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise ValidationError(f"Mes inválido: '{month}'", details={"month": month})
    return month


def _gens_in_month(repo: GenerationRepo, month: str, *, scan_limit: int = 1000) -> list[VideoGeneration]:
    out: list[VideoGeneration] = []
    for g in repo.list_recent(limit=scan_limit):
        if g.deleted:
            continue
        if not g.created_at:
            continue
        try:
            ts = datetime.fromisoformat(g.created_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.strftime("%Y-%m") == month:
            out.append(g)
    return out


def _build_monthly_stats(
    repo: GenerationRepo,
    queue: JobQueue,
    month: str,
) -> MonthlyStatsResponse:
    gens = _gens_in_month(repo, month)

    cost_by_user: dict[str, float] = defaultdict(float)
    cost_by_product: dict[str, float] = defaultdict(float)
    cost_by_tier: dict[str, float] = defaultdict(float)
    daily: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "count": 0})

    total_cost = 0.0
    for g in gens:
        c = g.cost.total or 0.0
        total_cost += c
        cost_by_user[g.user_id] += c
        cost_by_product[g.product_id] += c
        cost_by_tier[g.tier_used] += c
        try:
            ts = datetime.fromisoformat((g.created_at or "").replace("Z", "+00:00"))
            day_key = ts.strftime("%Y-%m-%d")
            daily[day_key]["cost"] += c
            daily[day_key]["count"] += 1
        except ValueError:
            pass

    # Conteo total de vídeos: TT Shop generations + jobs completados de CR en el mismo mes
    cr_completed_in_month = _count_cr_completed_jobs_in_month(queue, month)
    total_videos = len(gens) + cr_completed_in_month

    cost_by_module = {
        "tiktok_shop": round(total_cost, 4),
        "creator_reward": 0.0,  # placeholder hasta que tengamos cost tracking en CR
    }

    daily_breakdown = sorted(
        (
            DailyCostPoint(date=d, cost=round(v["cost"], 4), count=v["count"])
            for d, v in daily.items()
        ),
        key=lambda p: p.date,
    )

    return MonthlyStatsResponse(
        month=month,
        total_cost_usd=round(total_cost, 4),
        total_videos_generated=total_videos,
        cost_by_module=cost_by_module,
        cost_by_user={k: round(v, 4) for k, v in cost_by_user.items()},
        cost_by_product={k: round(v, 4) for k, v in cost_by_product.items()},
        cost_by_tier={k: round(v, 4) for k, v in cost_by_tier.items()},
        daily_breakdown=daily_breakdown,
    )


def _count_cr_completed_jobs_in_month(queue: JobQueue, month: str) -> int:
    """Cuenta jobs `COMPLETED` de Creator Reward en el mes dado.
    Aproximación: usa `finished_at` (timestamp Unix) del Job."""
    cr_modes = {
        JobMode.PRESIDENTS,
        JobMode.PRONOSTICOS,
        JobMode.COPYRIGHT,
        JobMode.SUBS_AUTO,
    }
    count = 0
    for j in queue.get_all():
        if j.mode not in cr_modes or j.status != JobStatus.COMPLETED:
            continue
        if not j.finished_at:
            continue
        ts = datetime.fromtimestamp(j.finished_at, tz=timezone.utc)
        if ts.strftime("%Y-%m") == month:
            count += 1
    return count


# ---------------------------------------------------------------------------
# GET /stats/monthly
# ---------------------------------------------------------------------------
@router.get("/monthly", response_model=MonthlyStatsResponse)
def monthly_stats(
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
    queue: Annotated[JobQueue, Depends(get_queue)],
    month: str | None = Query(default=None, description="YYYY-MM. Default: mes actual."),
) -> MonthlyStatsResponse:
    target_month = _validate_month(month) if month else _current_month_str()
    return _build_monthly_stats(repo, queue, target_month)


# ---------------------------------------------------------------------------
# GET /stats/historical
# ---------------------------------------------------------------------------
@router.get("/historical", response_model=HistoricalStatsResponse)
def historical_stats(
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
    queue: Annotated[JobQueue, Depends(get_queue)],
    months: int = Query(default=12, ge=1, le=60),
) -> HistoricalStatsResponse:
    now = datetime.now(timezone.utc)
    out: list[MonthlyStatsResponse] = []
    year, month = now.year, now.month
    for _ in range(months):
        key = f"{year:04d}-{month:02d}"
        out.append(_build_monthly_stats(repo, queue, key))
        # Decrement month
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return HistoricalStatsResponse(months=out, total_months=len(out))


# ---------------------------------------------------------------------------
# GET /stats/budget
# ---------------------------------------------------------------------------
@router.get("/budget", response_model=BudgetStatusResponse)
def budget_status(
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> BudgetStatusResponse:
    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")
    stats = _build_monthly_stats(repo, queue, month_key)
    current_cost = stats.total_cost_usd

    budget_env = os.getenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD")
    budget: float | None = None
    if budget_env:
        try:
            budget = float(budget_env)
        except ValueError:
            budget = None

    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_elapsed = now.day
    days_remaining = max(0, days_in_month - days_elapsed)

    if days_elapsed > 0:
        projected = round(current_cost * (days_in_month / days_elapsed), 4)
    else:
        projected = current_cost

    if budget is None or budget <= 0:
        return BudgetStatusResponse(
            current_month_cost=current_cost,
            monthly_budget_usd=None,
            percent_used=None,
            status="no_budget",
            days_remaining_in_month=days_remaining,
            projected_month_end_cost=projected,
        )

    pct = round((current_cost / budget) * 100, 2)
    if current_cost >= budget:
        status_value = "exceeded"
    elif pct >= 80:
        status_value = "warning"
    else:
        status_value = "ok"

    return BudgetStatusResponse(
        current_month_cost=current_cost,
        monthly_budget_usd=budget,
        percent_used=pct,
        status=status_value,
        days_remaining_in_month=days_remaining,
        projected_month_end_cost=projected,
    )
