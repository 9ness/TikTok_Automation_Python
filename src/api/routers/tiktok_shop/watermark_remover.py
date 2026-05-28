"""Endpoint `POST /api/v1/tiktok-shop/watermark-remover/process`.

Quita marca de agua de un vídeo Veo 3 / Gemini vía ffmpeg `delogo`.

Síncrono — el procesado es rápido (~3-5s para vídeos de 10s). Devuelve un
token con el path relativo del output dentro de `temp_root` que el cliente
usa para descargar vía `GET /watermark-remover/file/{token}`.

Coste: $0 (ffmpeg local).

Para multi-upload el frontend llama el endpoint N veces (en paralelo o
serie según prefiera). Para uso "encolado pero sin delay" basta con esto
— cada llamada corre en threadpool de FastAPI y no compite con la cola
principal.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import get_current_user
from src.api.exceptions import ValidationError
from src.api.temp_storage import resolve_relative, to_relative, upload_subdir
from src.tiktok_shop.pipeline.watermark_remover import (
    WatermarkRemoverError,
    remove_watermark,
)


router = APIRouter(
    prefix="/api/v1/tiktok-shop/watermark-remover",
    tags=["tiktok-shop · sin marca"],
    dependencies=[Depends(get_current_user)],
)


_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_MAX_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB — vídeos Veo de 10s son <10MB
_WATERMARK_TYPES = {"veo_flow", "gemini_chat", "auto"}


class WatermarkRemoverResponse(BaseModel):
    """Resultado del procesado.

    `output_path` es relativo a `temp_root` — el cliente lo descarga vía
    `GET /watermark-remover/file?path=<output_path>`.
    """
    output_path: str
    output_filename: str
    output_size_bytes: int
    processing_seconds: float
    watermark_type: str


@router.post("/process", response_model=WatermarkRemoverResponse)
async def process_video(
    file: Annotated[UploadFile, File(description="Vídeo .mp4/.mov/.mkv/.webm")],
    watermark_type: Annotated[
        Literal["veo_flow", "gemini_chat", "auto"],
        Form(description="Tipo de marca de agua a eliminar"),
    ] = "auto",
) -> WatermarkRemoverResponse:
    """Procesa un vídeo y devuelve el path al output sin marca de agua."""
    # ---------- Validación de input ----------
    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if filename.endswith(e)), "")
    if not ext:
        raise ValidationError(
            f"Formato no soportado: '{file.filename}'. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            details={"filename": file.filename},
        )
    if watermark_type not in _WATERMARK_TYPES:
        raise ValidationError(
            f"watermark_type inválido: '{watermark_type}'. "
            f"Opciones: {', '.join(sorted(_WATERMARK_TYPES))}.",
        )

    contents = await file.read()
    if not contents:
        raise ValidationError("Archivo vacío.", details={"filename": file.filename})
    if len(contents) > _MAX_VIDEO_BYTES:
        raise ValidationError(
            f"El vídeo pesa {len(contents) / 1024 / 1024:.1f} MB, máximo "
            f"{_MAX_VIDEO_BYTES / 1024 / 1024:.0f} MB.",
            details={"size_bytes": len(contents)},
        )

    # ---------- Guardar input en temp ----------
    upload_dir = upload_subdir("watermark_remover")
    token = uuid.uuid4().hex[:10]
    safe_base = Path(file.filename or "video").stem.replace(" ", "_")[:60]
    in_path = upload_dir / f"in_{token}_{safe_base}{ext}"
    in_path.write_bytes(contents)

    out_path = upload_dir / f"out_{token}_{safe_base}.mp4"

    # ---------- Procesar ----------
    started = time.time()
    try:
        remove_watermark(
            str(in_path), str(out_path),
            watermark_type=watermark_type,
        )
    except WatermarkRemoverError as e:
        # Limpia input para no acumular basura
        try:
            in_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ValidationError(
            f"Error procesando el vídeo: {e}",
            details={"watermark_type": watermark_type},
        )
    finally:
        # Borra input siempre (ya no lo necesitamos)
        try:
            in_path.unlink(missing_ok=True)
        except OSError:
            pass

    elapsed = round(time.time() - started, 2)
    output_size = out_path.stat().st_size

    return WatermarkRemoverResponse(
        output_path=to_relative(out_path),
        output_filename=out_path.name,
        output_size_bytes=output_size,
        processing_seconds=elapsed,
        watermark_type=watermark_type,
    )


@router.get("/file")
def download_processed_file(
    path: str,
) -> FileResponse:
    """Descarga el vídeo procesado. `path` debe ser relativo a `temp_root`
    y dentro de `api_uploads/watermark_remover/` (validado anti-traversal)."""
    try:
        resolved = resolve_relative(path)
    except ValueError as e:
        raise ValidationError(f"Path inválido: {e}")

    # Validar que el path está dentro del subdir esperado
    expected_parent = upload_subdir("watermark_remover").resolve()
    if expected_parent not in resolved.parents:
        raise ValidationError("Path fuera de watermark_remover/")

    if not resolved.exists() or not resolved.is_file():
        raise ValidationError(
            f"Archivo no existe: {path}",
            details={"path": path},
        )

    return FileResponse(
        path=str(resolved),
        media_type="video/mp4",
        filename=resolved.name,
    )
