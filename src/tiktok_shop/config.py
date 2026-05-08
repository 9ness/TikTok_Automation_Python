"""Constantes y resolución de paths del nicho TikTok Shop.

Decisiones:
- TikTok Shop es un PROGRAMA HERMANO de Creator Reward, no anidado:
    Mi unidad/NEBULABS_AUTOMATED_TIKTOK/
    ├── TIKTOK_CR/TIKTOK_ASSETS/   (TIKTOK_ROOT_PATH — Creator Reward)
    └── TIKTOK_SHOP/                (TIKTOK_SHOP_ROOT_PATH — Programa 2)
- Las subcarpetas `_users/` y `_products/` se crean lazy al guardar el primer
  usuario/producto (mismo patrón que Creator Reward).
- Las fotos del producto se separan en `photos_source/` (originales) y
  `photos_generated/` (premium creadas con Nano Banana 2). Los pipelines de
  vídeo usan `generated` por defecto, fallback a `source`.
"""

from __future__ import annotations

import os
import string
from pathlib import Path


# ---------------------------------------------------------------------------
# Modelos de generación de vídeo — 3 tiers (Atlas Cloud) + 2 prompt-only
# ---------------------------------------------------------------------------
VIDEO_MODELS: dict[str, dict] = {
    "standard": {
        "name": "Seedance v1.5 Pro Fast",
        "model_id": "bytedance/seedance-v1.5-pro/image-to-video-fast",
        "type": "image_to_video",
        "supports_multi_ref": False,
        "max_input_images": 1,
        "cost_per_second": 0.018,
        "max_duration": 15,
        "max_resolution": "1080p",
        "strategy": "multi_clip_anchor",
        "use_case": "Volumen diario, validación, testing hooks",
        "tier_color": "🟢",
    },
    "advanced": {
        "name": "Seedance v1.5 Pro",
        "model_id": "bytedance/seedance-v1.5-pro/image-to-video",
        "type": "image_to_video",
        "supports_multi_ref": False,
        "max_input_images": 1,
        "cost_per_second": 0.047,
        "max_duration": 15,
        "max_resolution": "1080p",
        "strategy": "multi_clip_anchor",
        "use_case": "Productos prometedores, A/B testing",
        "tier_color": "🟡",
    },
    "pro": {
        "name": "Seedance 2.0 Fast Reference",
        "model_id": "bytedance/seedance-2.0-fast/reference-to-video",
        "type": "reference_to_video",
        "supports_multi_ref": True,
        "max_input_images": 9,
        "max_input_videos": 3,
        "max_input_audios": 3,
        "cost_per_second": 0.072,
        "max_duration": 15,
        "max_resolution": "1080p",
        "strategy": "single_shot_multishot",
        "use_case": "Productos ganadores, hero ads, packaging complejo",
        "tier_color": "🔴",
    },
    "veo3_prompt_only": {
        "name": "Veo 3 (solo prompt)",
        "model_id": None,
        "type": "prompt_only",
        "supports_multi_ref": True,
        "max_input_images": 5,
        "cost_per_second": 0.0,
        "max_duration": 8,
        "strategy": "manual_paste_in_gemini_chat",
        "use_case": "Premium puntual manual",
        "tier_color": "🟣",
    },
    "nano_banana_prompt_only": {
        "name": "Nano Banana 2 (solo prompt para fotos)",
        "model_id": None,
        "type": "prompt_only",
        "purpose": "image_generation",
        "cost_per_second": 0.0,
        "max_duration": 0,
        "strategy": "manual_paste_in_gemini_chat",
        "use_case": "Generar fotos premium del producto desde 1-2 fotos pobres",
        "tier_color": "🍌",
    },
}

DEFAULT_TIER = "standard"

# Tiers que generan vídeo automático vía Atlas Cloud
ATLAS_TIERS = ("standard", "advanced", "pro")

# Tiers prompt-only (no consumen Atlas)
PROMPT_ONLY_TIERS = ("veo3_prompt_only", "nano_banana_prompt_only")

RESOLUTIONS: dict[str, dict] = {
    "480p":     {"width": 480,  "height": 854,  "multiplier": 0.7,
                 "tiers_supported": ("advanced", "pro")},          # Standard NO ofrece 480p
    "720p":     {"width": 720,  "height": 1280, "multiplier": 1.0,
                 "tiers_supported": ("standard", "advanced", "pro")},
    "1080p-SR": {"width": 1080, "height": 1920, "multiplier": 1.5,
                 "tiers_supported": ("pro",)},                     # solo Pro (Super-Res)
    "1440p-SR": {"width": 1440, "height": 2560, "multiplier": 2.0,
                 "tiers_supported": ("pro",)},                     # solo Pro
}

DEFAULT_RESOLUTION = "720p"

# Durations totales seleccionables en UI. La app divide en clips con `duration_splitter`.
DURATIONS: list[int] = [5, 10, 12, 15, 20, 24, 25, 30]
DEFAULT_DURATION = 15

# Límites de Atlas Cloud por tier (validación en runtime).
TIER_DURATION_LIMITS: dict[str, dict[str, int]] = {
    "standard": {"min_per_clip": 4, "max_per_clip": 12},
    "advanced": {"min_per_clip": 4, "max_per_clip": 12},
    "pro":      {"min_per_clip": 4, "max_per_clip": 15},
}


# ---------------------------------------------------------------------------
# Estrategias de generación de vídeo (FUNC 5)
# ---------------------------------------------------------------------------
# Dos presets que controlan: nº y duración de clips, asignación de fotos,
# crossfade del editor, trim del primer frame y estilo de cámara descrito al
# director. Default = DYNAMIC (mejor retención TikTok).
VIDEO_STRATEGIES = ("cinematic", "dynamic")
DEFAULT_VIDEO_STRATEGY = "dynamic"

STRATEGY_CONFIG: dict[str, dict] = {
    "cinematic": {
        "label":           "🎬 Cinematográfico",
        "tagline":         "Pocos cambios de plano, calidad cinematográfica",
        "photo_strategy":  "smooth_transitions",   # foto base repetida con anchoring suave
        "crossfade_s":     0.5,                     # solapamiento al concatenar
        "trim_head_s":     0.15,                    # quita el frame "fotografía" inicial
        "camera_style":    "continuous_slow",       # cámara lenta, planos largos
    },
    "dynamic": {
        "label":           "⚡ Dinámico TikTok",
        "tagline":         "Cambios de plano frecuentes, mejor retención",
        "photo_strategy":  "rotate",                # cada clip una foto distinta
        "crossfade_s":     0.3,
        "trim_head_s":     0.15,
        "camera_style":    "varied_contained",      # cámara variada pero no caótica
    },
}

# Voces preset MiniMax por defecto. La library añadirá clones encima.
DEFAULT_VOICE_PRESETS_ES: list[dict] = [
    {"id": "Spanish_EnergeticBoy", "label": "Energético (chico, ES)"},
    {"id": "Spanish_Strong-WilledBoy", "label": "Decidido (chico, ES)"},
    {"id": "Spanish_PassionateWarrior", "label": "Apasionado (chico, ES)"},
]

NICHE_OPTIONS = ["skincare", "fitness", "hogar", "tech", "moda", "otros"]
LANGUAGE_OPTIONS = ["es", "en", "pt", "fr", "it", "de"]
COUNTRY_OPTIONS = ["ES", "MX", "AR", "CO", "CL", "PE", "US", "FR", "IT", "DE"]

PHOTO_TYPES_GENERATED = ["packshot", "lifestyle", "detail", "in_use", "macro"]
PHOTO_ORIGINS_SOURCE = ["internet", "own", "tiktok_shop_url"]

# Umbral de detección "foto pobre" — si CUALQUIER lado es menor → sugerir Nano Banana 2
LOW_RESOLUTION_THRESHOLD_PX = 1024

VIDEO_STYLES = [
    "asmr_macro",
    "ugc_natural",
    "lifestyle_aspirational",
    "cinematic_premium",
    "testimonial_voice",
    "before_after",
    "demo_use",
]

VIDEO_TYPE_SHOPPABLE = "shoppable"
VIDEO_TYPE_NORMAL = "normal"

# Pilot Program — constantes de TikTok Shop España
PILOT_WEEKLY_SHOPPABLE_LIMIT = 5
PILOT_GRADUATION_REQUIRED_VIDEOS = 6
PILOT_GRADUATION_REQUIRED_DAYS = 30
PILOT_GRADUATION_MIN_CHR = 176
PILOT_GRADUATION_REQUIRED_ORDERS = 10


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Cola de rutas relativas (dentro del Drive) donde buscar TIKTOK_SHOP cuando
# `TIKTOK_SHOP_ROOT_PATH` no está definida. La primera coincidencia gana.
# - "Mi unidad/..." aplica a Drive Desktop en Windows
# - Las rutas SIN "Mi unidad/" aplican a rclone mount en Linux (ver utils.py)
_TIKTOK_SHOP_RELATIVE_CANDIDATES = (
    os.path.join("Mi unidad", "NEBULABS_AUTOMATED_TIKTOK", "TIKTOK_SHOP"),
    os.path.join("NEBULABS_AUTOMATED_TIKTOK", "TIKTOK_SHOP"),
)


def _autodetect_shop_root() -> str | None:
    """Escanea las unidades del sistema buscando la carpeta TIKTOK_SHOP en
    Drive. Misma estrategia que `src.utils._autodetect_tiktok_root` pero
    apuntando a `NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP` (al mismo nivel que
    TIKTOK_CR, NO anidado dentro)."""
    if os.name == "nt":
        roots = [f"{letter}:\\" for letter in string.ascii_uppercase]
    else:
        home = os.path.expanduser("~")
        roots = [
            os.path.join(home, "gdrive"),
            "/mnt/gdrive",
            "/srv/gdrive",
            home,
            "/",
        ]
        media_root = "/media"
        if os.path.isdir(media_root):
            try:
                for sub in os.listdir(media_root):
                    p = os.path.join(media_root, sub, "gdrive")
                    if os.path.isdir(p):
                        roots.append(p)
            except OSError:
                pass
    for root in roots:
        if not os.path.exists(root):
            continue
        for relative in _TIKTOK_SHOP_RELATIVE_CANDIDATES:
            candidate = os.path.join(root, relative)
            if os.path.isdir(candidate):
                return candidate
    return None


def resolve_shop_root() -> str:
    """Devuelve la ruta raíz de `TIKTOK_SHOP/` como string.

    Resolución (en orden):
      1) `TIKTOK_SHOP_ROOT_PATH` del entorno si existe en disco.
      2) (Compat) `TIKTOK_SHOP_ROOT` (nombre antiguo) si existe en disco.
      3) Auto-detección: escaneo de unidades buscando
         `Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP`.
      4) Fallback `./TIKTOK_SHOP_FALLBACK/` (solo dev local — la carpeta
         puede no existir en disco, el caller debe gestionar).

    Si encuentra una ruta por auto-detección, la exporta al entorno como
    `TIKTOK_SHOP_ROOT_PATH` para que módulos posteriores la vean.

    NO crea la carpeta — solo devuelve la ruta. La creación es lazy en cada
    operación de escritura.
    """
    env_path = os.getenv("TIKTOK_SHOP_ROOT_PATH") or os.getenv("TIKTOK_SHOP_ROOT")
    if env_path and os.path.isdir(env_path):
        os.environ["TIKTOK_SHOP_ROOT_PATH"] = env_path
        return env_path

    detected = _autodetect_shop_root()
    if detected:
        os.environ["TIKTOK_SHOP_ROOT_PATH"] = detected
        return detected

    return os.path.abspath("./TIKTOK_SHOP_FALLBACK")


def tiktok_shop_root_path() -> Path:
    """Versión `Path` de `resolve_shop_root()`. Usar este helper en código nuevo."""
    return Path(resolve_shop_root())


def ensure_shop_root() -> str:
    """Garantiza que la carpeta raíz `TIKTOK_SHOP/` y sus subcarpetas
    `_users/` y `_products/` existen. Devuelve la ruta raíz."""
    root = resolve_shop_root()
    Path(root).mkdir(parents=True, exist_ok=True)
    Path(root, "_users").mkdir(exist_ok=True)
    Path(root, "_products").mkdir(exist_ok=True)
    return root


def user_drive_folder(username: str) -> str:
    """Path de la carpeta del usuario en Drive (sin crear)."""
    safe = username if username.startswith("@") else f"@{username}"
    return os.path.join(resolve_shop_root(), "_users", safe)


def product_drive_folder(slug: str) -> str:
    """Path de la carpeta del producto en Drive (sin crear)."""
    return os.path.join(resolve_shop_root(), "_products", slug)


def product_photos_source_folder(slug: str) -> str:
    """Path de fotos originales (internet/propias) del producto."""
    return os.path.join(product_drive_folder(slug), "photos_source")


def product_photos_generated_folder(slug: str) -> str:
    """Path de fotos premium generadas con Nano Banana 2."""
    return os.path.join(product_drive_folder(slug), "photos_generated")


def product_prompt_templates_folder(slug: str) -> str:
    """Path de los `.txt` con prompts (Nano Banana, Seedance hooks, etc.)."""
    return os.path.join(product_drive_folder(slug), "prompt_templates")


def user_videos_folder(username: str, product_slug: str) -> str:
    """Path donde se guardan los vídeos generados para una combinación user×product."""
    base = user_drive_folder(username)
    return os.path.join(base, "products", product_slug, "videos")


def redis_prefix() -> str:
    """Prefijo Redis del nicho. Default `tiktok_shop:`. Override por env."""
    return os.getenv("TIKTOK_SHOP_REDIS_PREFIX") or "tiktok_shop:"


def gemini_api_key() -> str | None:
    """Devuelve la primera API key Gemini disponible para el módulo TikTok Shop.

    Orden de preferencia (mismo que usa `api/gemini.py:_get_gemini_keys`):
      1. `GOOGLE_GEMINI_KEY_FREE` — proyecto sin billing (free tier).
      2. `GOOGLE_GEMINI_KEY_PAID` — proyecto con billing (límite mensual).
      3. (Compat) `GOOGLE_AI_API_KEY` o `GOOGLE_GEMINI_KEY` — nombres legacy.

    Solo se usa este helper para checks de "configurado / no configurado" en
    UI (banner del router). La selección dinámica con fallback dual la hace
    `api/gemini.py:generate_text()`.
    """
    return (
        os.getenv("GOOGLE_GEMINI_KEY_FREE")
        or os.getenv("GOOGLE_GEMINI_KEY_PAID")
        or os.getenv("GOOGLE_AI_API_KEY")
        or os.getenv("GOOGLE_GEMINI_KEY")
    )


def atlas_api_key() -> str | None:
    """Acepta el nombre nuevo (`ATLASCLOUD_API_KEY` per doc) o el legacy
    (`ATLAS_CLOUD_API_KEY`)."""
    return os.getenv("ATLASCLOUD_API_KEY") or os.getenv("ATLAS_CLOUD_API_KEY")


def atlas_base_url() -> str:
    """URL base de Atlas Cloud. Default: `https://api.atlascloud.ai/api/v1` (per doc).
    Override con `ATLASCLOUD_BASE_URL` o `ATLAS_CLOUD_BASE_URL`."""
    return (
        os.getenv("ATLASCLOUD_BASE_URL")
        or os.getenv("ATLAS_CLOUD_BASE_URL")
        or "https://api.atlascloud.ai/api/v1"
    ).rstrip("/")


def atlas_is_configured() -> bool:
    """True si tenemos API key de Atlas Cloud en el .env. URL tiene default."""
    return bool(atlas_api_key())


# Multiplicadores de coste por resolución (Atlas Cloud, doc oficial)
RESOLUTION_COST_MULTIPLIER: dict[str, float] = {
    "480p": 0.7,
    "720p": 1.0,
    "1080p-SR": 1.5,
    "1440p-SR": 2.0,
}

# Modo de subida de imágenes a Atlas Cloud. Default `base64` (funciona en Pro).
# Para Standard/Advanced que requieren URL pública: configurar R2/S3 (TODO).
PHOTO_UPLOAD_MODE_DEFAULT = "base64"
