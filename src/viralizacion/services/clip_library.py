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


def clips_folder() -> Path:
    """Carpeta de la biblioteca. Hermana de `paisajes/` en los assets."""
    override = os.getenv("VIRALIZACION_CLIPS_PATH")
    if override:
        return Path(override)
    return config.assets_root_path() / "paisajes_clips"


@lru_cache(maxsize=1)
def _load_manifest() -> tuple[dict, ...]:
    path = clips_folder() / MANIFEST_NAME
    if not path.is_file():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    return tuple(data.get("clips", []))


def is_available() -> bool:
    """True si la biblioteca existe y tiene clips utilizables."""
    return len(_load_manifest()) > 0


def all_clips() -> list[dict]:
    return [dict(c) for c in _load_manifest()]


def clip_count() -> int:
    return len(_load_manifest())


def clip_path(entry: dict) -> Path:
    return clips_folder() / entry["file"]


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
