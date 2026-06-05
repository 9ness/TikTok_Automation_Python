"""CRUD de usuarios del programa Editor Auto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

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
from src.api.schemas.editor_auto.users import (
    ProvisionFromWebRequest,
    WebAccountBanRequest,
    WebAccountPlanRequest,
    WebAccountResponse,
    WebAccountRoleRequest,
)
from src.editor_auto.config import (
    TOOL_EXCLUSIVE_GROUPS,
    ensure_user_folders,
    user_folder,
    user_output_folder,
)
from src.editor_auto.models import EditorUser, ReferralUse, ToolStep
from src.editor_auto.repos import PlanRepo, ReferralRepo, UserRepo
from src.editor_auto.repos.web_account_repo import get_web_account_repo
from src.editor_auto.tools import REGISTRY


def _web_account_dto(account: dict | None) -> WebAccountResponse | None:
    """Mapea el JSON crudo de `nebulabs:user:*` (camelCase del front) al DTO.
    Enriquece con el EditorUser vinculado (si lo hay) por account_email."""
    if not account:
        return None
    email = account.get("email", "")
    linked = UserRepo().get_by_account_email(email) if email else None
    return WebAccountResponse(
        email=email,
        name=account.get("name", ""),
        picture=account.get("picture"),
        role=account.get("role", "standard"),
        plan_id=account.get("planId"),
        trial_videos=int(account.get("trialVideos") or 0),
        banned=bool(account.get("banned")),
        created_at=account.get("createdAt"),
        last_login_at=account.get("lastLoginAt"),
        linked_editor_user_id=linked.id if linked else None,
        linked_editor_user_name=linked.name if linked else None,
    )


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
        auto_enqueue_delay_minutes=u.auto_enqueue_delay_minutes,
        daily_video_limit_override=u.daily_video_limit_override,
        window_start_hour_override=u.window_start_hour_override,
        window_end_hour_override=u.window_end_hour_override,
        output_released_on=u.output_released_on,
        auto_revoke_output_daily=u.auto_revoke_output_daily,
        account_email=u.account_email,
        web_account=_web_account_dto(
            get_web_account_repo().get(u.account_email)
        ) if u.account_email else None,
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


class SettingsResponse(BaseModel):
    send_cutoff_hour: int


class CutoffRequest(BaseModel):
    send_cutoff_hour: int


# IMPORTANTE: rutas estáticas ANTES de "/{user_id}" o este las captura (404).
@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Ajustes globales del Editor Auto (hora de cierre de envíos…)."""
    from src.editor_auto.config import send_cutoff_hour
    return SettingsResponse(send_cutoff_hour=send_cutoff_hour())


@router.patch("/settings/cutoff", response_model=SettingsResponse)
def set_cutoff(payload: CutoffRequest) -> SettingsResponse:
    """Cambia la hora de cierre diaria (0-23, Europe/Madrid). Se guarda en Redis."""
    from src.editor_auto.config import set_send_cutoff_hour
    if not 0 <= payload.send_cutoff_hour <= 23:
        raise ValidationError("La hora debe estar entre 0 y 23.", details={"hour": payload.send_cutoff_hour})
    h = set_send_cutoff_hour(payload.send_cutoff_hour)
    return SettingsResponse(send_cutoff_hour=h)


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
    if payload.auto_enqueue_delay_minutes is not None:
        u.auto_enqueue_delay_minutes = max(0, int(payload.auto_enqueue_delay_minutes))
    if payload.daily_video_limit_override is not None:
        # -1 = limpiar override (usar el del plan).
        v = int(payload.daily_video_limit_override)
        u.daily_video_limit_override = None if v < 0 else v
    if payload.window_start_hour_override is not None:
        v = int(payload.window_start_hour_override)
        u.window_start_hour_override = None if v < 0 else max(0, min(23, v))
    if payload.window_end_hour_override is not None:
        v = int(payload.window_end_hour_override)
        u.window_end_hour_override = None if v < 0 else max(0, min(23, v))
    if payload.account_email is not None:
        # "" = desvincular. Si no, normaliza y valida que sea un email.
        em = payload.account_email.strip().lower()
        if em and "@" not in em:
            raise ValidationError(
                f"Email de cuenta web inválido: '{em}'",
                details={"account_email": em},
            )
        u.account_email = em or None
    # Asegurar carpetas en Drive — idempotente. Cubre el caso de users
    # creados antes de que `resolve_editor_root` supiera autodetectar el
    # padre del Drive (entonces cayeron al fallback local).
    try:
        ensure_user_folders(u.name)
    except OSError as e:
        print(f"[editor_auto.users] ensure_user_folders falló en PATCH: {e}")
    repo.save(u)
    return _to_response(u)


class ReleaseDayRequest(BaseModel):
    count: int | None = None          # nº de vídeos del día (para el email)
    emails: list[str] | None = None   # override; default = known_share_emails


@router.post("/{user_id}/release-day")
def release_day(user_id: str, payload: ReleaseDayRequest | None = None) -> dict:
    """Marca los vídeos del día como LISTOS: da acceso a la carpeta de
    salida a los emails conocidos del usuario y les manda un email
    'tus vídeos del día están listos'. Idempotente.

    Si Drive no está configurado → solo intenta el email. Si SMTP no está
    configurado → solo comparte la carpeta. Nunca rompe.
    """
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}", details={"user_id": user_id},
        )
    emails = list(payload.emails) if (payload and payload.emails) else list(u.known_share_emails)
    emails = [e.strip() for e in emails if e and "@" in e]
    result: dict = {"shared": [], "share_errors": [], "emails": emails, "email": None}
    if not emails:
        result["warning"] = (
            "el usuario no tiene emails conocidos a los que dar acceso "
            "(comparte la carpeta con su email al menos una vez)"
        )
        return result

    from src.editor_auto.services import drive_sharing, email_notify

    folder_link: str | None = None
    if drive_sharing.is_configured():
        for email in emails:
            try:
                drive_sharing.share_folders(u.name, email, folders=["salida"], notify=False)
                result["shared"].append(email)
            except Exception as e:
                result["share_errors"].append(f"{email}: {e}")
        try:
            fid = drive_sharing._subfolder_id(u.name, "salida")  # noqa: SLF001
            folder_link = f"https://drive.google.com/drive/folders/{fid}"
        except Exception:
            folder_link = None
    else:
        result["share_errors"].append("Drive sharing no configurado")

    # Nº de vídeos = los realmente editados HOY en salida (ignora leftovers de
    # días anteriores). Fallback al count del payload si no se puede contar.
    from src.editor_auto import config as _ea_config
    count_today = _ea_config.count_output_videos_today(u.name)
    if count_today is None:
        count_today = payload.count if payload else None
    result["videos_today"] = count_today
    result["email"] = email_notify.send_videos_ready(
        to=emails,
        client_name=u.display_name or u.name,
        count=count_today,
        folder_link=folder_link,
    )
    # Registrar el día del acceso para que el watcher lo revoque al cambiar
    # de día (si auto_revoke_output_daily). Solo si se compartió algo.
    if result["shared"]:
        u.output_released_on = datetime.now(timezone.utc).date().isoformat()
        repo.save(u)
        result["output_released_on"] = u.output_released_on
    return result


# ───────────────────────────── Cuentas web ──────────────────────────────
# Puente con nebulabs-media: el admin gestiona rol/plan/ban de la cuenta web
# (datos en `nebulabs:user:*`) desde el panel de configuración, por email.


@router.get("/web-accounts/all", response_model=list[WebAccountResponse])
def list_web_accounts() -> list[WebAccountResponse]:
    """Todas las cuentas registradas en la web de cliente.

    Auto-provisiona (idempotente) el EditorUser de cada cuenta verificada
    no-admin, así el cliente aparece en Usuarios sin que el admin pulse nada.
    """
    from src.editor_auto.services.provision_service import provision_from_web
    repo = get_web_account_repo()
    out: list[WebAccountResponse] = []
    for a in repo.list_all():
        if not a:
            continue
        email = (a.get("email") or "").strip().lower()
        # Solo cuentas reales (email verificado) y que no sean admin.
        if email and a.get("role") != "admin" and a.get("emailVerified"):
            try:
                provision_from_web(email)
            except Exception as e:
                print(f"[editor_auto.users] auto-provision falló para {email}: {e}")
        dto = _web_account_dto(a)
        if dto:
            out.append(dto)
    return out


@router.post("/web-accounts/provision", response_model=EditorUserResponse,
             status_code=status.HTTP_201_CREATED)
def provision_from_web(payload: ProvisionFromWebRequest) -> EditorUserResponse:
    """Crea (o devuelve) el EditorUser vinculado a una cuenta web por email.
    Idempotente. El mismo servicio se usa para la auto-provisión de la subida
    web, así que el botón manual y el automático comparten lógica."""
    from src.editor_auto.services.provision_service import provision_from_web as _provision
    email = payload.email.strip().lower()
    if "@" not in email:
        raise ValidationError("Email inválido.", details={"email": email})
    user = _provision(email)
    if user is None:
        raise UserNotFoundError(
            "No existe una cuenta web con ese email (¿ha entrado el cliente en la web?).",
            details={"email": email},
        )
    return _to_response(user)


def _web_or_404(account: dict | None, email: str) -> WebAccountResponse:
    if account is None:
        raise UserNotFoundError(
            f"Cuenta web no encontrada: {email}", details={"email": email},
        )
    return _web_account_dto(account)  # type: ignore[return-value]


@router.get("/web-accounts/{email}", response_model=WebAccountResponse)
def get_web_account(email: str) -> WebAccountResponse:
    return _web_or_404(get_web_account_repo().get(email), email)


@router.patch("/web-accounts/{email}/role", response_model=WebAccountResponse)
def set_web_account_role(email: str, payload: WebAccountRoleRequest) -> WebAccountResponse:
    return _web_or_404(get_web_account_repo().set_role(email, payload.role), email)


@router.patch("/web-accounts/{email}/plan", response_model=WebAccountResponse)
def set_web_account_plan(email: str, payload: WebAccountPlanRequest) -> WebAccountResponse:
    plan_id = (payload.plan_id or "").strip() or None
    return _web_or_404(get_web_account_repo().set_plan(email, plan_id), email)


@router.patch("/web-accounts/{email}/ban", response_model=WebAccountResponse)
def set_web_account_ban(email: str, payload: WebAccountBanRequest) -> WebAccountResponse:
    return _web_or_404(get_web_account_repo().set_banned(email, payload.banned), email)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, hard: bool = False) -> None:
    repo = UserRepo()
    ok = repo.delete(user_id, hard=hard)
    if not ok:
        raise UserNotFoundError(
            f"Usuario no encontrado: {user_id}",
            details={"user_id": user_id},
        )
