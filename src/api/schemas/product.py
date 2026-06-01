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
    slug: str | None = Field(default=None, max_length=200)
    brand: str | None = None
    category: str = "otros"
    subcategory: str | None = None
    target_audience: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    # Idioma del contenido (afecta voz + guion + subs). Códigos:
    # "es_ES" Spain (default), "es_LATAM", "en_US", "en_UK", "pt_BR", "fr_FR", "it_IT".
    language: str = "es_ES"
    tiktok_shop: ProductTikTokShopInput = Field(default_factory=ProductTikTokShopInput)
    default_tier: TierName = DEFAULT_TIER
    default_duration: int = Field(default=DEFAULT_DURATION, ge=5, le=30)
    default_resolution: str = DEFAULT_RESOLUTION
    analyze_with_gemini: bool = False  # si true → background task tras crear
    # Si viene relleno, tras crear el producto descarga esta imagen y la
    # añade como primera foto source (photo_type=packshot). Pensado para
    # auto-completar productos creados desde URL TikTok Shop con la
    # `og:image` que sale del scraping.
    image_url_to_download: str | None = Field(default=None, max_length=2000)

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
    slug: str | None = Field(default=None, max_length=200)
    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    target_audience: list[str] | None = None
    key_features: list[str] | None = None
    selling_points: list[str] | None = None
    language: str | None = None
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
    language: str = "es_ES"
    tiktok_shop: dict[str, Any]
    photos: dict[str, Any]
    video_config: dict[str, Any]
    hooks_library: list[dict[str, Any]]
    # Presets de vídeo precocinados (música + scripted). Dump genérico
    # — el frontend tiene types VideoPreset que matchea.
    video_presets: list[dict[str, Any]] = Field(default_factory=list)
    # Investigación profunda (pains, benefits, objections, viral_patterns,
    # top_videos, etc). Se rellena al pulsar "Reanalizar producto".
    research_context: dict[str, Any] = Field(default_factory=dict)
    # Hooks marcados como favoritos por el operador. Sobreviven a la
    # regeneración de presets y se usan como proven_hooks extras.
    favorite_hooks: list[dict[str, Any]] = Field(default_factory=list)
    performance_history: dict[str, Any]
    needs_nano_banana_regeneration: bool = False
    drive_folder: str | None = None
    deleted: bool = False
    last_analyzed_at: str | None = None
    photos_quality_assessment: str = ""
    last_analysis_warnings: list[str] = Field(default_factory=list)
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
# URL preview — auto-rellenar form Identidad pegando URL de TikTok Shop
# ---------------------------------------------------------------------------
class AnalyzeUrlPreviewRequest(BaseModel):
    # Al menos UNO de los dos tiene que venir relleno (validado en el router).
    # url      — la pegamos en TikTok Shop y la app intenta scrapearla
    # raw_text — el user pega texto del producto (título, descripción,
    #            precio, share text del móvil…). Gemini saca campos
    #            estructurados. Útil cuando TikTok bloquea el scraping.
    url: str | None = Field(default=None, max_length=2000)
    raw_text: str | None = Field(default=None, max_length=8000)
    use_gemini: bool = True  # opcionalmente desactivable para debug


class AnalyzeUrlPreviewResponse(BaseModel):
    """Campos detectados — todos opcionales (devolvemos lo que pudimos)."""
    name: str | None = None
    brand: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    price_eur: float | None = None
    currency: str | None = None
    image_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Importar fotos por URL + grading con Gemini
# ---------------------------------------------------------------------------
class ImportPhotosFromUrlsRequest(BaseModel):
    """Lista de URLs candidatas. Backend descarga + Gemini puntúa cada una."""
    urls: list[str] = Field(..., min_length=1, max_length=20)


class PhotoCandidateGrade(BaseModel):
    """Resultado de evaluar una foto candidata. NO está guardada todavía
    en el producto — se queda en `temp_work/` hasta que el user marque
    cuáles confirmar vía `commit-imported-photos`."""
    candidate_id: str          # uuid corto, se usa en el commit
    url: str
    score: int                  # 0-10
    type: str                   # packshot|lifestyle|detail|in_use|macro|other
    # Detección "mismo producto vs producto parecido". Si el producto
    # ya tiene fotos source, Gemini compara la candidata con esas como
    # ground truth y marca is_same_product=false si dudosamente es el
    # mismo SKU. En ese caso el score se forzó a max 3 en el backend.
    is_same_product: bool = True
    same_product_confidence: str = "no_reference"  # high|medium|low|no_reference
    # Si la candidata es esencialmente el MISMO plano que alguna foto de
    # referencia (mismo ángulo, composición, fondo). El score ya viene
    # capado en -3 desde el grader. La UI muestra badge "duplicado" para
    # que el user no la marque y prefiera fotos complementarias.
    is_duplicate_of_reference: bool = False
    is_branded: bool
    has_text_overlay: bool
    has_watermark: bool
    is_collage: bool
    shows_product_clearly: bool
    reasons: str
    preview_url: str            # endpoint para servir el preview en la UI
    error: str | None = None   # si la descarga falló


class ImportPhotosFromUrlsResponse(BaseModel):
    product_id: str
    candidates: list[PhotoCandidateGrade]


class CommitImportedPhotosRequest(BaseModel):
    """El user marcó qué candidatos quiere guardar. Llega el candidate_id
    + el `type` final (puede haber editado el detectado por Gemini)."""
    candidates: list["CommitImportedPhotoItem"] = Field(..., min_length=1)


class CommitImportedPhotoItem(BaseModel):
    candidate_id: str
    type: PhotoType | None = None  # si None, usa el detectado por Gemini


class CommitImportedPhotosResponse(BaseModel):
    product_id: str
    saved_count: int
    skipped: list[str] = Field(default_factory=list)  # candidate_ids que fallaron


CommitImportedPhotosRequest.model_rebuild()


class GoogleImageSearchRequest(BaseModel):
    """Buscar imágenes externas para el producto.

    Provider:
      - "auto" (default): DDG primero, fallback CSE si está configurado
      - "ddg": fuerza DuckDuckGo (sin API key, siempre funciona)
      - "google": fuerza Google CSE (requiere env vars, falla si no)
    """
    query: str | None = Field(default=None, max_length=200)
    num: int = Field(default=10, ge=1, le=10)
    provider: str = Field(default="auto")  # auto | ddg | google


class GoogleImageSearchResultItem(BaseModel):
    link: str
    title: str = ""


class GoogleImageSearchResponse(BaseModel):
    configured: bool                    # True si hubo algún provider disponible
    provider_used: str = "none"        # ddg | google_cse | none
    query_used: str
    results: list[GoogleImageSearchResultItem] = Field(default_factory=list)
    hint: str = ""  # mensaje al usuario (ej. "ningún resultado")


# ---------------------------------------------------------------------------
# Video presets (blueprints precocinados de vídeo por producto)
# ---------------------------------------------------------------------------
PresetKindRequest = Literal["music", "scripted", "both", "fruit"]


class TextOverlayStyleSchema(BaseModel):
    font: str = ""
    size_px: int = 56
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = 6
    position: str = "top_center"
    position_y_pct: float = 12.0
    animation: str = "fade_in"
    uppercase: bool = True
    background: str = "none"
    duration_s: float = 4.0


class SubtitleStyleSchema(BaseModel):
    enabled: bool = True
    font: str = ""
    size_px: int = 48
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = 5
    position: str = "bottom_center"
    position_y_pct: float = 75.0
    highlight_mode: str = "pill"
    highlight_color: str = "#FFE066"
    max_words_per_line: int = 3
    uppercase: bool = False
    animation: str = "fade_in"
    margin_x_pct: float = 8.0


class CtaArrowStyleSchema(BaseModel):
    enabled: bool = False
    sticker_file: str = "flecha_negra.mov"
    position_x_pct: float = 50.0
    position_y_pct: float = 75.0
    scale_width_pct: float = 25.0
    rotation_deg: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    duration_seconds: float = 4.0
    show_at_end: bool = True


class VideoPresetResponse(BaseModel):
    """Dump completo de un VideoPreset persistido."""
    id: str
    kind: str
    name: str
    angle: str = ""
    style: str = ""              # "voiceover" | "creator_pov" | ""
    shot_style: str = "auto"     # "single_shot" | "multi_shot" | "auto"
    strategy: str = "dynamic"    # "cinematic" | "dynamic"
    duration_s: int
    compatible_tiers: list[str]
    text_overlay: str = ""
    text_hooks: list[str] = Field(default_factory=list)
    text_overlay_style: TextOverlayStyleSchema = Field(default_factory=TextOverlayStyleSchema)
    subtitle_style: SubtitleStyleSchema = Field(default_factory=SubtitleStyleSchema)
    cta_arrow_style: CtaArrowStyleSchema = Field(default_factory=CtaArrowStyleSchema)
    music_mood: str = ""
    voice_id: str | None = None
    voice_tone: str = "energetic"
    title: str = ""
    voice_script: str = ""
    hooks_alternatives: list[str] = Field(default_factory=list)
    cta: str = ""
    oratory_tips: str = ""
    keywords: list[str] = Field(default_factory=list)
    seedance_prompt: str = ""
    image_prompt: str = ""       # keyframe Nano Banana (solo fruit_story)
    veo3_prompt: str = ""
    # Para vídeos > 10s: lista de N prompts de ~8-10s cada uno (Flow Gemini
    # encadenado). Vacío si `duration_s` ≤ 10.
    veo3_prompt_segments: list[str] = Field(default_factory=list)
    # Fotos del producto que Gemini eligió para adjuntar a Veo 3 (max 3).
    # El user las adjunta MANUALMENTE al pegar el prompt en Gemini chat / Flow.
    veo3_photo_filenames: list[str] = Field(default_factory=list)
    source: str = "manual"
    variant: str = "original"   # "original" | "fruit_story"
    notes: str = ""
    created_at: str
    updated_at: str


class GeneratePresetsRequest(BaseModel):
    kind: PresetKindRequest = "both"
    n_music: int = Field(default=8, ge=1, le=20)
    n_scripted: int = Field(default=12, ge=1, le=20)
    n_fruit: int = Field(default=10, ge=1, le=20)
    # Si true, reemplaza los presets autogenerados anteriores del mismo
    # `source` (music_bof/scripted_bof/fruit_story). Los manuales nunca se tocan.
    replace_existing: bool = False


class GenerateFruitRequest(BaseModel):
    """Generación SÍNCRONA de presets fruta desde el generador Veo 3.
    Un solo call a Gemini devuelve los N (no encola)."""
    generation: Literal["single", "batch", "ab"] = "batch"
    n: int = Field(default=10, ge=1, le=20)
    fruit_hint: str | None = None        # fruta base (forzada)
    narrative_angle: str | None = None   # enfoque base (dramatico/chismoso/…)
    # Idea/escena escrita por el user. Si viene, la historia se construye
    # sobre este tema (convertido a personajes-fruta) en vez de inventar.
    custom_theme: str | None = Field(default=None, max_length=2000)
    # Por defecto reemplaza las fruta anteriores (source=fruit_story).
    replace_existing: bool = True


class GenerateFruitResponse(BaseModel):
    product_id: str
    created_count: int
    presets: list[VideoPresetResponse] = Field(default_factory=list)
    cost_usd: float = 0.0


class GenerateFruitHooksResponse(BaseModel):
    """3 ganchos de texto generados (y persistidos) para un preset de fruta."""
    product_id: str
    preset_id: str
    text_hooks: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0


class ExtendFruitRequest(BaseModel):
    """Alargar una historia de fruta (de ~10s) a N partes continuas que el
    user genera por separado y une en un solo vídeo de N×10s."""
    parts: int = Field(default=2, ge=2, le=3)


class FruitStoryPart(BaseModel):
    part: int
    beat: str = ""
    image_prompt: str = ""    # keyframe Nano Banana de esta parte
    veo3_prompt: str = ""     # animación Flow de esta parte


class ExtendFruitResponse(BaseModel):
    product_id: str
    preset_id: str
    parts: list[FruitStoryPart] = Field(default_factory=list)
    # 3 ganchos de texto (overlay 1er segundo) para el vídeo unido.
    text_hooks: list[str] = Field(default_factory=list)
    # Fotos del producto a adjuntar al generar la imagen de CADA parte
    # (mismas en todas, para que el bote salga fiel y coherente).
    photo_filenames: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0


class GeneratePresetsResponse(BaseModel):
    """Respuesta INMEDIATA del endpoint async. Devuelve el `gen_id` para
    que el frontend pueda hacer polling del progreso. Los presets reales
    se persistirán cuando la BackgroundTask termine."""
    product_id: str
    gen_id: str
    stage: str = "started"
    # NOTA: `created_count` y `presets` quedan vacíos en la response
    # inicial. El frontend los obtiene cuando stage="done" via polling
    # del status endpoint + refetch del producto.
    created_count: int = 0
    presets: list[VideoPresetResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PresetGenStatusResponse(BaseModel):
    """Snapshot del progreso de una generación en curso."""
    gen_id: str
    product_id: str
    kind: str                       # "music" | "scripted" | "both"
    stage: str                       # started|generating_music|generating_scripted|saving|done|error
    percent: int                     # 0-100
    expected_count: int
    created_count: int
    warnings: list[str] = Field(default_factory=list)
    started_at: str
    ended_at: str | None = None
    error: str | None = None
    # Coste acumulado de llamadas a Gemini en USD. Se llena tras cada
    # stage (music/scripted) leyendo `cost_tracking.get_active()`.
    cost_usd: float = 0.0


class GenerateVariantsRequest(BaseModel):
    count: int = Field(default=4, ge=2, le=8)
    dimensions: list[str] = Field(default_factory=list)


class VariantMeta(BaseModel):
    variant_id: str
    hypothesis: str
    patch_keys: list[str]


class GenerateVariantsResponse(BaseModel):
    base_preset_id: str
    variants: list[VideoPresetResponse] = Field(default_factory=list)
    meta: list[VariantMeta] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class VideoPresetUpdateRequest(BaseModel):
    """PATCH parcial de un preset (edición a mano desde la UI)."""
    name: str | None = None
    shot_style: str | None = None
    strategy: str | None = None
    duration_s: int | None = Field(default=None, ge=5, le=60)
    text_overlay: str | None = None
    text_overlay_style: TextOverlayStyleSchema | None = None
    subtitle_style: SubtitleStyleSchema | None = None
    cta_arrow_style: CtaArrowStyleSchema | None = None
    music_mood: str | None = None
    voice_id: str | None = None
    voice_tone: str | None = None
    title: str | None = None
    voice_script: str | None = None
    hooks_alternatives: list[str] | None = None
    cta: str | None = None
    oratory_tips: str | None = None
    keywords: list[str] | None = None
    seedance_prompt: str | None = None
    veo3_prompt: str | None = None
    veo3_prompt_segments: list[str] | None = None
    veo3_photo_filenames: list[str] | None = None
    angle: str | None = None
    notes: str | None = None
    compatible_tiers: list[str] | None = None


class BulkStyleRequest(BaseModel):
    """Aplica un patch de estilo VISUAL a TODOS los presets del producto
    (o a un subconjunto por scope). Sólo se permiten campos visuales —
    `position` y `position_x_pct`/`position_y_pct` se ignoran en server.

    El cliente envía dicts parciales: sólo las claves presentes se
    aplican a cada preset; el resto queda intacto. Si el preset no
    tiene `subtitle_style` (kind=music con subs OFF) el patch de subs
    se ignora para ese preset — no fuerza a habilitarlos.
    """
    # Patch parcial sobre VideoPreset.text_overlay_style (hook box).
    text_overlay_style: dict[str, Any] | None = None
    # Patch parcial sobre VideoPreset.subtitle_style (karaoke subs).
    subtitle_style: dict[str, Any] | None = None
    # Scope: aplicar a todos los presets, sólo a music, sólo a scripted,
    # o sólo a réplicas virales. Default 'all'.
    scope: Literal["all", "music", "scripted", "viral_replica"] = "all"


class BulkStyleResponse(BaseModel):
    updated_count: int
    skipped_count: int
    total_presets: int


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
