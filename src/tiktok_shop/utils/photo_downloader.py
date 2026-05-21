"""Descarga una imagen desde URL y la guarda como `ProductPhoto` source
del producto. Pensado para auto-añadir la `og:image` de TikTok Shop al
crear un producto desde URL — el user no tiene que subir manualmente.

Nunca lanza al frontend: si la descarga falla, devolvemos None y el
caller decide (típicamente: log warning y seguir, el producto ya está
creado, la foto se puede subir luego a mano).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.tiktok_shop.config import product_photos_source_folder
from src.tiktok_shop.models.product import ProductPhoto

logger = logging.getLogger("tiktok_shop.photo_downloader")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Tamaño max del descargado en bytes (~10 MB — suficiente para fotos
# de producto, evita que TikTok nos sirva un vídeo enorme por error).
_MAX_BYTES = 10 * 1024 * 1024

# Content-Types que aceptamos
_OK_CONTENT_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
}

# Map content-type → extensión (preferida a la que venga en la URL).
_CT_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def download_image_to_product(
    *,
    product_slug: str,
    image_url: str,
    photo_type: str = "packshot",
    origin: str = "tiktok_shop_url",
    timeout_s: int = 20,
) -> ProductPhoto | None:
    """Descarga `image_url` y la guarda en `photos_source/` del producto.

    Devuelve el `ProductPhoto` creado (no lo persiste en Redis — eso lo
    hace el caller añadiéndolo a `product.photos.source` y guardando).
    Devuelve `None` si la descarga falla.
    """
    if not image_url:
        return None

    try:
        resp = requests.get(
            image_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout_s,
            allow_redirects=True,
            stream=True,
        )
    except requests.exceptions.RequestException as e:
        logger.warning("[photo_downloader] GET falló %s: %s", image_url, e)
        return None

    if resp.status_code >= 400:
        logger.warning(
            "[photo_downloader] HTTP %s descargando %s", resp.status_code, image_url
        )
        return None

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if content_type and content_type not in _OK_CONTENT_TYPES:
        logger.warning(
            "[photo_downloader] Content-Type rechazado: %s url=%s",
            content_type, image_url,
        )
        return None

    # Streaming + cap de tamaño
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > _MAX_BYTES:
            logger.warning(
                "[photo_downloader] imagen >%dMB, cancelo url=%s",
                _MAX_BYTES // 1024 // 1024, image_url,
            )
            return None
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        return None

    # Decidir extensión: content-type primero, luego de la URL.
    ext = _CT_TO_EXT.get(content_type) or _guess_ext_from_url(image_url) or ".jpg"

    folder = product_photos_source_folder(product_slug)
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("[photo_downloader] mkdir falló %s: %s", folder, e)
        return None

    # Nombre: stamp + suffix corto para evitar colisiones.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    filename = f"tiktok_share_{stamp}_{suffix}{ext}"
    dest = Path(folder) / filename
    try:
        dest.write_bytes(data)
    except OSError as e:
        logger.warning("[photo_downloader] write falló %s: %s", dest, e)
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    return ProductPhoto(
        filename=filename,
        local_path=str(dest),
        type=photo_type,
        origin=origin,
        url_origin=image_url,
        added_at=now_iso,
    )


def _guess_ext_from_url(url: str) -> str | None:
    """Saca extensión de la URL (sin query string)."""
    try:
        path = urlparse(url).path
    except Exception:
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return ".jpg" if ext == ".jpeg" else ext
    return None
