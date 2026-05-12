"""Endpoints CRUD de usuarios TikTok + asignación de productos +
estado del Pilot Program.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Path as PathParam, Query, Response, status

from src.api.dependencies import get_current_user, get_product_repo, get_user_repo
from src.api.exceptions import (
    DriveError,
    ProductAlreadyAssignedError,
    ProductNotFoundError,
    UserNotFoundError,
    ValidationError,
)
from src.api.schemas.user import (
    AssignProductRequest,
    PilotProgressResponse,
    PilotRequirement,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from src.tiktok_shop.config import (
    PILOT_GRADUATION_MIN_CHR,
    PILOT_GRADUATION_REQUIRED_DAYS,
    PILOT_GRADUATION_REQUIRED_ORDERS,
    PILOT_GRADUATION_REQUIRED_VIDEOS,
    user_drive_folder,
)
from src.tiktok_shop.models import TikTokUser
from src.tiktok_shop.repos import ProductRepo, UserRepo
from src.tiktok_shop.services.pilot_tracker import (
    days_in_pilot,
    weeks_progress,
    _check_graduation_eligible,
    _ensure_weekly_reset,
)
from src.tiktok_shop.utils.validators import validate_tiktok_username


router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    dependencies=[Depends(get_current_user)],
)


def _normalize_username(raw: str) -> str:
    """Path param viene URL-encoded (`%40user` → `@user`). Normaliza y valida."""
    decoded = urllib.parse.unquote(raw).strip()
    if not decoded.startswith("@"):
        decoded = f"@{decoded}"
    ok, err = validate_tiktok_username(decoded)
    if not ok:
        raise ValidationError(err, details={"username": raw})
    return decoded


def _to_response(user: TikTokUser) -> UserResponse:
    return UserResponse.model_validate(user.model_dump())


def _get_user_or_404(repo: UserRepo, raw_username: str) -> TikTokUser:
    username = _normalize_username(raw_username)
    user = repo.get_by_username(username)
    if user is None:
        raise UserNotFoundError(
            f"Usuario '{username}' no encontrado.",
            details={"username": username},
        )
    return user


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------
@router.get("", response_model=UserListResponse)
def list_users(
    repo: Annotated[UserRepo, Depends(get_user_repo)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    niche: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
) -> UserListResponse:
    users = repo.list_all()
    if not include_deleted:
        users = [u for u in users if not u.deleted]
    if niche:
        users = [u for u in users if u.niche == niche]
    total = len(users)
    page = users[offset : offset + limit]
    return UserListResponse(
        items=[_to_response(u) for u in page],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------
@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    repo: Annotated[UserRepo, Depends(get_user_repo)],
) -> UserResponse:
    if repo.get_by_username(payload.username) is not None:
        raise ValidationError(
            f"Ya existe un usuario con username '{payload.username}'.",
            details={"username": payload.username},
        )

    drive_folder = user_drive_folder(payload.username)
    try:
        Path(drive_folder).mkdir(parents=True, exist_ok=True)
        Path(drive_folder, "products").mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise DriveError(
            f"No se pudo crear la estructura de carpetas: {e}",
            details={"username": payload.username, "path": drive_folder},
        )

    user = TikTokUser(
        username=payload.username,
        display_name=payload.display_name,
        niche=payload.niche,
        language=payload.language,
        country=payload.country,
        followers_count=payload.followers_count,
        creator_health_rating=payload.creator_health_rating,
        default_voice_id=payload.default_voice_id,
        default_language=payload.default_language,
        default_video_tier=payload.default_video_tier,
        drive_folder=drive_folder,
    )
    repo.save(user)
    return _to_response(user)


# ---------------------------------------------------------------------------
# GET /users/{username}
# ---------------------------------------------------------------------------
@router.get("/{username}", response_model=UserResponse)
def get_user(
    username: Annotated[str, PathParam(...)],
    repo: Annotated[UserRepo, Depends(get_user_repo)],
) -> UserResponse:
    user = _get_user_or_404(repo, username)
    return _to_response(user)


# ---------------------------------------------------------------------------
# PUT /users/{username}
# ---------------------------------------------------------------------------
@router.put("/{username}", response_model=UserResponse)
def update_user(
    username: Annotated[str, PathParam(...)],
    payload: UserUpdate,
    repo: Annotated[UserRepo, Depends(get_user_repo)],
) -> UserResponse:
    user = _get_user_or_404(repo, username)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    repo.save(user)
    return _to_response(user)


# ---------------------------------------------------------------------------
# DELETE /users/{username} — soft delete
# ---------------------------------------------------------------------------
@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    username: Annotated[str, PathParam(...)],
    repo: Annotated[UserRepo, Depends(get_user_repo)],
) -> Response:
    user = _get_user_or_404(repo, username)
    user.deleted = True
    repo.save(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# POST /users/{username}/products — assign
# ---------------------------------------------------------------------------
@router.post(
    "/{username}/products",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def assign_product(
    username: Annotated[str, PathParam(...)],
    payload: AssignProductRequest,
    user_repo: Annotated[UserRepo, Depends(get_user_repo)],
    product_repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> UserResponse:
    user = _get_user_or_404(user_repo, username)
    product = product_repo.get(payload.product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{payload.product_id}' no encontrado.",
            details={"product_id": payload.product_id},
        )
    if payload.product_id in user.assigned_products:
        raise ProductAlreadyAssignedError(
            f"El producto '{payload.product_id}' ya está asignado al usuario '{user.username}'.",
            details={"username": user.username, "product_id": payload.product_id},
        )
    user.assigned_products.append(payload.product_id)
    user_repo.save(user)
    return _to_response(user)


# ---------------------------------------------------------------------------
# DELETE /users/{username}/products/{product_id} — unassign
# ---------------------------------------------------------------------------
@router.delete(
    "/{username}/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unassign_product(
    username: Annotated[str, PathParam(...)],
    product_id: str,
    repo: Annotated[UserRepo, Depends(get_user_repo)],
) -> Response:
    user = _get_user_or_404(repo, username)
    if product_id not in user.assigned_products:
        # Idempotente: si ya no está, devolvemos 204 igualmente
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    user.assigned_products.remove(product_id)
    repo.save(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# GET /users/{username}/pilot-progress
# ---------------------------------------------------------------------------
@router.get(
    "/{username}/pilot-progress",
    response_model=PilotProgressResponse,
)
def pilot_progress(
    username: Annotated[str, PathParam(...)],
    repo: Annotated[UserRepo, Depends(get_user_repo)],
) -> PilotProgressResponse:
    user = _get_user_or_404(repo, username)

    # Asegurar reset semanal antes de leer contadores
    _ensure_weekly_reset(user)

    pp = user.pilot_program
    days = days_in_pilot(user)
    eligible = _check_graduation_eligible(user)
    weekly = weeks_progress(user)

    requirements = _build_requirements(user, days)

    if user.status == "graduated":
        graduation_status = "graduated"
    elif eligible:
        graduation_status = "eligible"
    else:
        graduation_status = "not_eligible"

    days_until_eligible = _days_until_eligible(user, days, eligible)

    return PilotProgressResponse(
        username=user.username,
        status=user.status,
        days_in_program=days,
        shoppable_videos_count=pp.shoppable_videos_published,
        current_chr=user.creator_health_rating,
        orders_count=pp.orders_generated,
        followers=user.followers_count,
        weekly_shoppable_used=weekly["shoppable_used"],
        weekly_shoppable_remaining=weekly["shoppable_remaining"],
        weekly_reset_at=weekly["reset_at"],
        quiz_passed=pp.quiz_passed,
        graduation_status=graduation_status,
        days_until_eligible=days_until_eligible,
        requirements_met=requirements,
    )


def _build_requirements(user: TikTokUser, days: int) -> list[PilotRequirement]:
    """Construye el desglose de las 3 vías de graduación con qué falta."""
    pp = user.pilot_program

    # Vía A — followers
    a_met = user.followers_count >= 5000
    a_missing: list[str] = []
    if not a_met:
        a_missing.append(f"Necesitas {5000 - user.followers_count} followers más (actual: {user.followers_count}).")

    # Vía B — videos + quiz + CHR + 30d
    b_videos_ok = pp.shoppable_videos_published >= PILOT_GRADUATION_REQUIRED_VIDEOS
    b_days_ok = days >= PILOT_GRADUATION_REQUIRED_DAYS
    b_quiz_ok = pp.quiz_passed
    b_chr_ok = user.creator_health_rating >= PILOT_GRADUATION_MIN_CHR
    b_met = b_videos_ok and b_days_ok and b_quiz_ok and b_chr_ok
    b_missing: list[str] = []
    if not b_videos_ok:
        b_missing.append(
            f"Faltan {PILOT_GRADUATION_REQUIRED_VIDEOS - pp.shoppable_videos_published} vídeos shoppable."
        )
    if not b_days_ok:
        b_missing.append(f"Faltan {PILOT_GRADUATION_REQUIRED_DAYS - days} días en el programa.")
    if not b_quiz_ok:
        b_missing.append("Quiz pendiente.")
    if not b_chr_ok:
        b_missing.append(
            f"CHR demasiado bajo: {user.creator_health_rating}/{PILOT_GRADUATION_MIN_CHR}."
        )

    # Vía C — órdenes + 30d
    c_orders_ok = pp.orders_generated >= PILOT_GRADUATION_REQUIRED_ORDERS
    c_days_ok = days >= PILOT_GRADUATION_REQUIRED_DAYS
    c_met = c_orders_ok and c_days_ok
    c_missing: list[str] = []
    if not c_orders_ok:
        c_missing.append(
            f"Faltan {PILOT_GRADUATION_REQUIRED_ORDERS - pp.orders_generated} órdenes shoppable."
        )
    if not c_days_ok:
        c_missing.append(f"Faltan {PILOT_GRADUATION_REQUIRED_DAYS - days} días en el programa.")

    return [
        PilotRequirement(
            name="via_a_5000_followers",
            label="Vía A: ≥5000 followers",
            met=a_met,
            missing=a_missing,
        ),
        PilotRequirement(
            name="via_b_videos_quiz_chr",
            label=f"Vía B: ≥{PILOT_GRADUATION_REQUIRED_VIDEOS} shoppable + ≥{PILOT_GRADUATION_REQUIRED_DAYS}d + quiz + CHR≥{PILOT_GRADUATION_MIN_CHR}",
            met=b_met,
            missing=b_missing,
        ),
        PilotRequirement(
            name="via_c_orders_30d",
            label=f"Vía C: ≥{PILOT_GRADUATION_REQUIRED_ORDERS} órdenes + ≥{PILOT_GRADUATION_REQUIRED_DAYS}d",
            met=c_met,
            missing=c_missing,
        ),
    ]


def _days_until_eligible(user: TikTokUser, days: int, eligible: bool) -> int | None:
    """Estima días para ser elegible si el bloqueante actual son los 30 días.
    Si nunca puede llegar (le faltan vídeos/órdenes/quiz/CHR/followers) → None.
    Si ya es elegible → 0."""
    if eligible or user.status == "graduated":
        return 0

    pp = user.pilot_program
    candidates: list[int] = []

    # Vía B: si todo lo demás está OK pero faltan días → días restantes
    if (
        pp.shoppable_videos_published >= PILOT_GRADUATION_REQUIRED_VIDEOS
        and pp.quiz_passed
        and user.creator_health_rating >= PILOT_GRADUATION_MIN_CHR
        and days < PILOT_GRADUATION_REQUIRED_DAYS
    ):
        candidates.append(PILOT_GRADUATION_REQUIRED_DAYS - days)

    # Vía C
    if (
        pp.orders_generated >= PILOT_GRADUATION_REQUIRED_ORDERS
        and days < PILOT_GRADUATION_REQUIRED_DAYS
    ):
        candidates.append(PILOT_GRADUATION_REQUIRED_DAYS - days)

    return min(candidates) if candidates else None
