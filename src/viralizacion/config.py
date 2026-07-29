"""Constantes y resolución de paths del Programa 4 — Viralización.

Decisiones:
- Los recursos (vídeos de gancho, audios, paisajes, música) viven en una
  carpeta LOCAL persistente del VPS (NO en Drive montado, NO en `/tmp`,
  NO dentro del repo git) — son ficheros pesados (el vídeo de paisajes
  pesa ~2.5GB) que se reutilizan en cientos de renders y no tiene sentido
  releerlos de Drive en cada job. `VIRALIZACION_ASSETS_PATH` permite
  override; si no se define, autodetecta un default razonable.
- Los vídeos finales se suben a Drive (`gdrive:NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/VIRALIZACION/<cuenta>_<fecha>/<ponente>/`)
  vía `services/drive_uploader.py`, pero NO se leen de vuelta desde ahí.
- Sin cost tracking: este programa no llama a ninguna API de pago (todo
  ffmpeg + Whisper local + rclone). El wrapper `dispatch_job` sigue
  envolviendo el job en `cost_tracking.start_job/finalize_and_persist`
  automáticamente (no hace daño, simplemente no registra líneas), pero
  el runner NUNCA llama a `record_*` — es intencional, ver VIRALIZACION_MODULE.md.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Ponentes soportados
# ---------------------------------------------------------------------------
# slug -> metadata. `drive_folder` es el nombre de la subcarpeta bajo
# "Skool/Estrategia viralización/España/" en Drive (compartido con la cuenta
# del operador) de donde se descargaron los recursos originales — se guarda
# solo como referencia/documentación, el pipeline SIEMPRE lee de local.
PONENTES: dict[str, dict] = {
    "pablo": {
        "label": "Pablo Motos",
        "drive_folder": "Pablo Motos",
    },
    "victor": {
        "label": "Víctor Küppers",
        "drive_folder": "Victor Kuppers",
    },
}


def is_known_ponente(slug: str) -> bool:
    return slug in PONENTES


def ponente_label(slug: str) -> str:
    return PONENTES.get(slug, {}).get("label", slug)


# ---------------------------------------------------------------------------
# Paths — raíz local persistente de assets
# ---------------------------------------------------------------------------
_DEFAULT_CANDIDATES = (
    "/home/nebulabsai/viralizacion_assets",
    os.path.join(os.path.expanduser("~"), "viralizacion_assets"),
)


def resolve_assets_root() -> str:
    """Devuelve la ruta raíz local de assets de Viralización.

    Resolución (en orden):
      1) `VIRALIZACION_ASSETS_PATH` del entorno si existe en disco.
      2) Auto-detección: primer candidato de `_DEFAULT_CANDIDATES` que
         exista en disco.
      3) Fallback: primer candidato (se crea lazy si no existe).
    """
    env_path = os.getenv("VIRALIZACION_ASSETS_PATH")
    if env_path and os.path.isdir(env_path):
        return env_path

    for candidate in _DEFAULT_CANDIDATES:
        if os.path.isdir(candidate):
            return candidate

    return env_path or _DEFAULT_CANDIDATES[0]


def assets_root_path() -> Path:
    return Path(resolve_assets_root())


def ensure_assets_root() -> Path:
    root = assets_root_path()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ponente_folder(slug: str) -> Path:
    return assets_root_path() / slug


def ponente_gancho_folder(slug: str) -> Path:
    return ponente_folder(slug) / "gancho"


def ponente_audios_folder(slug: str) -> Path:
    return ponente_folder(slug) / "audios"


def ponente_gancho_video(slug: str) -> Path | None:
    folder = ponente_gancho_folder(slug)
    if not folder.is_dir():
        return None
    videos = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in (".mp4", ".mov", ".mkv")
    )
    return videos[0] if videos else None


def ponente_audio_files(slug: str) -> list[Path]:
    """Lista ordenada (alfabética, determinista) de audios del ponente."""
    folder = ponente_audios_folder(slug)
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in (".mp3", ".wav", ".m4a")
    )


def paisajes_folder() -> Path:
    return assets_root_path() / "paisajes"


def paisajes_video() -> Path | None:
    folder = paisajes_folder()
    if not folder.is_dir():
        return None
    videos = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in (".mp4", ".mov", ".mkv")
    )
    return videos[0] if videos else None


def musica_folder() -> Path:
    return assets_root_path() / "musica"


def musica_file() -> Path | None:
    folder = musica_folder()
    if not folder.is_dir():
        return None
    files = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in (".mp3", ".wav", ".m4a")
    )
    return files[0] if files else None


def work_root() -> Path:
    """Raíz ESCRIBIBLE (staging + caches).

    En Docker el mount de assets suele ser del host (uid 1000) y el
    proceso corre como `app` (uid 999) → Permission denied al mkdir en
    staging. Preferimos:
      1) VIRALIZACION_WORK_PATH
      2) API_TEMP_ROOT/viralizacion  (volumen docker `api_temp`, escribible)
      3) assets_root/_work          (dev local, mismo usuario)
    """
    env = os.getenv("VIRALIZACION_WORK_PATH")
    if env:
        root = Path(env)
    else:
        api_temp = os.getenv("API_TEMP_ROOT")
        if api_temp:
            root = Path(api_temp) / "viralizacion"
        else:
            root = assets_root_path() / "_work"
    root.mkdir(parents=True, exist_ok=True)
    return root


def staging_folder() -> Path:
    """MP4 de un batch antes de subir a Drive. Subcarpeta única por batch."""
    root = work_root() / "staging"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cache_folder() -> Path:
    """Cachés de escaneo y transcripciones (siempre en work_root escribible)."""
    root = work_root() / "_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _seed_cache_from_legacy(work: Path, legacy: Path) -> Path:
    """Si hay caché legacy en assets (solo-lectura) y aún no en work, cópiala."""
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists():
        return work
    if legacy.is_file():
        try:
            work.write_bytes(legacy.read_bytes())
            return work
        except OSError:
            # work no escribible o legacy ilegible → devolver legacy (read)
            return legacy
    return work


def hook_candidates_cache_path(slug: str) -> Path:
    """JSON de ganchos: escribible en work_root; se siembra desde assets si existe."""
    return _seed_cache_from_legacy(
        work_root() / "hook_candidates" / f"{slug}.json",
        ponente_folder(slug) / "hook_candidates.json",
    )


def paisaje_candidates_cache_path() -> Path:
    """JSON de paisajes: escribible en work_root; se siembra desde assets si existe."""
    return _seed_cache_from_legacy(
        work_root() / "paisaje_candidates.json",
        paisajes_folder() / "paisaje_candidates.json",
    )


def transcript_cache_path(slug: str, audio_path: Path) -> Path:
    cache_dir = cache_folder() / "transcripts" / slug
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{audio_path.stem}.json"


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
def redis_prefix() -> str:
    """Prefijo Redis del programa. Default `viralizacion:`. Override por env."""
    return os.getenv("VIRALIZACION_REDIS_PREFIX") or "viralizacion:"


# ---------------------------------------------------------------------------
# Drive de destino (subida del batch final)
# ---------------------------------------------------------------------------
DRIVE_REMOTE = "gdrive:"
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/VIRALIZACION"


def sanitize_account_name(nombre_cuenta: str) -> str:
    """Sanea el nombre de cuenta para que sea un nombre de carpeta válido:
    sin caracteres raros, espacios -> guion_bajo."""
    name = (nombre_cuenta or "").strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9_\-]", "", name)
    return name or "sin_nombre"


# ---------------------------------------------------------------------------
# Render — parámetros validados por el operador (ver VIRALIZACION_MODULE.md)
# ---------------------------------------------------------------------------
TARGET_W, TARGET_H = 1080, 1920
TARGET_FPS = 30

# Tope de duración del vídeo final (diseño: 20-60s). Audios largos se
# trocean en ventanas no solapadas por ronda — ver `audio_window_for_round`.
MAX_VIDEO_DURATION_S = 90.0
MIN_VIDEO_DURATION_S = 20.0

# Encode final: velocidad + peso TikTok (~15-40MB / 50s).
FFMPEG_PRESET = "veryfast"
FFMPEG_CRF = 23
FFMPEG_AUDIO_BITRATE = "128k"
# Pre-extract de clips individuales (fase 1 del renderer, anti-OOM).
FFMPEG_CLIP_PRESET = "ultrafast"
FFMPEG_CLIP_CRF = 18

HOOK_DUR = 3.0
PAISAJE_CLIP_TARGET_S = 4.5

# Umbral de detección de cara en primer plano (altura del bounding box /
# altura del frame). Igual que el prototipo validado.
FACE_HEIGHT_FRAC_THRESHOLD = 0.22
FACE_SAMPLE_STEP_S = 1.0

# Paisajes: saltar intro/outro del vídeo fuente (CTAs, mapas, etc.)
PAISAJES_SKIP_HEAD_S = 60.0
PAISAJES_SKIP_TAIL_S = 60.0

TRANSITION_HOOK = ("hblur", 0.35)
TRANSITION_LANDSCAPE = ("fadeblack", 0.9)

VOICE_VOLUME = 1.0
MUSIC_VOLUME = 0.75
MUSIC_FADEOUT_DUR = 0.5

EQ_BASE_CONTRAST = 1.14
EQ_BASE_SATURATION = 1.25
EQ_BASE_BRIGHTNESS = 0.06
EQ_BASE_GAMMA = 1.08
VIGNETTE_FILTER_BASE = "vignette=angle=PI/4.2:mode=forward"
NOISE_FILTER_BASE = "noise=alls=8:allf=t+u"

SUB_FONT = "DejaVu Sans"
SUB_FONTSDIR = "/usr/share/fonts/truetype/dejavu"
SUB_FONTSIZE = 68
SUB_MAX_WORDS = 7
SUB_MAX_DURATION = 2.5
SUB_PAUSE_BREAK = 0.45
SUB_MIN_WORDS_BEFORE_PAUSE_BREAK = 3
SUB_MARGIN_LR = 145

WHISPER_MODEL_SIZE = "small"
WHISPER_LANGUAGE = "es"

# Por defecto SIN música de fondo: se añade solo si el operador la marca
# explícitamente. Antes la ronda 1 salía siempre con "Musica Reels.MP3"
# aunque no se pidiera.
DEFAULT_MUSIC_ROUNDS = 0

# ---------------------------------------------------------------------------
# Anti-fingerprint: jitter aleatorio POR CLIP y POR VÍDEO
# ---------------------------------------------------------------------------
# Si todos los vídeos generados con esta plantilla comparten EXACTAMENTE el
# mismo encuadre/zoom, la misma cadencia de paisajes y el mismo grado de
# color, es una huella reconocible ("hecho con la misma plantilla
# automatizada") que TikTok puede usar para shadowban/copy-strike en cadena
# entre cuentas. Para evitarlo, cada clip/vídeo sortea sus propios valores
# dentro de estos rangos (sin seed fija — ni dos vídeos del mismo lote y
# mismo estilo quedan idénticos). Rangos ajustables aquí.

# Zoom EXTRA (encima del mínimo necesario para cubrir 1080x1920), aplicado
# por clip. >1.0 acerca el crop al centro — beneficio doble: variedad visual
# + más margen de seguridad frente a marcas de agua/rótulos de borde.
HOOK_ZOOM_JITTER_RANGE = (1.0, 1.08)      # conservador: no recortar frente/barbilla
PAISAJE_ZOOM_JITTER_RANGE = (1.0, 1.18)   # hay margen de sobra, más agresivo

# Duración individual de cada tramo de paisaje (la MEDIA ronda ~4.5s pero
# cada clip varía dentro de este rango; la SUMA total siempre cuadra exacta
# con `fill_duration` — ver `pipeline/renderer.py:_jittered_paisaje_durations`).
PAISAJE_CLIP_DUR_JITTER_RANGE = (3.5, 5.5)

# Margen que hay que dejar libre en cada clip de la biblioteca para el SOLAPE
# de las transiciones: el renderer extrae `duración + medio fundido` por cada
# lado. Sin reservarlo, una ventana pegada al borde del clip pide material que
# no existe y ffmpeg congela el último fotograma (vídeo de 49s con 470 frames).
CLIP_TRANSITION_PAD_S = 1.3

# Duración de la transición paisaje→paisaje (antes fija en 0.9s). La
# transición gancho→paisaje (hblur) se mantiene fija en 0.35s — es la
# validada explícitamente por el operador y no aporta tanta "huella" al
# ser una única transición por vídeo.
TRANSITION_LANDSCAPE_JITTER_RANGE = (0.7, 1.1)

# +-5% de variación aleatoria POR VÍDEO (no por clip) en contrast/saturation/
# brightness del filtro "película" base — mismo look aprobado, sin ser un
# valor pelado idéntico en cada render.
EQ_JITTER_FRAC = 0.05

# Estilo G "Cuadrado": lado del recuadro y radio de las esquinas, sobre el
# lienzo 1080x1920. 940 deja margen negro a los lados y bastante arriba y
# abajo, que es la proporción de los vídeos de referencia.
SQUARE_SIDE = 940
SQUARE_RADIUS = 90


def audio_window_for_round(audio_duration: float, ronda: int) -> tuple[float, float]:
    """Ventana (start, duration) del audio fuente para esta ronda.

    Si el audio cabe en MAX_VIDEO_DURATION_S devuelve (0, audio_duration).
    Si es mas largo, trocea en ventanas no solapadas de MAX_VIDEO_DURATION_S;
    la ronda N usa la ventana ((N-1) % n_windows). Un audio de 163s da ~3
    trozos distintos de ~55s en vez de un monstruo de 163s.
    """
    max_d = float(MAX_VIDEO_DURATION_S)
    min_d = float(MIN_VIDEO_DURATION_S)
    if audio_duration <= max_d:
        return 0.0, float(audio_duration)
    n_full = max(1, int(audio_duration // max_d))
    remainder = audio_duration - n_full * max_d
    n_windows = n_full + (1 if remainder >= min_d else 0)
    if n_windows <= 0:
        n_windows = 1
    idx = (max(1, int(ronda)) - 1) % n_windows
    start = idx * max_d
    if start >= audio_duration:
        start = max(0.0, audio_duration - max_d)
    dur = min(max_d, audio_duration - start)
    if dur < min_d and start > 0:
        start = max(0.0, audio_duration - max_d)
        dur = min(max_d, audio_duration - start)
    return float(start), float(dur)
