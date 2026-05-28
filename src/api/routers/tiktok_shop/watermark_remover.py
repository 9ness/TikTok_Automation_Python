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

import os
import shutil
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import (
    get_current_user, get_product_repo, get_user_repo,
)
from src.api.exceptions import (
    ProductNotFoundError, UserNotFoundError, ValidationError,
)
from src.api.temp_storage import resolve_relative, to_relative, upload_subdir
from src.tiktok_shop.config import user_videos_folder
from src.tiktok_shop.pipeline.watermark_remover import (
    WatermarkRemoverError,
    remove_watermark,
    remove_watermark_magic,
)
from src.tiktok_shop.repos import ProductRepo, UserRepo


router = APIRouter(
    prefix="/api/v1/tiktok-shop/watermark-remover",
    tags=["tiktok-shop · sin marca"],
    dependencies=[Depends(get_current_user)],
)


_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_MAX_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB — vídeos Veo de 10s son <10MB
_WATERMARK_TYPES = {"veo_flow", "gemini_chat", "auto"}
_QUALITY_VALUES = {"fast", "magic"}


class WatermarkRemoverResponse(BaseModel):
    """Resultado del procesado.

    Si se pasó `user_id`+`product_id`, el vídeo se copia a Drive en
    `<user>/products/<slug>/videos/sin_marca/<filename>` y `drive_path`
    contiene el path absoluto donde se guardó. Si no, sigue disponible
    en `output_path` (relativo a `temp_root`) para descarga via
    `GET /watermark-remover/file?path=<output_path>`.
    """
    output_path: str
    output_filename: str
    output_size_bytes: int
    processing_seconds: float
    watermark_type: str
    quality: str = "fast"
    cost_usd: float = 0.0            # 0 para fast, ~0.015 para magic
    drive_path: str | None = None    # path Drive si se guardó allí
    drive_subdir: str | None = None  # relativo a TIKTOK_SHOP root (display)


@router.post("/process", response_model=WatermarkRemoverResponse)
async def process_video(
    file: Annotated[UploadFile, File(description="Vídeo .mp4/.mov/.mkv/.webm")],
    user_repo: Annotated[UserRepo, Depends(get_user_repo)],
    product_repo: Annotated[ProductRepo, Depends(get_product_repo)],
    watermark_type: Annotated[
        Literal["veo_flow", "gemini_chat", "auto"],
        Form(description="Tipo de marca de agua a eliminar"),
    ] = "auto",
    quality: Annotated[
        Literal["fast", "magic"],
        Form(description="fast=delogo gratis (deja blur leve) · magic=ProPainter ~$0.015/clip (magic eraser real)"),
    ] = "magic",
    user_id: Annotated[
        str | None,
        Form(description="Username TikTok destino — si se pasa con product_id, guarda en Drive"),
    ] = None,
    product_id: Annotated[
        str | None,
        Form(description="Product ID destino — si se pasa con user_id, guarda en Drive"),
    ] = None,
) -> WatermarkRemoverResponse:
    """Procesa un vídeo. Si user_id+product_id están presentes lo guarda
    en `<user>/products/<slug>/videos/sin_marca/<filename>` en Drive."""
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

    # ---------- Resolver Drive destination si user+product ----------
    drive_subdir: Path | None = None
    if user_id and product_id:
        user = user_repo.get(user_id)
        if user is None:
            raise UserNotFoundError(
                f"Usuario '{user_id}' no existe",
                details={"user_id": user_id},
            )
        product = product_repo.get(product_id)
        if product is None:
            raise ProductNotFoundError(
                f"Producto '{product_id}' no existe",
                details={"product_id": product_id},
            )
        videos_folder = user_videos_folder(user.username, product.slug)
        drive_subdir = Path(videos_folder) / "sin_marca"

    # ---------- Guardar input en temp ----------
    upload_dir = upload_subdir("watermark_remover")
    token = uuid.uuid4().hex[:10]
    safe_base = Path(file.filename or "video").stem.replace(" ", "_")[:60]
    in_path = upload_dir / f"in_{token}_{safe_base}{ext}"
    in_path.write_bytes(contents)

    out_path = upload_dir / f"out_{token}_{safe_base}.mp4"

    # ---------- Procesar ----------
    started = time.time()
    cost_usd = 0.0
    gpu_seconds: float | None = None
    try:
        if quality == "magic":
            # Magic Eraser via ProPainter (Replicate) — cobra ~$0.015/10s
            _, gpu_seconds = remove_watermark_magic(
                str(in_path), str(out_path),
                watermark_type=watermark_type,
            )
            # Cost tracking
            try:
                from src.cost_tracking import record_replicate_propainter
                from src.tiktok_shop.pipeline.watermark_remover import _ffprobe_dimensions
                # Duración real del vídeo (para estimación si gpu_seconds=None)
                # Sin embargo no exponemos ffprobe_duration. Usamos size hint.
                vid_dur = max(5.0, len(contents) / (1024 * 1024) * 1.0)  # rough
                cost_usd = record_replicate_propainter(
                    gpu_seconds=gpu_seconds,
                    video_duration_s=vid_dur,
                    detail=f"{watermark_type} · {file.filename}",
                )
            except Exception as e:
                print(f"[watermark_remover] cost tracking falló: {e}")
        else:
            # Fast: delogo gratis (deja blur leve)
            remove_watermark(
                str(in_path), str(out_path),
                watermark_type=watermark_type,
            )
            cost_usd = 0.0
    except WatermarkRemoverError as e:
        try:
            in_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ValidationError(
            f"Error procesando el vídeo: {e}",
            details={"watermark_type": watermark_type, "quality": quality},
        )
    finally:
        try:
            in_path.unlink(missing_ok=True)
        except OSError:
            pass

    elapsed = round(time.time() - started, 2)
    output_size = out_path.stat().st_size

    # ---------- Copiar a Drive si procede ----------
    drive_path_str: str | None = None
    drive_subdir_display: str | None = None
    if drive_subdir is not None:
        try:
            drive_subdir.mkdir(parents=True, exist_ok=True)
            # Nombre destino: <YYYY-MM-DD>_<safe_base>_v<n>.mp4 para
            # evitar colisiones si subes el mismo vídeo varias veces.
            today = date.today().isoformat()
            n = 1
            while True:
                candidate = drive_subdir / f"{today}_{safe_base}_v{n}.mp4"
                if not candidate.exists():
                    break
                n += 1
            shutil.copy2(out_path, candidate)
            drive_path_str = str(candidate)
            # Para display: relativo a la home del user (mucho más legible)
            try:
                drive_subdir_display = str(
                    candidate.relative_to(Path(user_videos_folder(user.username, "")).parent.parent)
                )
            except ValueError:
                drive_subdir_display = str(candidate)
            # Si guardamos en Drive ya no necesitamos el temp file
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass
        except Exception as e:
            # No abortamos — devolvemos el temp como fallback
            print(f"[watermark_remover] copia a Drive falló: {e}")

    return WatermarkRemoverResponse(
        output_path=to_relative(out_path) if out_path.exists() else "",
        output_filename=Path(drive_path_str).name if drive_path_str else out_path.name,
        output_size_bytes=output_size,
        processing_seconds=elapsed,
        watermark_type=watermark_type,
        quality=quality,
        cost_usd=round(cost_usd, 4),
        drive_path=drive_path_str,
        drive_subdir=drive_subdir_display,
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
