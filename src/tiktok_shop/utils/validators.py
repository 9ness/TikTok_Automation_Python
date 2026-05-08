"""Validadores de inputs UI — formato de slug, URLs, fotos.

Estas funciones devuelven `(ok, error_message)` para que la UI pueda mostrar
mensajes específicos en lugar de un genérico "Error". Centralizadas aquí para
poder testearlas sin Streamlit.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes de validación
# ---------------------------------------------------------------------------
SLUG_PATTERN = re.compile(r"^[a-z0-9_]+$")
PHOTO_MIN_RESOLUTION_DEFAULT = 512   # px (cualquier lado >= 512)
PHOTO_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
SUPPORTED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
TIKTOK_SHOP_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(tiktok\.com|shop-\w+\.tiktok\.com)/.+",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------
def validate_slug(slug: str) -> tuple[bool, str]:
    """Slug solo `a-z`, `0-9`, `_`. Sin mayúsculas ni espacios ni símbolos."""
    if not slug:
        return False, "El slug no puede estar vacío."
    if " " in slug:
        return False, f"El slug no puede contener espacios: '{slug}'"
    if slug != slug.lower():
        return False, f"El slug debe estar todo en minúsculas: '{slug}'"
    if not SLUG_PATTERN.match(slug):
        return False, (
            f"Slug inválido: '{slug}'. Solo se permiten letras minúsculas, "
            "números y guion bajo (`_`)."
        )
    return True, ""


# ---------------------------------------------------------------------------
# Username TikTok
# ---------------------------------------------------------------------------
def validate_tiktok_username(username: str) -> tuple[bool, str]:
    """Username debe empezar con `@` y solo letras/números/`._-`."""
    if not username:
        return False, "El username no puede estar vacío."
    if not username.startswith("@"):
        return False, "El username debe empezar con `@`."
    if len(username) < 3:
        return False, "El username debe tener al menos 2 caracteres tras `@`."
    if len(username) > 25:
        return False, "El username no puede tener más de 24 caracteres tras `@`."
    handle = username[1:]
    if not re.match(r"^[a-zA-Z0-9._]+$", handle):
        return False, (
            f"Username inválido: '{username}'. Solo letras, números, "
            "puntos (`.`) y guion bajo (`_`) tras la `@`."
        )
    return True, ""


# ---------------------------------------------------------------------------
# URL TikTok Shop
# ---------------------------------------------------------------------------
def validate_tiktok_shop_url(url: str, *, required: bool = False) -> tuple[bool, str]:
    """URL del producto en TikTok Shop. Opcional por defecto."""
    if not url:
        if required:
            return False, "URL TikTok Shop obligatoria."
        return True, ""  # vacío OK si no es obligatoria
    if not TIKTOK_SHOP_URL_PATTERN.match(url):
        return False, (
            f"URL no parece de TikTok Shop: '{url}'. "
            "Formato esperado: `https://www.tiktok.com/...` o "
            "`https://shop-xx.tiktok.com/...`."
        )
    return True, ""


# ---------------------------------------------------------------------------
# Fotos (resolución + tamaño + formato)
# ---------------------------------------------------------------------------
def validate_photo_extension(filename: str) -> tuple[bool, str]:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_PHOTO_EXTS:
        return False, (
            f"Formato no soportado: '{ext or '(sin extensión)'}'. "
            f"Aceptados: {', '.join(sorted(SUPPORTED_PHOTO_EXTS))}."
        )
    return True, ""


def validate_photo_size(num_bytes: int, max_bytes: int = PHOTO_MAX_SIZE_BYTES) -> tuple[bool, str]:
    if num_bytes <= 0:
        return False, "El archivo está vacío."
    if num_bytes > max_bytes:
        return False, (
            f"La foto pesa {num_bytes / 1024 / 1024:.1f} MB, máximo "
            f"{max_bytes / 1024 / 1024:.0f} MB."
        )
    return True, ""


def validate_photo_resolution(
    photo_path: str | Path,
    *,
    min_px: int = PHOTO_MIN_RESOLUTION_DEFAULT,
) -> tuple[bool, str]:
    """Resolución mínima por lado (`min_px`). Por defecto 512px en cualquier lado."""
    if not os.path.exists(photo_path):
        return False, f"Archivo no encontrado: {photo_path}"
    try:
        from PIL import Image
        with Image.open(photo_path) as img:
            w, h = img.size
    except Exception as e:
        return False, f"No se pudo leer la imagen: {e}"
    if w < min_px or h < min_px:
        return False, (
            f"Resolución demasiado baja: {w}×{h} (mínimo {min_px}px por lado)."
        )
    return True, ""


def validate_photo_upload(
    filename: str,
    num_bytes: int,
    photo_path: str | Path | None = None,
    *,
    min_px: int = PHOTO_MIN_RESOLUTION_DEFAULT,
    max_bytes: int = PHOTO_MAX_SIZE_BYTES,
) -> tuple[bool, str]:
    """Validación combinada para subida de fotos en wizards.

    Si `photo_path` es None, no se valida resolución (útil cuando aún no se
    ha guardado el archivo en disco — solo se conoce filename + bytes).
    """
    ok, err = validate_photo_extension(filename)
    if not ok:
        return False, err
    ok, err = validate_photo_size(num_bytes, max_bytes=max_bytes)
    if not ok:
        return False, err
    if photo_path is not None:
        ok, err = validate_photo_resolution(photo_path, min_px=min_px)
        if not ok:
            return False, err
    return True, ""


# ---------------------------------------------------------------------------
# Required-field helper
# ---------------------------------------------------------------------------
def require_non_empty(value: str | None, field_label: str) -> tuple[bool, str]:
    if value is None or not str(value).strip():
        return False, f"Campo obligatorio: {field_label}."
    return True, ""
