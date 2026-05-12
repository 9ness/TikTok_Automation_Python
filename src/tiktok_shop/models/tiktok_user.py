"""Modelo de cuenta TikTok afiliada (publica los vídeos)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PilotProgramState(BaseModel):
    """Estado de la cuenta dentro del Pilot Program de TikTok Shop España.

    Las reglas de graduación están en `src/tiktok_shop/services/pilot_tracker.py`.
    Este modelo solo guarda el estado bruto.
    """

    started_at: str = Field(default_factory=_now_iso)
    shoppable_videos_published: int = 0
    orders_generated: int = 0
    quiz_passed: bool = False
    graduation_eligible: bool = False
    weekly_shoppable_remaining: int = 5
    weekly_shoppable_reset_at: str | None = None  # ISO date del próximo lunes


class TikTokUser(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    username: str  # con @
    display_name: str
    niche: str = "otros"
    language: str = "es"
    country: str = "ES"
    status: Literal["pilot", "graduated"] = "pilot"
    followers_count: int = 0
    creator_health_rating: int = 200
    pilot_program: PilotProgramState = Field(default_factory=PilotProgramState)
    drive_folder: str | None = None  # path local en Drive sincronizado
    assigned_products: list[str] = Field(default_factory=list)  # product ids
    default_voice_id: str | None = None
    default_language: str = "es"
    default_video_tier: Literal["standard", "advanced", "pro", "veo3_prompt_only"] = "standard"
    deleted: bool = False                     # soft-delete: oculta sin tocar Drive/Redis
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()
