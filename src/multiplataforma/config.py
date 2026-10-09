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
import shutil
import threading
import time
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

# Reels de prueba (`trial_params`) de IG. Apagado: con nuestra app Meta lo
# rechaza (code=10, subcode=2207081, «Application does not have permission»)
# aunque el token tenga instagram_content_publish. =1 si algún día lo da.
IG_TRIAL_REELS = os.getenv("MULTIPLATAFORMA_IG_TRIAL", "0") == "1"

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

# Hashtags de los vídeos de producto (Mis tandas) según lo que es el producto:
# la primera fila cuyas palabras salgan en el título manda. El primero es el
# que queda en Threads (una sola etiqueta). La tienda (SHEIN/Amazon) se añade
# detrás en `tandas._hashtags`.
HASHTAGS_CATEGORIA: list[tuple[tuple[str, ...], list[str]]] = [
    (("bolso", "bandolera", "mochila"), ["bolsos", "bolso", "modamujer"]),
    (("bota", "zapat", "sandalia", "deportiva"), ["zapatos", "zapatillas", "modamujer"]),
    (("vestido", "falda", "camiseta", "pantal", "jersey", "chaqueta", "abrigo", "blusa", "top ",
      "conjunto", "sudadera", "chaleco", "cardigan", "mono "), ["outfit", "moda", "modamujer"]),
    (("serum", "crema", "spf", "antimanchas", "facial", "micelar", "retin", "cosmetic", "rellenador",
      "maquillaje", "bronceador"), ["skincare", "belleza", "cuidadodelapiel"]),
    (("creatina", "proteina", "whey", "colageno", "magnesio", "capsula", "vitamina", "melatonina",
      "ashwagandha", "shilajit", "probiotic", "biotina", "inositol", "moringa", "curcuma", "matcha",
      "gomita"), ["bienestar", "salud", "suplementos"]),
    (("masaje", "rodillera", "depiladora", "cortapelo", "afeitadora", "secador", "alisador"),
     ["cuidadopersonal", "bienestar", "salud"]),
    (("cinta de correr", "bicicleta", "mancuerna", "fitness", "gimnasio", "escaladora", "vibratoria"),
     ["fitness", "entrenamiento", "gymencasa"]),
    (("jardin", "tumbona", "gazebo", "plantas", "camping", "paddle", "tienda de campana"),
     ["jardin", "terraza", "airelibre"]),
    (("taladro", "herramienta", "escalera", "clavadora"), ["bricolaje", "herramientas", "hogar"]),
]
# Productos de temporada: el enlace se guarda todo el año, pero `encolar` solo
# los publica en estos meses (p. ej. tumbonas y piscinas no salen en Q4).
TEMPORADAS: dict[str, tuple[int, ...]] = {
    "verano": (4, 5, 6, 7, 8, 9),
    "invierno": (10, 11, 12, 1, 2, 3),
    "navidad": (11, 12),
}
HASHTAGS_DEFECTO = ["hogar", "casa", "ideasparacasa"]
HASHTAGS_TIENDA = {"shein": ["shein", "sheinhaul"], "amazon": ["amazonfinds", "chollos"]}

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
# Desfase de ±N minutos sobre cada hora (14:00 → 13:57, 14:03…) para no
# publicar siempre al minuto exacto. Fijo por cuenta y día (hash), 0 lo apaga.
DESFASE_MAX_MIN = int(os.getenv("MULTIPLATAFORMA_DESFASE_MIN", "4"))
# Plataformas por tipo cuando el vídeo no dice otra cosa. Los virales de
# viralización son para ganar seguidores en Instagram (clase 7/10: «solo
# mételos en reel de prueba»); FB y Threads ya tienen enlace y no los necesitan.
PLATAFORMAS_POR_TIPO: dict[str, tuple[str, ...]] = {"prueba_viral": ("instagram",)}


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


# `_marca` se SUBE al Drive (es donde el operador deja logos y fondos), pero la
# página pública /links no lo lee de ahí: listar el mount de rclone a veces
# tarda segundos y en el móvil la página se quedaba en «cargando». Se sirve una
# COPIA en el disco local (`temp_work/multiplataforma_marca/`) y un hilo la
# pone al día con el Drive cada `_MARCA_TTL_S`, sin hacer esperar a nadie.
_MARCA_TTL_S = 600
_marca_sync = {"ultimo": 0.0, "en_curso": False}
_marca_lock = threading.Lock()


def _marca_local() -> Path:
    return Path.cwd() / "temp_work" / "multiplataforma_marca"


def sincronizar_marca() -> None:
    """Copia al disco local lo nuevo o cambiado de `_marca` del Drive y borra
    lo que ya no está allí."""
    origen = raiz_drive() / MARCA_SUBDIR
    destino = _marca_local()
    try:
        destino.mkdir(parents=True, exist_ok=True)
        vistos = set()
        for p in origen.iterdir():
            if not p.is_file() or p.suffix.lower() not in MARCA_EXTENSIONES:
                continue
            vistos.add(p.name)
            d = destino / p.name
            st = p.stat()
            if not d.exists() or d.stat().st_size != st.st_size or d.stat().st_mtime < st.st_mtime:
                tmp = d.with_suffix(d.suffix + ".tmp")
                shutil.copyfile(p, tmp)
                os.replace(tmp, d)
        for d in destino.iterdir():
            if d.is_file() and d.name not in vistos:
                d.unlink(missing_ok=True)
    except OSError:
        pass


def _sincronizar_en_hilo() -> None:
    try:
        sincronizar_marca()
    finally:
        with _marca_lock:
            _marca_sync["ultimo"] = time.time()
            _marca_sync["en_curso"] = False


def fichero_marca(slug: str, tipo: str) -> Path | None:
    """`tipo` = logo | portada | fondo. Primer fichero `<slug>_<tipo>*` de la
    copia local de `_marca` (la primera vez la hace esperando)."""
    local = _marca_local()
    with _marca_lock:
        caducada = time.time() - _marca_sync["ultimo"] > _MARCA_TTL_S
        lanzar = caducada and not _marca_sync["en_curso"]
        if lanzar:
            _marca_sync["en_curso"] = True
    if lanzar:
        if local.is_dir():
            threading.Thread(target=_sincronizar_en_hilo, daemon=True).start()
        else:
            _sincronizar_en_hilo()
    try:
        for p in sorted(local.glob(f"{slug}_{tipo}*")):
            if p.is_file() and p.suffix.lower() in MARCA_EXTENSIONES:
                return p
    except OSError:
        return None
    return None


# ── Música de fondo para los vídeos MUDOS de Mis tandas ────────────────────
# La API de Meta no deja elegir canción de Instagram: la música se mezcla en
# el fichero. Banco en el Drive: `Multiplataforma/_musica/<estilo>/*.mp3`
# (Mixkit Stock Music Free License, ver `_musica/LICENCIA.md`). Las copias con
# música van al disco local persistente (`temp_work/multiplataforma_musica/`,
# protegido en `temp_cleanup`): los originales de Mis tandas no se tocan.
MUSICA_SUBDIR = "_musica"
MUSICA_ESTILO_NEUTRO = "lofi_otono"
MUSICA_LUFS = float(os.getenv("MULTIPLATAFORMA_MUSICA_LUFS", "-18"))
MUSICA_FADE_IN_S = 0.8
MUSICA_FADE_OUT_S = 1.5
MUSICA_INICIO_S = 4.0  # salta la entrada (casi muda) de la pista si da para ello


def musica_dir() -> Path:
    override = os.getenv("MULTIPLATAFORMA_MUSICA_DIR", "").strip()
    return Path(override) if override else raiz_drive() / MUSICA_SUBDIR


def musica_trabajo_dir() -> Path:
    override = os.getenv("MULTIPLATAFORMA_MUSICA_TRABAJO", "").strip()
    return Path(override) if override else Path.cwd() / "temp_work" / "multiplataforma_musica"
