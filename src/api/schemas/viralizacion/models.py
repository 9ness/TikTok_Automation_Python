"""Schemas Pydantic del Programa 4 — Viralización."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PonenteInfo(BaseModel):
    slug: str
    label: str
    n_audios: int
    hooks_available: int
    hooks_total: int
    paisajes_available: int
    paisajes_total: int


class PonentesListResponse(BaseModel):
    items: list[PonenteInfo]


class ViralizacionGenerateRequest(BaseModel):
    ponentes: list[str] = Field(..., min_length=1)
    cantidad: dict[str, int]
    nombre_cuenta: str = Field(..., min_length=1)
    music_rounds: int = 1


class ViralizacionGenerateResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int
    total_videos: int
