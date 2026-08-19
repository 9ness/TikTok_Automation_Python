"""Biblioteca de clips de paisaje — un fichero por PLANO real del original.

Por qué existe (bug que resuelve): antes los tramos de paisaje se sacaban del
vídeo fuente de 61 min cortando por tiempo fijo cada 4,5s. Como los cortes no
coincidían con los cambios de plano, dos tramos consecutivos podían ser el
MISMO sitio (misma fachada, misma plaza) — se veía la transición pero el lugar
no cambiaba. Además cualquier tramo podía caer sobre un rótulo sobreimpreso.

Ahora cada clip:
- Es UN SOLO plano del original (detectado por cambio de escena), así que
  nunca cambia de lugar a mitad.
- Está revisado: sin texto sobreimpreso, sin caras en primer plano, sin
  fotogramas oscuros o borrosos.
- Ya viene en 1080x1920, así que el render no reabre el fuente de 2,5 GB.

De cada clip se saca una VENTANA ALEATORIA (duración y desplazamiento) en cada
generación: el mismo clip nunca se usa con el mismo encuadre temporal, lo que
suma variedad y dificulta el fingerprinting.
"""

from __future__ import annotations

import json
import os
import random
from functools import lru_cache
from pathlib import Path

from src.viralizacion import config

MANIFEST_NAME = "clips_manifest.json"

# Clips VETADOS por país: material que NO puede volver al banco ni aunque se
# regenere el manifiesto (`viralizacion_trocear_paisajes.py`). Es una lista
# negra en código, no solo un fichero movido de carpeta, porque el motivo no
# es estético: los clips 221 y 222 de España son un encierro/capea con toros
# y costaron el BANEO de una cuenta — TikTok lo trata como maltrato animal.
CLIPS_VETADOS: dict[str, set[int]] = {
    "es": {221, 222},
}


def clips_folder(pais: str = "es") -> Path:
    """Carpeta de la biblioteca, UNA POR PAÍS.

    España conserva `paisajes_clips/` tal cual para no invalidar los 304 clips
    ya revisados; los demás cuelgan con sufijo (`paisajes_clips_us/`). Sin
    esto, un vídeo de Billy Graham saldría con b-roll de España.
    """
    override = os.getenv("VIRALIZACION_CLIPS_PATH")
    if override and pais == "es":
        return Path(override)
    sufijo = "" if pais == "es" else f"_{pais}"
    return config.assets_root_path() / f"paisajes_clips{sufijo}"


@lru_cache(maxsize=4)
def _load_manifest_cached(path_str: str, mtime: float) -> tuple[dict, ...]:
    try:
        data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    return tuple(data.get("clips", []))


def _load_manifest(pais: str = "es") -> tuple[dict, ...]:
    """Manifiesto cacheado POR MTIME.

    Si se retiran clips del banco (p. ej. al detectar un rótulo que se había
    colado), el proceso de la API tiene que verlo sin reiniciar el container.
    Cachear a secas dejaba sirviendo la lista vieja.
    """
    path = clips_folder(pais) / MANIFEST_NAME
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ()
    clips = _load_manifest_cached(str(path), mtime)
    vetados = CLIPS_VETADOS.get(pais)
    if vetados:
        clips = tuple(c for c in clips if c.get("index") not in vetados)
    return clips


def is_available(pais: str = "es") -> bool:
    """True si la biblioteca existe y tiene clips utilizables."""
    return len(_load_manifest(pais)) > 0


def all_clips(pais: str = "es") -> list[dict]:
    return [dict(c) for c in _load_manifest(pais)]


def clip_count(pais: str = "es") -> int:
    return len(_load_manifest(pais))


def clip_path(entry: dict, pais: str = "es") -> Path:
    return clips_folder(pais) / entry["file"]


def random_window(clip: dict) -> tuple[float, float]:
    """(start, dur) de una ventana aleatoria dentro del clip.

    La duración se sortea dentro del rango de jitter, pero acotada a lo que da
    el clip: el material tiene planos cortos (mediana ~4,5s) y forzar 5s
    dejaría fuera la mayoría. Si el clip no llega al mínimo se usa entero.
    """
    total = float(clip.get("dur") or 0.0)
    lo, hi = config.PAISAJE_CLIP_DUR_JITTER_RANGE
    if total <= lo:
        return 0.0, max(0.0, total)
    dur = random.uniform(lo, min(hi, total))
    start = random.uniform(0.0, max(0.0, total - dur))
    return round(start, 3), round(dur, 3)
