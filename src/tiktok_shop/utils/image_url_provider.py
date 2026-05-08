"""Conversión de fotos locales a referencias para Atlas Cloud.

Las fotos viven en el filesystem local sincronizado con Drive (Drive Desktop
o rclone mount). Para los 3 tiers usamos `data:image/...;base64,<...>` inline:

  - Pro acepta base64 oficialmente (per doc).
  - Standard/Advanced lo aceptan también para 1-4 fotos por vídeo (probado E2E).

Esta unificación evita configurar R2/S3 y simplifica el flow.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterable

_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def get_atlas_image_ref(local_path: str | Path, tier: str | None = None) -> str:
    """Lee la foto y devuelve un data URI base64 listo para Atlas.

    El parámetro `tier` se mantiene por compat con callers existentes pero NO
    cambia el comportamiento — todos los tiers usan base64.
    """
    _ = tier  # compat-only, no afecta a la salida
    p = Path(local_path)
    if not p.exists():
        raise FileNotFoundError(f"Photo not found: {p}")

    mime = _MIME_BY_EXT.get(p.suffix.lower(), "image/jpeg")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def get_atlas_image_refs(local_paths: Iterable[str | Path], tier: str | None = None) -> list[str]:
    return [get_atlas_image_ref(p, tier=tier) for p in local_paths]


# Mantenido por compatibilidad con el smoke test antiguo. La salida es
# idéntica a `get_atlas_image_ref` (los 3 tiers usan base64).
def to_base64_data_uri(local_path: str | Path) -> str:
    return get_atlas_image_ref(local_path)
