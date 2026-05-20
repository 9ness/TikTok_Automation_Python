"""Schemas para presets TikTok Shop (usuario × producto × modo)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ShopPresetResponse(BaseModel):
    name: str
    config: dict[str, Any]


class ShopPresetListResponse(BaseModel):
    items: list[str]
    total: int


# ---------------------------------------------------------------------------
# Fase 5 — Replicar viral
# ---------------------------------------------------------------------------
class ReplicateViralResponse(BaseModel):
    """Resultado del análisis: config preset + detected data + coste real."""

    config: dict[str, Any]
    detected: dict[str, Any]
    cost_breakdown: dict[str, Any]
