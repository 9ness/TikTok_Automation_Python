"""Modelo de voz clonada (catálogo de voces disponibles para los vídeos)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoiceClone(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    minimax_voice_id: str  # Spanish_EnergeticBoy o un voice_id de clone
    language: str = "es"
    tags: list[str] = Field(default_factory=list)
    is_preset: bool = False  # True para voces preset MiniMax (no clonadas)
    sample_local_path: str | None = None
    created_at: str = Field(default_factory=_now_iso)
