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
    # Cap de longitud: nombres de producto largos generaban slugs de 150+
    # chars que (a) rompían el max_length del schema al re-guardar y (b) son
    # malos como nombre de carpeta. Cortamos a 120 en frontera de palabra.
    if len(s) > 120:
        s = s[:120]
        if "_" in s:
            s = s[: s.rfind("_")]
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


class FavoriteHook(BaseModel):
    """Hook marcado como favorito por el operador. Sobrevive a la
    regeneración de presets — se almacena en `Product.favorite_hooks`
    independientemente del array `video_presets`.

    Cuando se regeneran presets con `replace_existing=True`, los
    favoritos NO se tocan. Además los prompts directores los reciben
    como `proven_hooks` extras, así los presets nuevos se inspiran
    también en los favoritos del user (no solo en la investigación)."""
    text: str                            # el hook literal
    angle: str = ""                      # ángulo detectado (urgencia, dolor, ...)
    kind: str = ""                       # kind del preset original (music/scripted)
    source_preset_id: str | None = None  # preset de donde vino (si vino de uno)
    notes: str = ""                      # comentario libre del user
    saved_at: str = Field(default_factory=_now_iso)


class ViralVideoSummary(BaseModel):
    """Resumen de un vídeo viral analizado por Gemini para extraer su fórmula."""
    url: str                            # https://tiktok.com/...
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_s: float = 0.0
    hook_text: str = ""                 # hook visible en pantalla seg 0-3
    hook_category: str = ""             # curiosity, problem, social_proof, ...
    script_structure: str = ""          # "0-3s hook → 3-8s problem → 8-12s reveal → 12-15s CTA"
    visual_patterns: list[str] = Field(default_factory=list)  # planos, cortes, transiciones
    cta_used: str = ""
    music_mood: str = ""
    # Clasificación de tráfico inferida por engagement rate:
    #   "organic" → engagement alto (resonó de verdad)
    #   "paid"    → muchas views pero engagement bajo (probable ad/boost)
    # Permite separar las dos fórmulas: qué convierte con presupuesto vs
    # qué engancha orgánicamente. NO es dato de ventas (TikTok no lo expone
    # públicamente para ES) — es un proxy por ratio de interacción.
    traffic_type: str = ""
    # País del que viene el vídeo (ES/US/GB/...). Cuando el nicho en España
    # es pequeño, ampliamos a otros mercados y Gemini adapta la fórmula al
    # español. "" = ES por defecto.
    country: str = ""
    # Audio/sonido del vídeo (extraído de Apify musicMeta). El sonido es
    # uno de los mayores drivers de viralidad en TikTok — capturamos el
    # ID para poder reutilizar el MISMO audio trending del nicho.
    music_id: str = ""                  # TikTok music id (reutilizable al subir)
    music_title: str = ""               # nombre de la canción/sonido
    music_author: str = ""              # autor del sonido
    music_is_original: bool = False     # True si es sonido original del creador
    music_url: str = ""                 # playUrl (preview del audio)


class TrendingSound(BaseModel):
    """Sonido/audio trending agregado de los top vídeos del nicho.

    Se construye contando cuántos de los top vídeos virales usan el mismo
    `music_id`. El operador puede reutilizar el mismo sonido al subir su
    vídeo (TikTok prioriza vídeos que montan sonidos en tendencia)."""
    music_id: str = ""
    title: str = ""
    author: str = ""
    is_original: bool = False
    url: str = ""
    used_count: int = 1                 # en cuántos top vídeos aparece
    total_views: int = 0                # suma de views de los vídeos que lo usan


class ResearchContext(BaseModel):
    """Contexto de investigación profunda del producto.

    Se rellena automáticamente por `research_service.py` al pulsar
    "Reanalizar producto". Mezcla:
      - Reviews de Amazon/AliExpress/web marca (Gemini con Google Search)
      - Top vídeos virales TikTok del producto (Apify + Gemini video analysis)
      - Comentarios de esos vídeos (Apify) → objeciones reales
      - Investigación del nicho (Gemini búsqueda)

    Los prompts directores (scripted, music, ab_variants) leen este
    contexto para generar guiones con autoridad real — usando dolor,
    objeciones y patrones virales verificados, no inventados.
    """
    # Pains/benefits extraídos de reviews reales
    customer_pains: list[str] = Field(default_factory=list)
    customer_benefits: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    # Patrones agregados de los top vídeos TikTok del producto
    viral_patterns: list[str] = Field(default_factory=list)
    # Vídeos analizados individualmente (referencia + posible reuso)
    top_videos: list[ViralVideoSummary] = Field(default_factory=list)
    # Keywords del nicho para SEO y inspiración
    niche_keywords: list[str] = Field(default_factory=list)
    niche_inspiration: list[str] = Field(default_factory=list)
    # Diferenciadores frente a competencia
    competitive_diff: list[str] = Field(default_factory=list)
    # Hooks AGREGADOS desde los vídeos virales (mejor que los inventados)
    proven_hooks: list[str] = Field(default_factory=list)
    # Preguntas/dudas REALES sacadas de los comentarios de los vídeos
    # virales (Apify comments scraper). Son las objeciones más afiladas
    # porque vienen del propio canal (TikTok), no de reviews de Amazon.
    audience_questions: list[str] = Field(default_factory=list)
    # Sonidos/audios trending del nicho (agregados de los top vídeos).
    trending_sounds: list[TrendingSound] = Field(default_factory=list)
    # True mientras el deep research corre en background (lo pone el
    # runner al arrancar y lo limpia al terminar). El frontend lo usa
    # para mostrar spinner "investigando…" y auto-refrescar.
    research_in_progress: bool = False
    # Cuándo se hizo (para refrescar cada N días)
    analyzed_at: str | None = None
    # Métricas de la investigación (para debug + cost tracking)
    sources_reviews_count: int = 0      # cuántas reviews leyó Gemini
    sources_videos_count: int = 0       # cuántos TikToks analizó
    sources_comments_count: int = 0     # cuántos comentarios analizó
    research_cost_usd: float = 0.0      # coste total REAL del último research


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
    # Códigos soportados: "es_ES" (Spain), "es_LATAM", "en_US", "en_UK", "pt_BR", "fr_FR", "it_IT"
    language: str = "es_ES"
    tiktok_shop: TikTokShopMeta = Field(default_factory=TikTokShopMeta)
    photos: ProductPhotos = Field(default_factory=ProductPhotos)
    video_config: VideoConfig = Field(default_factory=VideoConfig)
    hooks_library: list[Hook] = Field(default_factory=list)
    # Hooks marcados como favoritos por el operador. Sobreviven a la
    # regeneración de presets. Los prompts directores los usan como
    # `proven_hooks` extras al regenerar.
    favorite_hooks: list[FavoriteHook] = Field(default_factory=list)
    # Presets de vídeo precocinados (blueprints clickables en /generate).
    # Se crean desde la UI del producto pulsando "Generar" — Gemini usa
    # los prompts music_bof_director.md / scripted_bof_director.md.
    video_presets: list["VideoPreset"] = Field(default_factory=list)
    # Carruseles generados (Photo Mode) — cada uno es el dict del
    # carousel_director (format, hook_caption, slides[], ...). Se persisten
    # aquí para verlos/copiarlos desde la app (Radar → Calendario) sin abrir
    # Drive. Los escribe `creation_pack.build_pack`.
    carousels: list[dict] = Field(default_factory=list)
    # Investigación profunda: reviews + top vídeos TikTok + comentarios.
    # Se rellena vía `research_service.py` al pulsar "Reanalizar producto".
    # Los prompts directores leen esto para afinar hooks y guiones con
    # datos reales del producto + nicho (no inventados).
    research_context: ResearchContext = Field(default_factory=ResearchContext)
    performance_history: PerformanceHistory = Field(default_factory=PerformanceHistory)
    needs_nano_banana_regeneration: bool = False
    # Origen del producto: "manual" (creado a mano en la pestaña Productos) o
    # "radar" (descubierto + importado por el Radar de Productos). Default
    # "manual" para que TODOS los productos existentes sigan siendo manuales.
    origin: Literal["manual", "radar"] = "manual"
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
