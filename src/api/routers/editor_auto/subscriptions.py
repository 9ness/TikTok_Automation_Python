"""Asignar / quitar suscripción a un EditorUser."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, UserNotFoundError, ValidationError
from src.api.schemas.editor_auto import (
    SubscriptionAssignRequest,
    SubscriptionResponse,
)
from src.editor_auto.models import Subscription
from src.editor_auto.repos import PlanRepo, UserRepo

router = APIRouter(
    prefix="/api/v1/editor-auto/users/{user_id}/subscription",
    tags=["editor-auto · subscriptions"],
    dependencies=[Depends(get_current_user)],
)


def _serialize(sub: Subscription) -> SubscriptionResponse:
    plan = PlanRepo().get(sub.plan_id)
    return SubscriptionResponse(
        plan_id=sub.plan_id,
        plan_slug=plan.slug if plan else "?",
        plan_name=plan.name if plan else "(plan eliminado)",
        status=sub.status,
        started_at=sub.started_at,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        discount_pct_next_period=sub.discount_pct_next_period,
        notes=sub.notes,
    )


@router.get("", response_model=SubscriptionResponse | None)
def get_subscription(user_id: str) -> SubscriptionResponse | None:
    u = UserRepo().get(user_id)
    if u is None:
        raise UserNotFoundError(f"Usuario {user_id} no encontrado")
    if u.subscription is None:
        return None
    return _serialize(u.subscription)


@router.put("", response_model=SubscriptionResponse)
def assign_subscription(
    user_id: str, payload: SubscriptionAssignRequest,
) -> SubscriptionResponse:
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None:
        raise UserNotFoundError(f"Usuario {user_id} no encontrado")
    plan_repo = PlanRepo()
    plan = plan_repo.get(payload.plan_id)
    if plan is None:
        raise ValidationError(
            f"Plan {payload.plan_id} no encontrado",
            details={"plan_id": payload.plan_id},
        )
    # Si plan promo con slots, validar y consumir un slot
    if plan.is_promo and plan.promo_slots_total is not None:
        if plan.promo_slots_used >= plan.promo_slots_total:
            raise ValidationError(
                f"Plan promo '{plan.slug}' agotado "
                f"({plan.promo_slots_used}/{plan.promo_slots_total}).",
                details={"plan_id": plan.id},
            )
        # Solo consume slot si es alta nueva (no reasignación del mismo plan)
        is_new_or_different = (
            u.subscription is None or u.subscription.plan_id != plan.id
        )
        if is_new_or_different:
            plan.promo_slots_used += 1
            plan_repo.save(plan)

    started_at = payload.started_at or datetime.now(timezone.utc).isoformat()
    sub = Subscription(
        plan_id=plan.id,
        status=payload.status,
        started_at=started_at,
        current_period_start=started_at,
        discount_pct_next_period=payload.discount_pct_next_period,
        notes=payload.notes,
    )
    u.subscription = sub
    repo.save(u)
    return _serialize(sub)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_subscription(user_id: str) -> None:
    """Quita la suscripción → user pasa a 'modo prueba' (sin cuotas)."""
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None:
        raise UserNotFoundError(f"Usuario {user_id} no encontrado")
    u.subscription = None
    repo.save(u)
