"""Schemas Pydantic de la biblioteca de voces."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceResponse(BaseModel):
    id: str
    name: str
    minimax_voice_id: str
    language: str
    tags: list[str] = Field(default_factory=list)
    is_preset: bool = False
    sample_local_path: str | None = None
    created_at: str


class VoiceListResponse(BaseModel):
    items: list[VoiceResponse]
    total: int
