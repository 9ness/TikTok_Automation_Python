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
# `pais` decide dos cosas que antes eran globales: en qué idioma transcribe
# Whisper (Billy Graham habla inglés) y de qué pool salen los paisajes — con
# uno solo, los vídeos de EEUU saldrían con b-roll de España.
PONENTES: dict[str, dict] = {
    "pablo": {
        "label": "Pablo Motos",
        "drive_folder": "Pablo Motos",
        "pais": "es",
    },
    "victor": {
        "label": "Víctor Küppers",
        "drive_folder": "Victor Kuppers",
        "pais": "es",
    },
    "mario": {
        "label": "Mario Alonso Puig",
        "drive_folder": "Mario Alonso Puig",
        "pais": "es",
    },
    "segarra": {
        "label": "Dr. Manuel Segarra",
        "drive_folder": "Dr. Manuel Segarra",
        "pais": "es",
    },
    "billy": {
        "label": "Billy Graham",
        "drive_folder": "Billy Graham",
        "pais": "us",
        # Los sermones llevan rótulos QUEMADOS en todos los fotogramas: logo
        # abajo a la izquierda y "877-772-4559 / PeaceWithGod.tv" abajo a la
        # derecha. El recorte 9:16 los deja fuera mientras se quede centrado,
        # pero con la cara muy a la derecha (cx_frac 0.65-0.68) el teléfono
        # entra en cuadro — comprobado con capturas. Se limita el encuadre a
        # la franja donde se sabe que no hay texto.
        "cx_seguro": (0.34, 0.62),
    },
}

# Idioma de Whisper por país. Antes era una constante global "es", y con un
# ponente en inglés Whisper transcribía fonética española: los subtítulos
# salían ilegibles.
IDIOMA_POR_PAIS = {"es": "es", "us": "en"}

PAIS_LABEL = {"es": "España", "us": "Estados Unidos"}


def cx_seguro_de(slug: str) -> tuple[float, float] | None:
    """Franja horizontal donde el recorte no pilla gráficos quemados.

    None = el vídeo del ponente está limpio y se puede encuadrar libremente.
    """
    return PONENTES.get(slug, {}).get("cx_seguro")


def pais_de(slug: str) -> str:
    return PONENTES.get(slug, {}).get("pais", "es")


def idioma_de(slug: str) -> str:
    return IDIOMA_POR_PAIS.get(pais_de(slug), "es")


def ponentes_de_pais(pais: str) -> list[str]:
    return [s for s, m in PONENTES.items() if m.get("pais", "es") == pais]


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


def ponente_originales_folder(slug: str) -> Path:
    """Audios largos sin trocear (charlas de YouTube subidas por el operador).

    Va DENTRO de `audios/` y con nombre `_originales` porque `ponente_audio_files`
    no entra en subcarpetas: así el audio de 8 minutos no aparece como si fuera
    un candidato para un vídeo.
    """
    return ponente_audios_folder(slug) / "_originales"


# Todo lo que ffmpeg abre como audio. La lista era `.mp3/.wav/.m4a` y dejaba
# fuera lo que sale de descargar de YouTube (`.opus`, `.webm`, `.m4a` dentro de
# `.mp4`): el fichero se copiaba a la carpeta y simplemente no aparecía en el
# banco, sin ningún aviso. El pipeline no necesita que sea MP3 — Whisper y el
# render pasan por ffmpeg igual.
AUDIO_EXTS = (
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus",
    ".flac", ".wma", ".webm", ".mp4", ".mov", ".mkv",
)


def ponente_audio_files(slug: str) -> list[Path]:
    """Lista ordenada (alfabética, determinista) de audios del ponente."""
    folder = ponente_audios_folder(slug)
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )


def paisajes_folder(pais: str = "es") -> Path:
    """Carpeta del vídeo fuente de paisajes.

    España se queda en `paisajes/` tal cual para no romper lo que ya existe;
    los países nuevos cuelgan con sufijo (`paisajes_us/`).
    """
    if pais == "es":
        return assets_root_path() / "paisajes"
    return assets_root_path() / f"paisajes_{pais}"


def paisajes_video(pais: str = "es") -> Path | None:
    folder = paisajes_folder(pais)
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
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
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


def ponente_ganchos_dir(slug: str) -> Path:
    """Carpeta de ganchos YA recortados (3s cada uno).

    Existe para no tener el vídeo fuente en el disco del VPS: son de 300 MB a
    1,1 GB por ponente y con 4-8 ponentes el disco se llena. Recortados pesan
    ~0,8 MB cada uno (73 ganchos de Mario = 58 MB en vez de 303 MB) y el
    original se queda solo en Drive, que es de donde vino.
    """
    return ponente_folder(slug) / "ganchos"


def hook_candidates_cache_path(slug: str) -> Path:
    """JSON de ganchos: escribible en work_root; se siembra desde assets si existe."""
    return _seed_cache_from_legacy(
        work_root() / "hook_candidates" / f"{slug}.json",
        ponente_folder(slug) / "hook_candidates.json",
    )


def paisaje_candidates_cache_path(pais: str = "es") -> Path:
    """JSON de paisajes: escribible en work_root; se siembra desde assets si existe.

    Uno por país. España conserva el nombre de siempre para no invalidar la
    biblioteca ya troceada (304 clips); los demás llevan sufijo.
    """
    nombre = (
        "paisaje_candidates.json" if pais == "es"
        else f"paisaje_candidates_{pais}.json"
    )
    return _seed_cache_from_legacy(
        work_root() / nombre,
        paisajes_folder(pais) / nombre,
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
# El audio va ENTERO: los ponentes traen audios de hasta ~2 min y el operador
# no quiere recortarlos. Antes esto estaba en 75s porque el `xfade` abría un
# decodificador 1080x1920 por clip y ffmpeg moría por OOM con 19 tramos; ahora
# el montaje va por tandas (`XFADE_MAX_INPUTS`) y la memoria no depende del
# número de tramos.
MAX_VIDEO_DURATION_S = 130.0
MIN_VIDEO_DURATION_S = 20.0

# Encode final: velocidad + peso TikTok (~15-40MB / 50s).
FFMPEG_PRESET = "veryfast"
FFMPEG_CRF = 23
# Techo de bitrate del vídeo final. CRF solo fija CALIDAD, no tamaño: con los
# estilos de grano fuerte el encoder gastaba ~90 Mbps intentando conservar
# ruido aleatorio y salían MP4 de 800 MB para 74s (inservibles para subir a
# TikTok desde el móvil, y llenaron el disco del VPS). TikTok recomienda
# ~10 Mbps para 1080p, así que este techo no toca los estilos normales
# (rondan 3-5 Mbps).
FFMPEG_MAXRATE = "8M"
FFMPEG_BUFSIZE = "16M"
FFMPEG_AUDIO_BITRATE = "128k"
# Pre-extract de clips individuales (fase 1 del renderer, anti-OOM).
# Cuántos clips entran en UNA pasada de `xfade`. Por encima, el montaje se
# hace por tandas y luego se unen las tandas: ffmpeg abre un decodificador
# 1080x1920 por entrada y con 19 se quedó sin memoria en el VPS de 8 GB.
XFADE_MAX_INPUTS = 7

FFMPEG_CLIP_PRESET = "ultrafast"
FFMPEG_CLIP_CRF = 18

HOOK_DUR = 3.0
# Cuántos tramos de paisaje se PIDEN. Ojo: subirlo NO alarga los planos.
# Medido contra la biblioteca real, subiéndolo de 4,0 a 4,6 el plano medio se
# quedó igual (2,6s → 2,8s en un vídeo de 60s). El motivo es que el asignador
# tiene que reunir clips hasta que la SUMA de lo aprovechable cubra el hueco,
# y como cada clip solo aporta `duración - CLIP_TRANSITION_PAD_S` (≈2,6s de
# los 3,9s que dura un plano típico), acaba usando cada clip A TOPE.
#
# O sea: la duración de cada paisaje ya está al máximo que da el material.
# Para planos más largos hace falta metraje con planos más largos, no tocar
# este número.
PAISAJE_CLIP_TARGET_S = 4.0
# A partir de aquí el reparto de paisajes prioriza planos largos. No es un
# tope duro: es el punto donde importa más no reventar la memoria del xfade
# (un input de vídeo por clip) que respetar el sorteo aleatorio.
MAX_PAISAJE_CLIPS = 34

# Umbral de detección de cara en primer plano (altura del bounding box /
# altura del frame). Igual que el prototipo validado.
FACE_HEIGHT_FRAC_THRESHOLD = 0.22
FACE_SAMPLE_STEP_S = 1.0

# Paisajes: saltar intro/outro del vídeo fuente (CTAs, mapas, etc.)
PAISAJES_SKIP_HEAD_S = 60.0
PAISAJES_SKIP_TAIL_S = 60.0

# El paso del gancho al b-roll ya no tiene transición propia: usa la misma
# que entre paisajes (ver `renderer.build_transitions`). Se conserva la
# constante porque hay jobs viejos en cola que la referencian.
TRANSITION_HOOK = ("fadeblack", 0.9)
# 0,9s se veía brusco, pero cada décima que dura el fundido es una décima
# MENOS de paisaje limpio (el fundido solapa los dos planos). Con 1,15s se
# perdían 0,3s de cada paisaje, que ya son cortos. 1,05 es el punto medio.
TRANSITION_LANDSCAPE = ("fadeblack", 1.05)

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
PAISAJE_CLIP_DUR_JITTER_RANGE = (3.2, 5.0)

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
# Estilo H: el texto va abajo DENTRO del cuadrado, no en el borde del vídeo.
# El cuadrado (940px centrado en 1920) acaba en y=1430; con este margen desde
# abajo la última línea cae justo dentro.
HIGHLIGHT_MARGIN_V = 600

# Dónde cae el recorte cuadrado dentro del alto disponible: 0.5 = centrado
# (lo que había), 0.0 = pegado arriba. El gancho no tiene holgura vertical
# —la fuente 16:9 se escala para cubrir 1080x1920 y encaja EXACTA de alto—,
# así que la cabeza del ponente queda a ~70px del borde superior y un
# recorte centrado (empezaba en y=420) la cortaba por los ojos.
SQUARE_CROP_Y_FRAC = 0.08

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
