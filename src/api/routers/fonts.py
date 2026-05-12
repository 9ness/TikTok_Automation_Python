"""Endpoints universales de fuentes — usados por TODOS los selectores
de fuente del frontend (Presidentes, Subs sobre Vídeo, Quitar Copy).

4 endpoints:
- GET /api/v1/fonts                 — lista bundled + system
- POST /api/v1/fonts/upload         — sube un TTF/OTF a `assets/fonts/`
- DELETE /api/v1/fonts/{filename}   — quita una fuente bundled
- GET /api/v1/fonts/file/{filename} — sirve el TTF/OTF como blob (para @font-face)
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, UnauthorizedError, ValidationError
from src.fonts_registry import (
    _bundled_fonts_dir,
    _safe_filename,
    add_uploaded_font,
    list_fonts,
    remove_bundled_font,
)


router = APIRouter(
    prefix="/api/v1/fonts",
    tags=["fonts"],
    dependencies=[Depends(get_current_user)],
)


# Router separado SIN auth global porque `@font-face { src: url(...) }` no
# manda headers personalizables — autenticamos vía query `?api_key=` como
# el endpoint de frame.
file_router = APIRouter(
    prefix="/api/v1/fonts",
    tags=["fonts"],
)


def _auth_or_raise(
    settings: APISettings, header: str | None, query: str | None
) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


@router.get("")
def get_fonts() -> dict:
    """Devuelve todas las fuentes disponibles para los selectores."""
    return {"items": list_fonts()}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_font(
    file: Annotated[UploadFile, File(...)],
) -> dict:
    """Sube un TTF/OTF a `assets/fonts/`. Aparece inmediatamente en
    `GET /fonts` y por tanto en los selectores."""
    content = await file.read()
    try:
        entry = add_uploaded_font(file.filename or "font.ttf", content)
    except ValueError as e:
        raise ValidationError(str(e), details={"filename": file.filename})
    except Exception as e:
        raise APIError(
            f"No se pudo guardar la fuente: {e}",
            details={"filename": file.filename},
        )
    return entry


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_font(filename: str) -> None:
    """Quita una fuente bundled (no afecta a fuentes del sistema)."""
    try:
        removed = remove_bundled_font(filename)
    except ValueError as e:
        raise ValidationError(str(e), details={"filename": filename})
    if not removed:
        raise ValidationError(
            f"No existe ninguna fuente bundled con filename '{filename}'.",
            details={"filename": filename},
        )


@file_router.get("/file/{filename}")
def get_font_file(
    filename: str,
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    """Sirve un TTF/OTF bundled como blob para que el frontend pueda
    cargarlo con `@font-face` en previews WYSIWYG. Auth vía query
    `?api_key=` (los font requests del navegador no admiten headers
    custom). Solo sirve archivos dentro de `assets/fonts/`."""
    _auth_or_raise(settings, x_api_key, api_key)
    try:
        safe = _safe_filename(filename)
    except ValueError as e:
        raise ValidationError(str(e), details={"filename": filename})
    bdir = Path(_bundled_fonts_dir())
    target = bdir / safe
    if not target.is_file() or target.suffix.lower() not in {".ttf", ".otf"}:
        raise ValidationError(
            f"Fuente bundled no encontrada: '{filename}'.",
            details={"filename": filename},
        )
    media = "font/otf" if target.suffix.lower() == ".otf" else "font/ttf"
    return FileResponse(
        path=str(target),
        media_type=media,
        filename=target.name,
        headers={"Cache-Control": "public, max-age=86400"},
    )
