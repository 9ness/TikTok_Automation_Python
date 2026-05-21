"""Referidos del Editor Auto. CRUD ligero — los `uses` se añaden vía
la creación de un user con `referred_by_code`."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, UserNotFoundError
from src.api.schemas.editor_auto import (
    ReferralCodeResponse,
    ReferralUseResponse,
)
from src.editor_auto.models import ReferralCode
from src.editor_auto.repos import ReferralRepo, UserRepo

router = APIRouter(
    prefix="/api/v1/editor-auto/referrals",
    tags=["editor-auto · referrals"],
    dependencies=[Depends(get_current_user)],
)


def _serialize(ref: ReferralCode) -> ReferralCodeResponse:
    """Calcula descuento acumulado para el período actual + count activo."""
    current_period = datetime.now(timezone.utc).strftime("%Y-%m")
    next_period = _next_yyyy_mm(current_period)
    active = [u for u in ref.uses if u.valid_until_period == next_period]
    accum_pct = ref.discount_for_period(next_period)
    return ReferralCodeResponse(
        code=ref.code,
        owner_user_id=ref.owner_user_id,
        owner_user_name=ref.owner_user_name,
        uses=[
            ReferralUseResponse(**u.model_dump()) for u in ref.uses
        ],
        created_at=ref.created_at,
        active_uses_count=len(active),
        accumulated_discount_pct_next_period=accum_pct,
    )


def _next_yyyy_mm(yyyy_mm: str) -> str:
    y, m = yyyy_mm.split("-")
    yi, mi = int(y), int(m)
    mi += 1
    if mi > 12:
        mi = 1
        yi += 1
    return f"{yi:04d}-{mi:02d}"


@router.get("", response_model=list[ReferralCodeResponse])
def list_referrals() -> list[ReferralCodeResponse]:
    return [_serialize(r) for r in ReferralRepo().list_all()]


@router.get("/lookup/{code}", response_model=ReferralCodeResponse)
def lookup_referral(code: str) -> ReferralCodeResponse:
    """Valida que un code existe — usado por el frontend al registrar un user."""
    ref = ReferralRepo().get(code.upper())
    if ref is None:
        raise APIError(
            f"Código de referido '{code}' no existe",
            status_code=404,
            details={"code": code},
        )
    return _serialize(ref)


@router.post(
    "/users/{user_id}/generate",
    response_model=ReferralCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_for_user(user_id: str) -> ReferralCodeResponse:
    """Crea (o devuelve) el code propio de un user.

    Idempotente — si ya tenía code, lo devuelve.
    """
    user_repo = UserRepo()
    u = user_repo.get(user_id)
    if u is None:
        raise UserNotFoundError(f"Usuario {user_id} no encontrado")

    ref_repo = ReferralRepo()
    if u.referral_code:
        existing = ref_repo.get(u.referral_code)
        if existing:
            return _serialize(existing)

    # Crear nuevo code (intentamos hasta 5 veces por improbable colisión)
    for _ in range(5):
        ref = ReferralCode(owner_user_id=u.id, owner_user_name=u.name)
        if ref_repo.get(ref.code) is None:
            ref_repo.save(ref)
            u.referral_code = ref.code
            user_repo.save(u)
            return _serialize(ref)
    raise APIError("No se pudo generar code único — reintenta", status_code=500)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_referral(code: str) -> None:
    ok = ReferralRepo().delete(code.upper())
    if not ok:
        raise APIError(f"Code '{code}' no encontrado", status_code=404)
