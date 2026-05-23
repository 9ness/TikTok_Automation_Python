"""Modelo de producto del catálogo (lo que vende el afiliado)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.tiktok_shop.config import (
    DEFAULT_DURATION, DEFAULT_RESOLUTION, DEFAULT_TIER,
)
from src.tiktok_shop.models.video_preset import VideoPreset


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    """Slug ASCII-safe minúsculas para nombres de carpeta / keys Redis."""
    s = name.lower().strip()
    s = re.sub(r"[áàä]", "a", s)
    s = re.sub(r"[éèë]", "e", s)
    s = re.sub(r"[íìï]", "i", s)
    s = re.sub(r"[óòö]", "o", s)
    s = re.sub(r"[úùü]", "u", s)
    s = re.sub(r"ñ", "n", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "producto"


class ProductPhoto(BaseModel):
    """Una foto del producto. Usado tanto en `photos.source` como en
    `photos.generated`. Los campos opcionales son los específicos de cada tipo:
    - `origin`/`url_origin`/`added_at` solo para source
    - `type`/`generation_prompt_used`/`generated_at` solo para generated
    """

    filename: str
    local_path: str | None = None       # path absoluto en Drive sincronizado
    drive_file_id: str | None = None    # opcional, si tenemos Drive API
    deleted: bool = False                # soft-delete: oculta foto sin tocar disco

    # Tipo de plano — válido para source y generated; en source es opcional
    # (se infiere del filename), en generated es obligatorio en el upload UI.
    type: Literal["packshot", "lifestyle", "detail", "in_use", "macro"] | None = None
    preferred_for_tiers: list[str] = Field(default_factory=list)  # tiers que la prefieren

    # Solo para photos.source
    origin: Literal["internet", "own", "tiktok_shop_url"] | None = None
    url_origin: str | None = None
    added_at: str | None = None

    # Solo para photos.generated
    generation_prompt_used: str | None = None
    generated_at: str | None = None


class ProductPhotos(BaseModel):
    """Fotos del producto separadas por origen.

    - `source`: originales (internet, propias, scraping de TikTok Shop URL).
    - `generated`: premium creadas con Nano Banana 2 a partir de `source`.

    Los pipelines de vídeo (Standard/Advanced/Pro) usan `generated` por defecto;
    si la lista está vacía, fallback a `source`.
    """

    source: list[ProductPhoto] = Field(default_factory=list)
    generated: list[ProductPhoto] = Field(default_factory=list)

    def best_available(self) -> tuple[list[ProductPhoto], Literal["generated", "source"]]:
        """Devuelve `(lista, origen)` filtrando las marcadas como `deleted`.

        Prefiere `generated` si tiene contenido NO-eliminado; si todas están
        eliminadas o la lista está vacía, fallback a `source` (también filtrado).
        """
        gen_active = [p for p in self.generated if not p.deleted]
        if gen_active:
            return gen_active, "generated"
        src_active = [p for p in self.source if not p.deleted]
        return src_active, "source"


class TikTokShopMeta(BaseModel):
    product_url: str | None = None
    product_id: str | None = None
    commission_rate: float = 0.10  # 10% por defecto
    price_eur: float | None = None


class VoicePreference(BaseModel):
    type: Literal["tts_preset", "voice_clone"] = "tts_preset"
    voice_id: str | None = None
    tone: Literal["energetic", "calm", "informative"] = "energetic"


class VideoConfig(BaseModel):
    default_tier: Literal["standard", "advanced", "pro", "veo3_prompt_only"] = DEFAULT_TIER
    default_duration: int = DEFAULT_DURATION
    default_resolution: str = DEFAULT_RESOLUTION
    preferred_styles: list[str] = Field(default_factory=lambda: ["asmr_macro", "lifestyle_aspirational"])
    voice_preference: VoicePreference = Field(default_factory=VoicePreference)
    has_complex_packaging: bool = False
    use_first_frame_anchor: bool = True


class Hook(BaseModel):
    category: str  # curiosity, problem_solution, social_proof, ...
    template: str  # texto del hook (puede tener placeholders)
    performance_score: float | None = None  # se actualiza con resultados


class PerformanceHistory(BaseModel):
    """Métricas agregadas del producto. Útil para `tier_selector` cuando
    haya datos reales."""

    total_videos_generated: int = 0
    total_orders_generated: int = 0
    best_hook_category: str | None = None
    promoted_to_advanced_at: str | None = None
    promoted_to_pro_at: str | None = None


class Product(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    slug: str  # validado en el field_validator
    name: str
    brand: str | None = None
    category: str = "otros"
    subcategory: str | None = None
    target_audience: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    # Idioma del contenido para guion + voz. Default "es_ES" (España).
    # Influye en:
    # - El prompt que Gemini usa al generar presets (voice_script, text_overlay)
    # - La voz default sugerida (Spanish_* MiniMax si es*, English_* si en*)
    # - Subtítulos burned-in en su idioma
    # Códigos soportados: "es_ES" (Spain), "es_LATAM", "en_US", "en_UK", "pt_BR", "fr_FR"
    language: str = "es_ES"
    tiktok_shop: TikTokShopMeta = Field(default_factory=TikTokShopMeta)
    photos: ProductPhotos = Field(default_factory=ProductPhotos)
    video_config: VideoConfig = Field(default_factory=VideoConfig)
    hooks_library: list[Hook] = Field(default_factory=list)
    # Presets de vídeo precocinados (blueprints clickables en /generate).
    # Se crean desde la UI del producto pulsando "Generar" — Gemini usa
    # los prompts music_bof_director.md / scripted_bof_director.md.
    video_presets: list["VideoPreset"] = Field(default_factory=list)
    performance_history: PerformanceHistory = Field(default_factory=PerformanceHistory)
    needs_nano_banana_regeneration: bool = False
    drive_folder: str | None = None
    deleted: bool = False                     # soft-delete: oculta sin tocar Drive/Redis
    last_analyzed_at: str | None = None      # último análisis Gemini exitoso
    # Calidad de fotos según Gemini: "high" | "medium" | "low" | ""
    photos_quality_assessment: str = ""
    # Warnings explicativos del último análisis (por qué needs_nano_banana,
    # por qué packaging complejo, etc). Se muestran en la UI para que el
    # admin entienda las decisiones sin tener que ir al raw.
    last_analysis_warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not v:
            raise ValueError("slug no puede estar vacío")
        if not re.fullmatch(r"[a-z0-9_]+", v):
            raise ValueError(f"slug inválido: '{v}' (solo a-z, 0-9, _)")
        return v

    def touch(self) -> None:
        self.updated_at = _now_iso()
