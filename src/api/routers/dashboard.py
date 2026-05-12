"""Endpoint del dashboard global — KPIs + alertas para la landing.

Combina datos de:
- ProductRepo / UserRepo (counters TT Shop)
- GenerationRepo (vídeos del mes en curso)
- JobQueue (active jobs counters)
- pilot_tracker (status Pilot Program de cada usuario)
- stats router (cost del mes + budget)

Las alertas se calculan a partir de los mismos datos. Códigos de alerta:
- `budget_warning`: percent_used >= 80%
- `budget_exceeded`: cost >= budget
- `recent_failures`: ≥3 jobs FAILED en las últimas 24h
- `pilot_freeze`: usuario ha agotado su límite semanal de shoppable
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_current_user,
    get_generation_repo,
    get_product_repo,
    get_queue,
    get_user_repo,
)
from src.api.routers.stats import _build_monthly_stats, _current_month_str
from src.api.schemas.dashboard import (
    Alert,
    DashboardSummaryResponse,
    PilotUserSummary,
    VideoSummary,
)
from src.queue.manager import JobQueue
from src.queue.models import JobStatus
from src.tiktok_shop.repos import GenerationRepo, ProductRepo, UserRepo
from src.tiktok_shop.services.pilot_tracker import (
    _ensure_weekly_reset,
    days_in_pilot,
)


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)


# Cache en memoria del summary — list_all() de Redis (Upstash REST) hace
# muchas roundtrips y el endpoint puede tardar 20-30s con muchos datos. El
# frontend se queda con "Failed to fetch" por timeout del navegador.
# TTL 60s es suficiente: el dashboard no necesita estar al segundo, y la
# cola en tiempo real va por WebSocket aparte.
_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, DashboardSummaryResponse]] = {}


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    product_repo: Annotated[ProductRepo, Depends(get_product_repo)],
    user_repo: Annotated[UserRepo, Depends(get_user_repo)],
    gen_repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> DashboardSummaryResponse:
    now = time.time()
    cached = _cache.get("summary")
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    products = [p for p in product_repo.list_all() if not p.deleted]
    users = [u for u in user_repo.list_all() if not u.deleted]

    # Stats del mes actual
    month = _current_month_str()
    stats = _build_monthly_stats(gen_repo, queue, month)

    # Cola
    all_jobs = queue.get_all()
    pending = sum(1 for j in all_jobs if j.status == JobStatus.PENDING)
    running = sum(1 for j in all_jobs if j.status == JobStatus.RUNNING)

    # Vídeos recientes (últimos 5 generados — TT Shop)
    recent_gens = gen_repo.list_recent(limit=20)
    recent_videos = [
        VideoSummary(
            generation_id=g.id,
            user_id=g.user_id,
            product_id=g.product_id,
            tier_used=g.tier_used,
            cost_total=g.cost.total or 0.0,
            status=g.generation_status.value,
            created_at=g.created_at or "",
            completed_at=g.completed_at,
        )
        for g in recent_gens if not g.deleted
    ][:5]

    # Pilot summary
    pilot_summary: list[PilotUserSummary] = []
    for u in users:
        _ensure_weekly_reset(u)
        pilot_summary.append(
            PilotUserSummary(
                username=u.username,
                display_name=u.display_name,
                status=u.status,
                days_in_program=days_in_pilot(u),
                shoppable_videos_published=u.pilot_program.shoppable_videos_published,
                weekly_shoppable_remaining=u.pilot_program.weekly_shoppable_remaining,
                graduation_eligible=u.pilot_program.graduation_eligible,
            )
        )

    # Alerts
    alerts = _build_alerts(stats.total_cost_usd, all_jobs, users)

    response = DashboardSummaryResponse(
        total_users=len(users),
        total_products=len(products),
        total_videos_this_month=stats.total_videos_generated,
        total_cost_this_month=stats.total_cost_usd,
        active_jobs_count=pending + running,
        pending_jobs_count=pending,
        running_jobs_count=running,
        recent_videos=recent_videos,
        pilot_users_summary=pilot_summary,
        alerts=alerts,
    )
    _cache["summary"] = (now, response)
    return response


def _build_alerts(month_cost: float, all_jobs: list, users: list) -> list[Alert]:
    out: list[Alert] = []

    # Budget alerts
    budget_env = os.getenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD")
    budget: float | None = None
    if budget_env:
        try:
            budget = float(budget_env)
        except ValueError:
            budget = None
    if budget and budget > 0:
        pct = (month_cost / budget) * 100
        if month_cost >= budget:
            out.append(Alert(
                severity="error",
                code="budget_exceeded",
                message=(
                    f"Presupuesto mensual excedido: ${month_cost:.2f} de ${budget:.2f} "
                    f"({pct:.0f}%)."
                ),
            ))
        elif pct >= 80:
            out.append(Alert(
                severity="warning",
                code="budget_warning",
                message=(
                    f"Presupuesto al {pct:.0f}%: ${month_cost:.2f} de ${budget:.2f}."
                ),
            ))

    # Recent failures (≥3 en últimas 24h)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()
    recent_failed = sum(
        1 for j in all_jobs
        if j.status == JobStatus.FAILED and (j.finished_at or 0) >= cutoff
    )
    if recent_failed >= 3:
        out.append(Alert(
            severity="error",
            code="recent_failures",
            message=f"{recent_failed} jobs fallidos en las últimas 24h. Revisa los logs.",
        ))

    # Pilot freeze (usuarios sin shoppable disponibles esta semana)
    frozen = [u for u in users if u.status == "pilot" and u.pilot_program.weekly_shoppable_remaining == 0]
    if frozen:
        names = ", ".join(u.username for u in frozen[:3])
        more = f" +{len(frozen) - 3} más" if len(frozen) > 3 else ""
        out.append(Alert(
            severity="info",
            code="pilot_freeze",
            message=f"{len(frozen)} cuenta(s) en límite semanal: {names}{more}.",
        ))

    return out
