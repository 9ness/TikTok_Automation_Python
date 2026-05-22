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
    """Resultado del análisis: config preset + detected data + coste real.

    `video_preset` se rellena cuando el caller pasa `target_kind` en
    {auto_video, veo3} → es un VideoPreset completo listo para añadir a
    `product.video_presets[]` (con prompts Seedance/Veo3, fotos elegidas,
    overlays, subs, voz, etc.). Si es None, solo se generó el config
    legacy ShopPreset.
    """

    config: dict[str, Any]
    detected: dict[str, Any]
    cost_breakdown: dict[str, Any]
    video_preset: dict[str, Any] | None = None
