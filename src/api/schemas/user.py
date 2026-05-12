"""Schemas Pydantic de usuarios TikTok para la API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.tiktok_shop.utils.validators import validate_tiktok_username


TierName = Literal["standard", "advanced", "pro", "veo3_prompt_only"]
UserStatus = Literal["pilot", "graduated"]


def _normalize_username(v: str) -> str:
    """Normaliza username asegurando prefijo `@`."""
    v = v.strip()
    if not v.startswith("@"):
        v = f"@{v}"
    ok, err = validate_tiktok_username(v)
    if not ok:
        raise ValueError(err)
    return v


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    """Crea un usuario TikTok. `username` se normaliza añadiendo `@` si falta."""

    username: str
    display_name: str = Field(..., min_length=1, max_length=80)
    niche: str = "otros"
    language: str = "es"
    country: str = "ES"
    followers_count: int = Field(default=0, ge=0)
    creator_health_rating: int = Field(default=200, ge=0, le=300)
    default_voice_id: str | None = None
    default_language: str = "es"
    default_video_tier: TierName = "standard"

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        return _normalize_username(v)


class UserUpdate(BaseModel):
    """PATCH parcial — todos los campos opcionales (excepto `username`,
    que es la clave URL y no se cambia por aquí)."""

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    niche: str | None = None
    language: str | None = None
    country: str | None = None
    followers_count: int | None = Field(default=None, ge=0)
    creator_health_rating: int | None = Field(default=None, ge=0, le=300)
    status: UserStatus | None = None
    default_voice_id: str | None = None
    default_language: str | None = None
    default_video_tier: TierName | None = None


class AssignProductRequest(BaseModel):
    product_id: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    niche: str
    language: str
    country: str
    status: UserStatus
    followers_count: int
    creator_health_rating: int
    pilot_program: dict[str, Any]
    drive_folder: str | None = None
    assigned_products: list[str]
    default_voice_id: str | None = None
    default_language: str
    default_video_tier: TierName
    deleted: bool = False
    created_at: str
    updated_at: str


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int


class PilotRequirement(BaseModel):
    """Una vía de graduación con su estado."""

    name: str  # "via_a_5000_followers" / "via_b_videos_quiz_chr" / "via_c_orders_30d"
    label: str  # human-readable
    met: bool
    missing: list[str] = Field(default_factory=list)


class PilotProgressResponse(BaseModel):
    username: str
    status: UserStatus
    days_in_program: int
    shoppable_videos_count: int
    current_chr: int
    orders_count: int
    followers: int
    weekly_shoppable_used: int
    weekly_shoppable_remaining: int
    weekly_reset_at: str | None = None
    quiz_passed: bool
    graduation_status: Literal["eligible", "not_eligible", "graduated"]
    days_until_eligible: int | None = None  # solo si todas las vías exigen >=30 días
    requirements_met: list[PilotRequirement]
