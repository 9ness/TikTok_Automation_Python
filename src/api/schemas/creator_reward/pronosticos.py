"""Schemas Pydantic del nicho 📊 Pronósticos Diarios."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(v: str) -> str:
    if not DATE_RE.match(v):
        raise ValueError(f"Fecha debe estar en formato YYYY-MM-DD: '{v}'")
    return v


# ---------------------------------------------------------------------------
# Versiones del payload Redis
# ---------------------------------------------------------------------------
class PronosticosVersionItem(BaseModel):
    """Una versión del guion para una fecha. Mapea el shape de Redis
    `daily_bets_tiktok_video:YYYY-MM[YYYY-MM-DD]`."""

    id: str
    trigger: str | None = None  # "cron" | "manual" | "legacy"
    mode: str | None = None      # "single_match" | "multi_match"
    word_count: int | None = None
    estimated_duration_s: float | None = None
    picks_count: int = 0
    script: str = ""
    title: str | None = None
    competition_focus: str | None = None
    is_selected: bool = False


class PronosticosVersionsResponse(BaseModel):
    date: str
    payload_exists: bool
    versions: list[PronosticosVersionItem]
    selected_version_id: str | None = None


class PronosticosLatestDateResponse(BaseModel):
    latest_date: str | None = None  # null si no se encuentra ninguna en 14 días


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------
class PronosticosAudioConfig(BaseModel):
    add_subtitles: bool = True
    add_money_sfx: bool = True
    sfx_volume: float = Field(default=0.55, ge=0.0, le=1.0)
    add_clink_sfx: bool = True
    clink_volume: float = Field(default=0.35, ge=0.0, le=1.0)
    add_camera_sfx: bool = True
    camera_volume: float = Field(default=0.45, ge=0.0, le=1.0)
    add_background_music: bool = True
    bgm_volume: float = Field(default=0.20, ge=0.0, le=1.0)
    # Velocidad de la voz en el estilo viral (atempo). 1.0 = normal, 1.2 = más
    # rápida/corta. Permite ajustar la duración del vídeo desde la UI.
    voice_speed: float = Field(default=1.2, ge=0.5, le=2.0)


class PronosticosOverlaysConfig(BaseModel):
    use_intro_folder: bool = False
    add_league_overlay: bool = True
    league_overlay_duration: float = Field(default=3.0, ge=0.5, le=10.0)
    saturation: float = Field(default=1.25, ge=0.5, le=2.0)
    show_pick_carousel: bool = False
    # Estilo de vídeo: "standard" (histórico, intacto) o "viral" (overlays nuevos).
    video_style: Literal["standard", "viral"] = "standard"
    # Fotos elegidas a mano (estilo viral): {"hook": "Equipo/archivo.jpg", "1": ...,
    # "2": ...}. Si falta una clave, el render cae a la foto automática.
    photo_overrides: dict[str, str] | None = None

    # --- Posiciones de los overlays (0.0 = top, 1.0 = bottom) ---
    # Todos opcionales con los defaults históricos del pipeline. Se exponen
    # vía la UI con un preview 9:16 drag-to-position para que el usuario
    # ajuste sin tocar código. Si no se manda, el pipeline cae a defaults.
    subtitle_y_pct: float = Field(default=0.78, ge=0.0, le=1.0)
    league_overlay_y_pct: float = Field(default=0.30, ge=0.0, le=1.0)
    league_logo_height_pct: float = Field(default=0.13, ge=0.05, le=0.40)
    team_shield_y_pct: float = Field(default=0.43, ge=0.0, le=1.0)
    team_shield_height_pct: float = Field(default=0.22, ge=0.05, le=0.40)
    team_shield_x_inset_pct: float = Field(default=0.06, ge=0.0, le=0.30)
    profile_cta_y_pct: float = Field(default=0.36, ge=0.0, le=1.0)
    profile_cta_height_pct: float = Field(default=0.32, ge=0.05, le=0.50)


class PronosticosEnqueueRequest(BaseModel):
    target_date: str = Field(..., description="YYYY-MM-DD")
    version_ids: list[str] = Field(
        ...,
        min_length=1,
        description="IDs de versiones a generar. 'legacy' permitido para payload viejo.",
    )
    voice_id_override: str | None = Field(
        default=None,
        description="Voice ID MiniMax. Vacío → usa PRONOSTICOS_VOICE_ID del .env.",
    )
    script_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="{version_id: texto_editado}. Solo afecta a las versiones listadas.",
    )
    video_size: tuple[int, int] = Field(default=(1080, 1920))
    publish_to_redis: bool = False
    audio: PronosticosAudioConfig = Field(default_factory=PronosticosAudioConfig)
    overlays: PronosticosOverlaysConfig = Field(default_factory=PronosticosOverlaysConfig)

    @field_validator("target_date")
    @classmethod
    def _validate_target_date(cls, v: str) -> str:
        return _validate_date(v)


class PronosticosBatchEnqueueResponse(BaseModel):
    jobs: list[dict[str, Any]]  # [{job_id, position_in_queue, version_id, title}]
    total_enqueued: int
