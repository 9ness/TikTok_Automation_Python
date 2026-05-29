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


# ---------------------------------------------------------------------------
# Overlays componibles — Fase 3 (hook box al inicio + CTA flecha al final)
# Schemas flexibles (estructura libre) para que la UI evolucione sin tocar
# Pydantic en cada iteración. Los pipelines validan internamente sus campos.
# ---------------------------------------------------------------------------
class HookBoxOverlay(BaseModel):
    enabled: bool = False
    text: str | None = None  # si vacío → usa strategy.hook_text del strategist
    animation: str = "swipe_left"
    duration: float = 5.0
    y_position_pct: float = 0.40
    text_color: str = "#0B0B0B"
    box_color: str = "#FFFFFF"
    shadow_color: str = "#1E01C4"
    font_path: str | None = None
    font_scale: float = 0.018


class CtaArrowOverlay(BaseModel):
    enabled: bool = False
    sticker_file: str | None = None  # nombre archivo en Assets/flechas/
    position_x_pct: float = 50.0
    position_y_pct: float = 78.0
    scale_width_pct: float = 25.0
    rotation_deg: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    duration_seconds: float = 3.5
    fallback_last_seconds: float = 4.0


class OverlaysConfig(BaseModel):
    hook_box: HookBoxOverlay = Field(default_factory=HookBoxOverlay)
    cta_arrow: CtaArrowOverlay = Field(default_factory=CtaArrowOverlay)


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

    # Fase 3 — overlays componibles
    overlays: OverlaysConfig | None = None
    # Fase 4 — estilo de subtítulos del preset (formato VideoPreset.subtitle_style).
    # Si viene, el runner lo mapea a `captions_style` y lo pasa al editor.
    # Si no, usa el default conservador (`_default_caption_style`).
    subtitle_style: dict[str, Any] | None = None

    # Hora ISO 8601 a la que el job debe empezar a ejecutarse. Si está en
    # el futuro, el job se encola pero el worker NO lo coge hasta esa hora.
    # Útil para programar a horas valle (madrugada) donde los providers
    # AI tienen cola despejada. Si None o pasado → ejecuta inmediatamente.
    scheduled_for: str | None = None

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
# Fase 4 — Test batches (variantes A/B)
# ---------------------------------------------------------------------------
VARYABLE_DIMENSIONS = (
    "hook_category",
    "voice_id",
    "strategy",
    "duration_seconds",
    "hook_box_animation",
)


class TestBatchRequest(BaseModel):
    """Encolado de N variantes derivadas de un base_payload.

    `vary` declara las dimensiones que rotan entre variantes. Si `custom_values`
    está vacío, usamos defaults razonables por dimensión (definidos en el
    router). Si `custom_values["hook_category"] = ["curiosity","shock"]`, las
    variantes rotan SOLO esos valores para esa dimensión.
    """

    base: EnqueueRequest
    vary: list[str] = Field(..., min_length=1, max_length=3)
    count: int = Field(default=4, ge=2, le=8)
    custom_values: dict[str, list[str]] | None = None

    @field_validator("vary")
    @classmethod
    def _check_vary(cls, v: list[str]) -> list[str]:
        for dim in v:
            if dim not in VARYABLE_DIMENSIONS:
                raise ValueError(
                    f"Dimensión '{dim}' no soportada. Acepta: {VARYABLE_DIMENSIONS}",
                )
        return v


class TestBatchResponse(BaseModel):
    test_batch_id: str
    job_ids: list[str]
    estimated_cost_total: float
    variants: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Input — regenerar
# ---------------------------------------------------------------------------
class RegenerateRequest(BaseModel):
    """Cambios opcionales sobre el job original. Si está vacío → regenera idéntico."""

    overrides: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Input/Output — preview prompts (Veo3 / Nano Banana, sin tocar la cola)
# ---------------------------------------------------------------------------
class PreviewVeo3Request(BaseModel):
    username: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    hook_category: str = "curiosity"
    hook_custom: str | None = None
    target_audience: str = "Generalista"
    language: str = "es"
    # Variante "personaje de fruta" (mini-historia viral) — opcional.
    fruit_mode: bool = False
    fruit_hint: str | None = None          # fruta forzada (vacío = la elige la IA)
    narrative_angle: str | None = None     # dramatico/chismoso/comico/aspiracional

    @field_validator("username")
    @classmethod
    def _ensure_at(cls, v: str) -> str:
        v = v.strip()
        return v if v.startswith("@") else f"@{v}"


class PreviewVeo3Response(BaseModel):
    prompt: str
    hook_text: str
    voiceover_script: str
    style: str


class PreviewNanoBananaRequest(BaseModel):
    username: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    n_angles: int = Field(default=5, ge=4, le=8)
    use_cases: list[str] | None = None

    @field_validator("username")
    @classmethod
    def _ensure_at(cls, v: str) -> str:
        v = v.strip()
        return v if v.startswith("@") else f"@{v}"


class PreviewNanoBananaResponse(BaseModel):
    prompt: str
    n_angles: int


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
