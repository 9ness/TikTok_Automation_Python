"""CRUD de usuarios del programa Editor Auto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from datetime import datetime, timezone

from src.api.dependencies import get_current_user
from src.api.exceptions import UserNotFoundError, ValidationError
from src.api.schemas.editor_auto import (
    EditorUserCreateRequest,
    EditorUserResponse,
    EditorUserUpdateRequest,
    SubscriptionResponse,
    ToolStepIn,
    UsageResponse,
)
from src.editor_auto.config import (
    TOOL_EXCLUSIVE_GROUPS,
    ensure_user_folders,
    user_folder,
    user_output_folder,
)
from src.editor_auto.models import EditorUser, ReferralUse, ToolStep
from src.editor_auto.repos import PlanRepo, ReferralRepo, UserRepo
from src.editor_auto.tools import REGISTRY


router = APIRouter(
    prefix="/api/v1/editor-auto/users",
    tags=["editor-auto · users"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(u: EditorUser) -> EditorUserResponse:
    # Recalcula `drive_folder` y `output_folder` dinámicamente en cada GET
    # — así si la raíz cambia (env var nueva, autodetect mejorado), los
    # users existentes apuntan al sitio correcto SIN tener que migrar
    # nada en Redis. El campo `u.drive_folder` que viene de la BD se
    # mantiene como referencia histórica pero no se devuelve al cliente.
    sub_dto: SubscriptionResponse | None = None
    usage_dto: UsageResponse | None = None
    if u.subscription is not None:
        plan = PlanRepo().get(u.subscription.plan_id)
        sub_dto = SubscriptionResponse(
            plan_id=u.subscription.plan_id,
            plan_slug=plan.slug if plan else "?",
            plan_name=plan.name if plan else "(plan eliminado)",
            status=u.subscription.status,
            started_at=u.subscription.started_at,
            current_period_start=u.subscription.current_period_start,
            current_period_end=u.subscription.current_period_end,
            discount_pct_next_period=u.subscription.discount_pct_next_period,
            notes=u.subscription.notes,
        )
        usage_dto = UsageResponse(
            daily_videos_used=u.usage.daily_videos_used,
            monthly_videos_used=u.usage.monthly_videos_used,
            total_videos_ever=u.usage.total_videos_ever,
            last_reset_date=u.usage.last_reset_date,
            month_period=u.usage.month_period,
            last_enqueue_at=u.usage.last_enqueue_at,
            daily_limit=plan.daily_video_limit if plan else None,
            monthly_limit=plan.monthly_video_limit if plan else None,
        )
    else:
        # Test user: aún muestro contadores históricos
        usage_dto = UsageResponse(
            daily_videos_used=u.usage.daily_videos_used,
            monthly_videos_used=u.usage.monthly_videos_used,
            total_videos_ever=u.usage.total_videos_ever,
            last_reset_date=u.usage.last_reset_date,
            month_period=u.usage.month_period,
            last_enqueue_at=u.usage.last_enqueue_at,
            daily_limit=None,
            monthly_limit=None,
        )

    referrals_count = 0
    if u.referral_code:
        ref = ReferralRepo().get(u.referral_code)
        if ref:
            referrals_count = len(ref.uses)

    return EditorUserResponse(
        id=u.id,
        name=u.name,
        display_name=u.display_name,
        description=u.description,
        tool_flow=[ToolStepIn(**s.model_dump()) for s in u.tool_flow],
        drive_folder=user_folder(u.name) if u.name else None,
        output_folder=user_output_folder(u.name) if u.name else None,
        auto_enqueue=u.auto_enqueue,
        subscription=sub_dto,
        usage=usage_dto,
        referral_code=u.referral_code,
        referred_by_code=u.referred_by_code,
        referrals_count=referrals_count,
        deleted=u.deleted,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


def _validate_steps(steps: list[ToolStepIn]) -> list[ToolStep]:
    """Valida que cada step apunte a una herramienta registrada y
    convierte a `ToolStep` interno. Aplica también las reglas de
    exclusión mutua de `TOOL_EXCLUSIVE_GROUPS` (ej. silence_cutter vs
    silence_cutter_scripted no pueden coexistir habilitados en el mismo
    flujo — la 1ª mutila el input de la 2ª)."""
    out: list[ToolStep] = []
    for s in steps:
        if s.tool_id not in REGISTRY:
            raise ValidationError(
                f"Herramienta desconocida: '{s.tool_id}'",
                details={"valid_tool_ids": list(REGISTRY.keys())},
            )
        out.append(ToolStep(
            tool_id=s.tool_id, enabled=s.enabled, config=s.config or {},
        ))
    enabled_ids = {s.tool_id for s in out if s.enabled}
    for group in TOOL_EXCLUSIVE_GROUPS:
        clash = enabled_ids & group
        if len(clash) > 1:
            raise ValidationError(
                "Estas herramientas no son compatibles entre sí en el mismo "
                f"flujo: {sorted(clash)}. Deshabilita o elimina una.",
                details={
                    "conflicting_tool_ids": sorted(clash),
                    "exclusive_group": sorted(group),
                },
            )
    return out


@router.get("", response_model=list[EditorUserResponse])
def list_users(include_deleted: bool = False) -> list[EditorUserResponse]:
    repo = UserRepo()
    users = repo.list_all(include_deleted=include_deleted)
    return [_to_response(u) for u in users]


@router.get("/{user_id}", response_model=EditorUserResponse)
def get_user(user_id: str) -> EditorUserResponse:
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}",
            details={"user_id": user_id},
        )
    return _to_response(u)


@router.post("", response_model=EditorUserResponse,
             status_code=status.HTTP_201_CREATED)
def create_user(payload: EditorUserCreateRequest) -> EditorUserResponse:
    repo = UserRepo()
    if repo.get_by_name(payload.name) is not None:
        raise ValidationError(
            f"Ya existe un usuario con el nombre '{payload.name}'",
            details={"name": payload.name},
        )
    steps = _validate_steps(payload.tool_flow)
    # Crear carpetas en Drive sincronizado ANTES de guardar en Redis, así
    # `resolve_editor_root` tiene chance de auto-detectar el padre y crear
    # TIKTOK_EDITOR como hermana de TIKTOK_CR/TIKTOK_SHOP. Si Drive no
    # está accesible cae al fallback local (visible en el path devuelto).
    try:
        ensure_user_folders(payload.name)
    except OSError as e:
        print(f"[editor_auto.users] ensure_user_folders falló: {e}")
    # Validar referido si lo trae
    referred_code = (payload.referred_by_code or "").strip().upper() or None
    ref_repo = ReferralRepo()
    referrer_ref = None
    if referred_code:
        referrer_ref = ref_repo.get(referred_code)
        if referrer_ref is None:
            raise ValidationError(
                f"Código de referido '{referred_code}' no existe",
                details={"referred_by_code": referred_code},
            )

    user = EditorUser(
        name=payload.name,
        display_name=payload.display_name or payload.name,
        description=payload.description,
        tool_flow=steps,
        drive_folder=user_folder(payload.name),
        referred_by_code=referred_code,
    )
    repo.save(user)

    # Tras crear el user, anotamos el uso del code en el owner. El descuento
    # se aplica al siguiente período de facturación del owner.
    if referrer_ref is not None:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        # Próximo mes en YYYY-MM
        year = now.year + (1 if now.month == 12 else 0)
        month = 1 if now.month == 12 else now.month + 1
        next_period = f"{year:04d}-{month:02d}"
        # Cap a 50% por owner-mes — discount_for_period() ya lo limita,
        # pero aquí ya damos un 25% por uso (estándar). Si owner ya tiene
        # 2+ usos para next_period, el 3º+ no aporta más al cap.
        use = ReferralUse(
            referred_user_id=user.id,
            referred_user_name=user.name,
            discount_pct_applied=0.25,
            valid_until_period=next_period,
        )
        ref_repo.add_use(referrer_ref.code, use)
        # Si el owner tiene suscripción, le propagamos el discount acumulado.
        owner = repo.get(referrer_ref.owner_user_id)
        if owner and owner.subscription:
            updated_ref = ref_repo.get(referrer_ref.code)
            if updated_ref:
                owner.subscription.discount_pct_next_period = (
                    updated_ref.discount_for_period(next_period)
                )
                repo.save(owner)
    return _to_response(user)


@router.patch("/{user_id}", response_model=EditorUserResponse)
def update_user(
    user_id: str, payload: EditorUserUpdateRequest,
) -> EditorUserResponse:
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}",
            details={"user_id": user_id},
        )
    if payload.display_name is not None:
        u.display_name = payload.display_name
    if payload.description is not None:
        u.description = payload.description
    if payload.tool_flow is not None:
        u.tool_flow = _validate_steps(payload.tool_flow)
    if payload.auto_enqueue is not None:
        u.auto_enqueue = bool(payload.auto_enqueue)
    # Asegurar carpetas en Drive — idempotente. Cubre el caso de users
    # creados antes de que `resolve_editor_root` supiera autodetectar el
    # padre del Drive (entonces cayeron al fallback local).
    try:
        ensure_user_folders(u.name)
    except OSError as e:
        print(f"[editor_auto.users] ensure_user_folders falló en PATCH: {e}")
    repo.save(u)
    return _to_response(u)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, hard: bool = False) -> None:
    repo = UserRepo()
    ok = repo.delete(user_id, hard=hard)
    if not ok:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}",
            details={"user_id": user_id},
        )
