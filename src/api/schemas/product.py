"""Schemas Pydantic de productos para la API.

Separados de `src.tiktok_shop.models.product` para no acoplar el contrato
HTTP a la persistencia. ProductResponse expone el dump completo (vía
`from_attributes`) — al frontend le da igual el shape interno mientras sea
estable.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.tiktok_shop.config import (
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    DEFAULT_TIER,
    PHOTO_TYPES_GENERATED,
)
from src.tiktok_shop.models.product import slugify
from src.tiktok_shop.utils.validators import (
    validate_slug,
    validate_tiktok_shop_url,
)


PhotoType = Literal["packshot", "lifestyle", "detail", "in_use", "macro"]
PhotoOrigin = Literal["internet", "own", "tiktok_shop_url"]
PhotoLocation = Literal["source", "generated"]
TierName = Literal["standard", "advanced", "pro", "veo3_prompt_only", "nano_banana_prompt_only"]


# ---------------------------------------------------------------------------
# Producto — input
# ---------------------------------------------------------------------------
class ProductTikTokShopInput(BaseModel):
    product_url: str | None = None
    product_id: str | None = None
    commission_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    price_eur: float | None = Field(default=None, ge=0.0)

    @field_validator("product_url")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        if not v:
            return None
        ok, err = validate_tiktok_shop_url(v, required=False)
        if not ok:
            raise ValueError(err)
        return v


class ProductCreate(BaseModel):
    """Crea un producto. `slug` es opcional (se deriva de `name` si falta)."""

    name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    brand: str | None = None
    category: str = "otros"
    subcategory: str | None = None
    target_audience: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    tiktok_shop: ProductTikTokShopInput = Field(default_factory=ProductTikTokShopInput)
    default_tier: TierName = DEFAULT_TIER
    default_duration: int = Field(default=DEFAULT_DURATION, ge=5, le=30)
    default_resolution: str = DEFAULT_RESOLUTION
    analyze_with_gemini: bool = False  # si true → background task tras crear

    @field_validator("slug")
    @classmethod
    def _validate_slug_field(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        ok, err = validate_slug(v)
        if not ok:
            raise ValueError(err)
        return v

    def resolve_slug(self) -> str:
        return self.slug or slugify(self.name)


class ProductUpdate(BaseModel):
    """PATCH parcial — todos los campos opcionales."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    target_audience: list[str] | None = None
    key_features: list[str] | None = None
    selling_points: list[str] | None = None
    tiktok_shop: ProductTikTokShopInput | None = None
    default_tier: TierName | None = None
    default_duration: int | None = Field(default=None, ge=5, le=30)
    default_resolution: str | None = None

    @field_validator("slug")
    @classmethod
    def _validate_slug_field(cls, v: str | None) -> str | None:
        if v is None:
            return None
        ok, err = validate_slug(v)
        if not ok:
            raise ValueError(err)
        return v


# ---------------------------------------------------------------------------
# Producto — output
# ---------------------------------------------------------------------------
class ProductResponse(BaseModel):
    """Dump completo del producto. Usamos `dict[str, Any]` para los nested
    porque el frontend solo lee y pintar. Si necesitamos contratos más
    estrictos los desnormalizamos en otro PR."""

    id: str
    slug: str
    name: str
    brand: str | None = None
    category: str
    subcategory: str | None = None
    target_audience: list[str]
    key_features: list[str]
    selling_points: list[str]
    tiktok_shop: dict[str, Any]
    photos: dict[str, Any]
    video_config: dict[str, Any]
    hooks_library: list[dict[str, Any]]
    performance_history: dict[str, Any]
    needs_nano_banana_regeneration: bool = False
    drive_folder: str | None = None
    deleted: bool = False
    last_analyzed_at: str | None = None
    created_at: str
    updated_at: str


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------
class PhotoUploadMetadata(BaseModel):
    """Metadata adicional al subir una foto multipart.

    - `location`: si va a `photos_source/` o `photos_generated/`.
    - `type`: clase de plano (obligatorio en generated, opcional en source).
    - `origin`: solo aplica a source.
    - `url_origin`: URL desde la que se descargó (source).
    """

    location: PhotoLocation = "source"
    type: PhotoType | None = None
    origin: PhotoOrigin | None = None
    url_origin: str | None = None
    preferred_for_tiers: list[TierName] = Field(default_factory=list)


class PhotoUpdateRequest(BaseModel):
    type: PhotoType | None = None
    preferred_for_tiers: list[TierName] | None = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in PHOTO_TYPES_GENERATED:
            raise ValueError(f"type inválido: {v}. Aceptados: {PHOTO_TYPES_GENERATED}")
        return v


class PhotoResponse(BaseModel):
    """Foto individual. Usamos `id` derivado del filename ya que el modelo
    de dominio no tiene UUID por foto."""

    id: str  # filename actúa como id estable dentro del producto
    location: PhotoLocation
    filename: str
    local_path: str | None = None
    drive_file_id: str | None = None
    type: PhotoType | None = None
    preferred_for_tiers: list[str]
    origin: PhotoOrigin | None = None
    url_origin: str | None = None
    added_at: str | None = None
    generation_prompt_used: str | None = None
    generated_at: str | None = None
    deleted: bool = False


# ---------------------------------------------------------------------------
# Análisis Gemini
# ---------------------------------------------------------------------------
class ReanalyzeResponse(BaseModel):
    product_id: str
    analyzed_at: str
    key_features: list[str]
    suggested_audiences: list[str]
    selling_points: list[str]
    has_complex_packaging_text: bool = False
    needs_nano_banana_regeneration: bool = False
    warnings: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)  # JSON bruto de Gemini


# ---------------------------------------------------------------------------
# Nano Banana 2 prompt
# ---------------------------------------------------------------------------
class NanoBananaPromptRequest(BaseModel):
    photo_types_wanted: list[PhotoType] = Field(
        default_factory=lambda: ["packshot", "lifestyle", "macro"],
        min_length=1,
    )
    n_angles: int = Field(default=5, ge=4, le=8)


class NanoBananaPromptResponse(BaseModel):
    product_id: str
    prompt: str
    instructions: str
