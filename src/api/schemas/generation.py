"""Schemas de generaciones de vídeo (histórico) + encolado + regeneración."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


TierName = Literal["standard", "advanced", "pro", "veo3_prompt_only", "nano_banana_prompt_only"]
GenerationStatusValue = Literal[
    "pending", "generating", "completed", "manual_pending",
    "manual_completed", "failed",
]
StrategyValue = Literal["cinematic", "dynamic"]


# ---------------------------------------------------------------------------
# Output — histórico
# ---------------------------------------------------------------------------
class GenerationResponse(BaseModel):
    id: str
    user_id: str
    product_id: str
    tier_used: TierName
    model_used: str
    duration_seconds: int
    resolution: str
    num_clips: int
    clip_strategy: str
    language: str
    voice_used: dict[str, Any] | None = None
    hook: dict[str, Any] | None = None
    voiceover_script: str
    captions_srt: str | None = None
    video_prompts: list[dict[str, Any]] = Field(default_factory=list)
    veo3_prompt: str | None = None
    nano_banana_prompt: str | None = None
    photos_used: list[str]
    photos_source: Literal["generated", "source"]
    generation_status: GenerationStatusValue
    video_type: Literal["shoppable", "normal"]
    ai_disclosure: bool
    cost: dict[str, Any]
    local_path: str | None = None
    drive_url: str | None = None
    metadata_path: str | None = None
    tiktok_shop_metadata: dict[str, Any]
    performance: dict[str, Any]
    error: str | None = None
    deleted: bool = False
    created_at: str
    completed_at: str | None = None


class GenerationListResponse(BaseModel):
    items: list[GenerationResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Input — encolar
# ---------------------------------------------------------------------------
class ClipPhotoOverride(BaseModel):
    """Asignación manual de foto a un clip (Standard/Advanced)."""

    clip_idx: int = Field(..., ge=0)
    photo_index: int = Field(..., ge=0)


class EnqueueRequest(BaseModel):
    username: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    tier: TierName = "standard"
    duration_seconds: int = Field(default=15, ge=5, le=30)
    resolution: str = "720p"
    strategy: StrategyValue = "dynamic"
    voice_enabled: bool = True
    voice_id: str | None = None
    hook_category: str = "general"
    hook_custom: str | None = None
    target_audience: str = "Generalista"
    shoppable: bool = False
    ai_disclosure: bool = True
    n_angles: int | None = Field(default=None, ge=4, le=8)  # solo Nano Banana

    # Asignación manual de fotos (opcional)
    clip_photo_overrides: list[ClipPhotoOverride] | None = None
    pro_ref_photo_overrides: list[int] | None = None

    @field_validator("username")
    @classmethod
    def _ensure_at(cls, v: str) -> str:
        v = v.strip()
        return v if v.startswith("@") else f"@{v}"


class EnqueueResponse(BaseModel):
    job_id: str
    estimated_cost: float
    estimated_duration_seconds: int
    position_in_queue: int  # 0 = es el siguiente; running=0 si lo está procesando ya


# ---------------------------------------------------------------------------
# Input — regenerar
# ---------------------------------------------------------------------------
class RegenerateRequest(BaseModel):
    """Cambios opcionales sobre el job original. Si está vacío → regenera idéntico."""

    overrides: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Output — metadata técnica
# ---------------------------------------------------------------------------
class VideoMetadataResponse(BaseModel):
    generation_id: str
    duration_seconds: int
    resolution: str
    file_size_bytes: int | None = None
    clip_count: int
    photos_used: list[str]
    voice_id: str | None = None
    voiceover_script: str | None = None
    cost: dict[str, Any]
    tiktok_shop_metadata: dict[str, Any]
    drive_path: str | None = None
    drive_url: str | None = None
    metadata_path: str | None = None
    completed_at: str | None = None
