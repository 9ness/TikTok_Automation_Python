"""Schemas Pydantic del nicho 🏛️ Presidentes Top 5."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PrefixWord = Literal["The", "Top"]
TopCount = Literal[3, 4, 5]
ResolutionLabel = Literal[
    "1080p (Lento)", "720p (Medio)", "480p (Rápido)", "240p (Ultra Rápido)",
]
EngineVersion = Literal["v1_estable", "v2_estable"]


# ---------------------------------------------------------------------------
# Subs / Hook config (presets de la UI)
# ---------------------------------------------------------------------------
class PresidentsSubsConfig(BaseModel):
    """Estilo de subtítulos karaoke. Replica los campos del Streamlit."""

    enabled: bool = False
    font_choice: str = "Impact"  # nombre amigable; el router mapea a font_path
    highlight_color: str = "#BB0808"
    text_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = Field(default=3, ge=0, le=10)
    case_mode: Literal["UPPERCASE", "lowercase", "Title Case", "None"] = "UPPERCASE"
    font_scale: float = Field(default=0.040, gt=0.0, le=0.2)
    max_words: int = Field(default=4, ge=1, le=10)
    y_position: float = Field(default=0.62, ge=0.0, le=1.0)
    shadow_enabled: bool = False
    shadow_color: str = "#000000"
    shadow_opacity: float = Field(default=0.8, ge=0.0, le=1.0)
    shadow_blur: float = Field(default=33.0, ge=0.0, le=100.0)
    shadow_distance: float = Field(default=8.0, ge=0.0, le=100.0)
    shadow_angle: float = Field(default=-45.0, ge=-360.0, le=360.0)
    highlight_mode: Literal["pill", "color_swap", "underline", "box_outline", "glow", "none"] = "pill"
    max_width: float = Field(default=0.85, gt=0.0, le=1.0)


class PresidentsHookConfig(BaseModel):
    """Hook box que aparece los primeros N segundos."""

    enabled: bool = False
    duration: float = Field(default=5.0, ge=0.5, le=30.0)
    animation: Literal["swipe_left", "swipe_right", "fade_in", "pop", "none"] = "swipe_left"
    y_position: float = Field(default=0.33, ge=0.0, le=1.0)
    shadow_color: str = "#BB0808"
    box_color: str = "#FFFFFF"
    text_color: str = "#0B0B0B"
    font_scale: float = Field(default=0.020, gt=0.0, le=0.1)


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------
class PresidentsEnqueueItem(BaseModel):
    """Un vídeo a generar. La UI Streamlit permite encolar 1-10 items
    en un solo lote — replicamos el mismo patrón."""

    topic: str | None = Field(
        default=None,
        description="Tema del ranking. Vacío/None → tema aleatorio.",
    )
    prefix: PrefixWord = "The"
    top_count: TopCount = 5
    include_history: bool = True
    include_hook: bool = True


class PresidentsEnqueueRequest(BaseModel):
    items: list[PresidentsEnqueueItem] = Field(..., min_length=1, max_length=10)
    creative_mode: bool = False
    engine_version: EngineVersion = "v2_estable"
    resolution: ResolutionLabel = "1080p (Lento)"
    subs: PresidentsSubsConfig = Field(default_factory=PresidentsSubsConfig)
    hook: PresidentsHookConfig = Field(default_factory=PresidentsHookConfig)


class PresidentsBatchEnqueueResponse(BaseModel):
    """Cada item del lote produce un job. Devolvemos la lista de job_ids."""

    jobs: list[dict[str, Any]]  # [{job_id, position_in_queue, title}]
    total_enqueued: int


# ---------------------------------------------------------------------------
# Presets (configs_store)
# ---------------------------------------------------------------------------
class PresidentsPresetResponse(BaseModel):
    name: str
    config: dict[str, Any]


class PresidentsPresetListResponse(BaseModel):
    items: list[str]  # nombres
    total: int
