"""CRUD de planes de Editor Auto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, ValidationError
from src.api.schemas.editor_auto import (
    PlanCreateRequest,
    PlanResponse,
    PlanUpdateRequest,
)
from src.editor_auto.models import Plan
from src.editor_auto.repos import PlanRepo

router = APIRouter(
    prefix="/api/v1/editor-auto/plans",
    tags=["editor-auto · plans"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(p: Plan) -> PlanResponse:
    return PlanResponse(**p.model_dump())


@router.get("", response_model=list[PlanResponse])
def list_plans(only_active: bool = False) -> list[PlanResponse]:
    return [_to_response(p) for p in PlanRepo().list_all(only_active=only_active)]


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: str) -> PlanResponse:
    p = PlanRepo().get(plan_id)
    if p is None:
        raise APIError(f"Plan {plan_id} no encontrado", status_code=404)
    return _to_response(p)


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreateRequest) -> PlanResponse:
    repo = PlanRepo()
    if repo.get_by_slug(payload.slug) is not None:
        raise ValidationError(
            f"Ya existe un plan con slug '{payload.slug}'",
            details={"slug": payload.slug},
        )
    plan = Plan(**payload.model_dump())
    repo.save(plan)
    return _to_response(plan)


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(plan_id: str, payload: PlanUpdateRequest) -> PlanResponse:
    repo = PlanRepo()
    plan = repo.get(plan_id)
    if plan is None:
        raise APIError(f"Plan {plan_id} no encontrado", status_code=404)
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(plan, k, v)
    repo.save(plan)
    return _to_response(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: str) -> None:
    ok = PlanRepo().delete(plan_id)
    if not ok:
        raise APIError(f"Plan {plan_id} no encontrado", status_code=404)
