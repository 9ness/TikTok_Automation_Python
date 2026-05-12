"""Schemas Pydantic del nicho 🎬 Subs sobre Vídeo (Subs Auto)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


WhisperModelSize = Literal["tiny", "base", "small", "medium", "large"]
HighlightMode = Literal["pill", "color_swap", "underline", "box_outline", "glow", "none"]
CaseMode = Literal["UPPERCASE", "lowercase", "Title Case", "None"]
AudioType = Literal["speech", "music"]
QualityLabel = Literal[
    "1080p (Lento)", "720p (Medio)", "480p (Rápido)", "240p (Ultra Rápido)",
]


# ---------------------------------------------------------------------------
# Transcripción (paso 1)
# ---------------------------------------------------------------------------
class SubsAutoWord(BaseModel):
    word: str
    start: float
    end: float


class SubsAutoTranscribeResponse(BaseModel):
    """El frontend recibe paths relativos a temp_root, palabras con
    timestamps, y la config usada (para repetirla en el enqueue)."""

    input_path_relative: str
    out_path_relative: str
    words: list[SubsAutoWord]
    quality_label: QualityLabel
    model_size: WhisperModelSize
    language: str | None = None
    audio_type: AudioType


# ---------------------------------------------------------------------------
# Estilo (paso 3)
# ---------------------------------------------------------------------------
class SubsAutoStyleConfig(BaseModel):
    font_path: str
    highlight_mode: HighlightMode = "pill"
    highlight_color: str = "#BB0808"
    text_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = Field(default=3, ge=0, le=10)
    case_mode: CaseMode = "UPPERCASE"
    font_scale: float = Field(default=0.045, gt=0.0, le=0.2)
    max_words: int = Field(default=3, ge=1, le=10)
    y_position: float = Field(default=0.78, ge=0.0, le=1.0)
    pill_enabled: bool = True
    max_width: float = Field(default=0.85, gt=0.0, le=1.0)
    sync_offset: int = Field(default=0, ge=-2000, le=2000, description="ms")


# ---------------------------------------------------------------------------
# Enqueue (paso 3)
# ---------------------------------------------------------------------------
class SubsAutoEnqueueRequest(BaseModel):
    input_path: str = Field(..., description="Path RELATIVO a temp_root (devuelto por /transcribe).")
    out_path: str = Field(..., description="Path RELATIVO a temp_root (devuelto por /transcribe).")
    edited_text: str | None = Field(
        default=None,
        description="Si hay edición manual de palabras, manda aquí el texto editado.",
    )
    reference_text: str | None = None
    model_size: WhisperModelSize = "small"
    language: str | None = None
    audio_type: AudioType = "speech"
    quality_label: QualityLabel = "1080p (Lento)"
    style: SubsAutoStyleConfig


class SubsAutoEnqueueResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int
