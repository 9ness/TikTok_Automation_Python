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


class EditorUserResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    tool_flow: list[ToolStepIn]
    drive_folder: str | None
    output_folder: str | None
    auto_enqueue: bool = False
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
