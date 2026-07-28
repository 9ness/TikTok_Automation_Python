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


class CarpetasListResponse(BaseModel):
    """Carpetas ya creadas bajo VIRALIZACION, para elegir dónde guardar."""

    items: list[str]


class StyleChoice(BaseModel):
    key: str
    label: str


class StylesListResponse(BaseModel):
    items: list[StyleChoice]


class RoundPlan(BaseModel):
    """Cuántos vídeos caen en cada ronda con el reparto actual."""

    ronda: int
    n_videos: int
    default_style: str


class RoundPlanResponse(BaseModel):
    total_videos: int
    rounds: list[RoundPlan]


class ViralizacionGenerateRequest(BaseModel):
    ponentes: list[str] = Field(..., min_length=1)
    cantidad: dict[str, int]
    nombre_cuenta: str = Field(..., min_length=1)
    music_rounds: int = 1
    # Estilo por ronda: `round_styles[i]` es la ronda i+1. Vacío = rotación
    # automática. Lo que falte también cae en la rotación.
    round_styles: list[str] = Field(default_factory=list)


class ViralizacionGenerateResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int
    total_videos: int
