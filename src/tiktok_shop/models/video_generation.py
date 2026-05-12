"""Modelo de generación de vídeo (histórico) — un registro por vídeo creado."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GenerationStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    MANUAL_PENDING = "manual_pending"      # Veo3/NanoBanana: prompt listo, esperando upload manual
    MANUAL_COMPLETED = "manual_completed"  # Veo3/NanoBanana: el user subió el output manual
    FAILED = "failed"


class ClipPrompt(BaseModel):
    clip_idx: int
    duration: int  # segundos
    ref_photo_index: int | None = None       # standard/advanced: 1 foto
    ref_photo_indices: list[int] = Field(default_factory=list)  # pro: multi-ref
    use_first_frame_anchor: bool = False
    anchor_to_previous_clip_end: int | None = None  # idx del clip anterior cuyo last frame anclar
    prompt: str


class VideoCost(BaseModel):
    video_generation: float = 0.0
    voice_tts: float = 0.0
    other: float = 0.0
    total: float = 0.0
    estimated_at_creation: float | None = None  # lo que se calculó antes de generar
    actual_after_completion: float | None = None  # recalculado tras completar

    def recompute_total(self) -> None:
        self.total = round(self.video_generation + self.voice_tts + self.other, 4)


class HookUsed(BaseModel):
    category: str
    text: str


class VoiceUsed(BaseModel):
    type: Literal["tts_preset", "voice_clone"] = "tts_preset"
    voice_id: str
    name: str | None = None


class TikTokShopVideoMeta(BaseModel):
    caption_template: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    suggested_post_time: str | None = None
    human_presence: bool = True


class Performance(BaseModel):
    published_at: str | None = None
    views: int | None = None
    likes: int | None = None
    shares: int | None = None
    orders_generated: int = 0


class VideoGeneration(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str
    product_id: str
    tier_used: Literal[
        "standard", "advanced", "pro", "veo3_prompt_only", "nano_banana_prompt_only"
    ] = "standard"
    model_used: str = ""  # endpoint Atlas o "" para prompt-only
    duration_seconds: int = 15
    resolution: str = "720p"
    num_clips: int = 1
    clip_strategy: Literal["multi_clip_anchor", "single_shot_multishot", "manual_paste_in_gemini_chat"] = "multi_clip_anchor"
    language: str = "es"
    voice_used: VoiceUsed | None = None
    hook: HookUsed | None = None
    voiceover_script: str = ""
    captions_srt: str | None = None
    video_prompts: list[ClipPrompt] = Field(default_factory=list)
    veo3_prompt: str | None = None  # solo si tier == veo3_prompt_only
    nano_banana_prompt: str | None = None  # solo si tier == nano_banana_prompt_only
    photos_used: list[str] = Field(default_factory=list)  # filenames usados
    photos_source: Literal["generated", "source"] = "source"
    generation_status: GenerationStatus = GenerationStatus.PENDING
    video_type: Literal["shoppable", "normal"] = "normal"
    ai_disclosure: bool = True
    cost: VideoCost = Field(default_factory=VideoCost)
    local_path: str | None = None
    drive_url: str | None = None
    metadata_path: str | None = None
    tiktok_shop_metadata: TikTokShopVideoMeta = Field(default_factory=TikTokShopVideoMeta)
    performance: Performance = Field(default_factory=Performance)
    error: str | None = None
    deleted: bool = False                      # soft-delete: oculta del histórico
    created_at: str = Field(default_factory=_now_iso)
    completed_at: str | None = None
