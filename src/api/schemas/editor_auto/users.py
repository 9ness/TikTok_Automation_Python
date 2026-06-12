"""Schemas Pydantic para users del programa Editor Auto."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .billing import SubscriptionResponse, UsageResponse


class ToolStepIn(BaseModel):
    """ToolStep tal y como llega del frontend."""

    tool_id: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class EditorUserCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    display_name: str = ""
    description: str = ""
    tool_flow: list[ToolStepIn] = Field(default_factory=list)
    # Si el cliente se registra con un código de otro usuario, indícalo aquí.
    # El backend valida que existe y registra el `ReferralUse` para que el
    # owner reciba descuento el próximo mes.
    referred_by_code: str | None = None


class EditorUserUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    tool_flow: list[ToolStepIn] | None = None
    auto_enqueue: bool | None = None
    # Overrides por usuario (None = no tocar). Para limpiar un override a
    # "usar el del plan" se manda -1 en los int-nullable (lo traduce el handler).
    auto_enqueue_delay_minutes: int | None = None
    daily_video_limit_override: int | None = None
    window_start_hour_override: int | None = None
    window_end_hour_override: int | None = None
    # Email de la cuenta web (nebulabs-media) a vincular. "" = desvincular.
    account_email: str | None = None
    # Revisión manual: True → los vídeos editados van a `revision/` (no a
    # `salida/`) hasta que el admin los apruebe. None = no tocar.
    manual_review: bool | None = None


class WebAccountResponse(BaseModel):
    """Cuenta web (nebulabs-media) vinculada — leída de `nebulabs:user:*`."""

    email: str
    name: str = ""
    picture: str | None = None
    role: str = "standard"          # standard | plus | pro | admin
    plan_id: str | None = None      # id de tarifa contratada (o None = trial)
    trial_videos: int = 0
    banned: bool = False
    created_at: str | None = None
    last_login_at: str | None = None
    # id del EditorUser vinculado (si existe). None = aún sin usuario de
    # edición → el admin puede crearlo con "provision-from-web".
    linked_editor_user_id: str | None = None
    linked_editor_user_name: str | None = None


class ProvisionFromWebRequest(BaseModel):
    """Crea (o reutiliza) un EditorUser a partir de una cuenta web por email."""
    email: str


class WebAccountRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(standard|plus|pro|admin)$")


class WebAccountPlanRequest(BaseModel):
    plan_id: str | None = None      # None/"" = solo trial


class WebAccountBanRequest(BaseModel):
    banned: bool


class EditorUserResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    tool_flow: list[ToolStepIn]
    drive_folder: str | None
    output_folder: str | None
    auto_enqueue: bool = False
    auto_enqueue_delay_minutes: int = 0
    daily_video_limit_override: int | None = None
    window_start_hour_override: int | None = None
    window_end_hour_override: int | None = None
    output_released_on: str | None = None
    auto_revoke_output_daily: bool = True
    manual_review: bool = False
    # Puente con la web de cliente (nebulabs-media)
    account_email: str | None = None
    web_account: "WebAccountResponse | None" = None
    # Billing
    subscription: SubscriptionResponse | None = None
    usage: UsageResponse | None = None
    referral_code: str | None = None
    referred_by_code: str | None = None
    referrals_count: int = 0
    deleted: bool
    created_at: str
    updated_at: str


class ReferralRegisterRequest(BaseModel):
    """Validar y opcionalmente reservar un code al crear/editar user."""
    code: str = Field(..., min_length=4, max_length=20)
