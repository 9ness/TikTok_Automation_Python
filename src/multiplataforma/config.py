"""Configuración del publicador Multiplataforma.

Sube los vídeos YA montados por la fábrica (POV BOF, POV BOF Largo, Multimodo,
Viralización 1K…) a Instagram Reels, Facebook Page Reels, Threads y Pinterest
por sus APIs OFICIALES, con enlace de afiliado (Amazon / SHEIN).

Decisiones:
- Las credenciales de la APP (Meta, Pinterest) van en `.env`; los TOKENS de
  cada cuenta NO: viven en Redis dentro de `CuentaDestino`, porque hay varias
  cuentas por persona y se renuevan sin desplegar.
- Sin token (o sin id de destino) una plataforma va en MODO PRUEBA: se
  registra qué se haría y no se llama a la red. Igual con
  `MULTIPLATAFORMA_DRY_RUN=1` para todo el módulo.
- Sin cost tracking: las APIs de publicación de Meta y Pinterest son gratuitas
  (no hay `record_*` que llamar, a propósito).
"""

from __future__ import annotations

import os
from pathlib import Path

PLATAFORMAS: tuple[str, ...] = ("instagram", "facebook", "threads", "pinterest")
TIPOS: tuple[str, ...] = ("producto", "prueba_viral")

# Estados de cada plataforma dentro de una publicación.
ESTADO_PENDIENTE = "pendiente"
ESTADO_SIMULADO = "simulado"  # se hizo en modo prueba; se reintenta al haber token
ESTADO_ERROR = "error"  # falló, quedan intentos
ESTADO_PUBLICADO = "publicado"  # final
ESTADO_FALLIDO = "fallido"  # final: agotó intentos o error no reintentable
ESTADOS_FINALES = (ESTADO_PUBLICADO, ESTADO_FALLIDO)

MAX_INTENTOS = int(os.getenv("MULTIPLATAFORMA_MAX_INTENTOS", "3"))

# Límites de publicación por cuenta y plataforma en 24h móviles. Los de Meta
# son los oficiales (IG 50 posts/24h por API, Page Reels 30/24h, Threads 250);
# Pinterest no publica un tope fijo de pines: se pone uno prudente.
LIMITES_24H: dict[str, int] = {
    "instagram": int(os.getenv("MULTIPLATAFORMA_LIMITE_IG", "50")),
    "facebook": int(os.getenv("MULTIPLATAFORMA_LIMITE_FB", "30")),
    "threads": int(os.getenv("MULTIPLATAFORMA_LIMITE_THREADS", "250")),
    "pinterest": int(os.getenv("MULTIPLATAFORMA_LIMITE_PINTEREST", "50")),
}

# Hashtags como máximo por plataforma (IG limita a 5 desde 2025; Threads
# admite una sola etiqueta de tema).
MAX_HASHTAGS: dict[str, int] = {"instagram": 5, "facebook": 3, "threads": 1, "pinterest": 5}

# Longitudes máximas de texto que aceptan las APIs.
MAX_CHARS: dict[str, int] = {"instagram": 2200, "facebook": 2200, "threads": 500, "pinterest": 800}
MAX_TITULO_PINTEREST = 100

# Dominios acortadores prohibidos (Amazon exige enlaces completos y los
# acortadores genéricos bajan el alcance y huelen a spam).
ACORTADORES: tuple[str, ...] = (
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "cutt.ly", "is.gd",
    "buff.ly", "rebrand.ly", "shorturl.at", "tiny.cc", "rb.gy", "amzn.to", "amzn.eu",
)

AMAZON_DOMINIO = os.getenv("MULTIPLATAFORMA_AMAZON_DOMINIO", "www.amazon.es")

# Red: timeouts y espera del procesado de vídeo en cada plataforma.
HTTP_TIMEOUT_S = float(os.getenv("MULTIPLATAFORMA_HTTP_TIMEOUT_S", "60"))
UPLOAD_TIMEOUT_S = float(os.getenv("MULTIPLATAFORMA_UPLOAD_TIMEOUT_S", "600"))
POLL_INTERVALO_S = float(os.getenv("MULTIPLATAFORMA_POLL_INTERVALO_S", "10"))
POLL_MAX_S = float(os.getenv("MULTIPLATAFORMA_POLL_MAX_S", "600"))

# Vida de la URL firmada del vídeo (IG/Threads lo descargan al crear el
# contenedor; con unas horas sobra).
VIDEO_URL_TTL_S = int(os.getenv("MULTIPLATAFORMA_VIDEO_URL_TTL_S", str(6 * 3600)))
EXTENSIONES_SERVIBLES = (".mp4", ".mov", ".jpg", ".jpeg", ".png")

# ---- Ingesta desde el Drive montado ----
# Ruta COMPLETA desde la raíz del mount (como `DRIVE_UPLOAD_ROOT` del resto
# del Programa 4). Por cuenta: `<raíz>/<slug>/{viralizacion,producto}/` y,
# dentro de cada una, `publicados/` con lo ya subido a todas las plataformas.
AI_PRO_SUBDIR = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO"
DRIVE_SUBDIR = f"{AI_PRO_SUBDIR}/Multiplataforma"
CARPETAS_INGESTA: dict[str, str] = {"viralizacion": "prueba_viral", "producto": "producto"}
CARPETA_PUBLICADOS = "publicados"
EXTENSIONES_INGESTA = (".mp4", ".mov")
ZONA_HORARIA = os.getenv("MULTIPLATAFORMA_TZ", "Europe/Madrid")
RITMO_DEFAULT: dict[str, int] = {"prueba_viral": 1, "producto": 1}  # vídeos/día
HORAS_DEFAULT: dict[str, list[str]] = {"prueba_viral": ["19:00"], "producto": ["13:00"]}


def raiz_drive() -> Path:
    """Carpeta `Multiplataforma` del Drive montado.

    Override `MULTIPLATAFORMA_DRIVE_ROOT` (apunta YA a la carpeta Multiplataforma).
    Sin mount (dev local) cae a `API_TEMP_ROOT/multiplataforma`."""
    override = os.getenv("MULTIPLATAFORMA_DRIVE_ROOT", "").strip()
    if override:
        return Path(override)
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        return raiz / DRIVE_SUBDIR
    return Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "multiplataforma"


def raices_servibles() -> list[Path]:
    """Únicos árboles desde los que `/archivo/{token}` sirve ficheros."""
    raices = [raiz_drive(), Path.cwd() / "temp_work"]
    tmp = os.getenv("API_TEMP_ROOT", "").strip()
    if tmp:
        raices.append(Path(tmp))
    # Los vídeos que lista «Mis tandas» (POV BOF, Largo, Moda Mujer…) viven en
    # el árbol del Programa 4 del Drive montado: se sirven de ahí, nunca de
    # fuera (y solo con token firmado y extensión de vídeo/imagen).
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        raices.append(raiz / AI_PRO_SUBDIR)
    return raices


def graph_version() -> str:
    return os.getenv("META_GRAPH_VERSION", "v24.0").strip()


def graph_base() -> str:
    return f"https://graph.facebook.com/{graph_version()}"


def rupload_base() -> str:
    return "https://rupload.facebook.com"


def threads_base() -> str:
    return os.getenv("THREADS_API_BASE", "https://graph.threads.net/v1.0").rstrip("/")


def pinterest_base() -> str:
    # Con acceso «Trial» Pinterest solo deja escribir en el sandbox
    # (https://api-sandbox.pinterest.com/v5); con «Standard», producción.
    return os.getenv("PINTEREST_API_BASE", "https://api.pinterest.com/v5").rstrip("/")


def meta_app_id() -> str:
    return os.getenv("META_APP_ID", "").strip()


def meta_app_secret() -> str:
    return os.getenv("META_APP_SECRET", "").strip()


def pinterest_app_id() -> str:
    return os.getenv("PINTEREST_APP_ID", "").strip()


def pinterest_app_secret() -> str:
    return os.getenv("PINTEREST_APP_SECRET", "").strip()


def dry_run_global() -> bool:
    return os.getenv("MULTIPLATAFORMA_DRY_RUN", "").strip().lower() in ("1", "true", "si", "sí", "yes")


def redis_prefix() -> str:
    """Prefijo Redis del módulo. Default `multiplataforma:`. Override por env."""
    return os.getenv("MULTIPLATAFORMA_REDIS_PREFIX") or "multiplataforma:"


def base_publica() -> str:
    return os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/") or "https://factory.nebulabsmedia.com"


# ── Página pública /links/<cuenta> ─────────────────────────────────────────
# Logo y portada de cada cuenta: `Multiplataforma/_marca/<slug>_logo.*` y
# `<slug>_portada*.*` + `<slug>_fondo*.*` (vertical 9:16 para el móvil; las mismas imágenes del perfil de IG/FB, para que quien
# entra desde la bio reconozca la marca). Sin fichero, la página pone iniciales.
MARCA_SUBDIR = "_marca"
MARCA_EXTENSIONES = (".jpg", ".jpeg", ".png", ".webp")

# Colores de la página por cuenta (sacados de su logo). `claro` = fondo claro.
TEMA_DEFAULT: dict = {"fondo": "#0b1120", "acento": "#14b8a6", "acento2": "#5eead4", "claro": False,
                      "lema": "Lo que sale en mis vídeos, con su enlace."}
TEMAS: dict[str, dict] = {
    "viva_shop": {"fondo": "#0a1a4a", "acento": "#f7931e", "acento2": "#ffc72c", "claro": False,
                  "lema": "Los chollos de mis vídeos, con su enlace 🛒"},
    "ama_shop": {"fondo": "#f6e8de", "acento": "#c96a52", "acento2": "#4a5f94", "claro": True,
                 "lema": "Mis prendas favoritas, con su enlace 🤍"},
    "viva_salud": {"fondo": "#06281f", "acento": "#4ade80", "acento2": "#86efac", "claro": False,
                   "lema": "Bienestar del día a día, con su enlace 🌿"},
}
# Franja de urgencia: honesta (sin inventar descuentos ni plazos).
BANNER_LINKS = "🔥 Ofertas activas · los precios cambian a diario"


def tema_links(slug: str) -> dict:
    return {**TEMA_DEFAULT, **TEMAS.get(slug, {})}


def fichero_marca(slug: str, tipo: str) -> Path | None:
    """`tipo` = logo | portada | fondo. Primer fichero `<slug>_<tipo>*` de `_marca`."""
    carpeta = raiz_drive() / MARCA_SUBDIR
    try:
        for p in sorted(carpeta.glob(f"{slug}_{tipo}*")):
            if p.is_file() and p.suffix.lower() in MARCA_EXTENSIONES:
                return p
    except OSError:
        return None
    return None
