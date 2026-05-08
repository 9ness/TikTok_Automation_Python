"""Detección de fotos "pobres" para sugerir Nano Banana 2.

Lógica combinada:
  - Flag `needs_nano_banana_regeneration` que devuelve Gemini analyzer
    (basado en watermarks, artifacts, calidad visual).
  - Check local con PIL: si CUALQUIER lado < `LOW_RESOLUTION_THRESHOLD_PX`
    (1024 px por defecto) → flag = True.

Resultado: `needs = gemini_flag OR pil_low_resolution`.
"""

from __future__ import annotations

import os
from typing import Iterable

from src.tiktok_shop.config import LOW_RESOLUTION_THRESHOLD_PX


def is_low_resolution(photo_path: str, threshold_px: int = LOW_RESOLUTION_THRESHOLD_PX) -> bool:
    """True si CUALQUIER lado de la imagen es menor al umbral.

    Si el archivo no se puede abrir o no existe, devuelve False (asume OK
    para no bloquear el flow).
    """
    if not photo_path or not os.path.exists(photo_path):
        return False
    try:
        from PIL import Image
        with Image.open(photo_path) as img:
            w, h = img.size
        return min(w, h) < threshold_px
    except Exception:
        return False


def any_photo_low_resolution(photo_paths: Iterable[str], threshold_px: int = LOW_RESOLUTION_THRESHOLD_PX) -> bool:
    return any(is_low_resolution(p, threshold_px=threshold_px) for p in photo_paths)


def needs_nano_banana_regeneration(
    *,
    gemini_flag: bool,
    photo_paths: Iterable[str],
    threshold_px: int = LOW_RESOLUTION_THRESHOLD_PX,
) -> bool:
    """Combinación canónica: Gemini analyzer flag OR alguna foto < umbral."""
    return bool(gemini_flag) or any_photo_low_resolution(photo_paths, threshold_px=threshold_px)
