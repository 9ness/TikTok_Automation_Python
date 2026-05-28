"""Endpoint `POST /api/v1/tiktok-shop/watermark-remover/enqueue`.

Encola un job de quitar marca de agua. El procesado real corre en el
worker de la cola (JobMode.TIKTOK_SHOP_WATERMARK), así que el user puede
cerrar la web y volver más tarde para descargar el resultado.

Por cada vídeo subido se crea un Job independiente. La cola los procesa
en orden. El resultado final se copia a:
  <user>/products/<slug>/videos/sin_marca/<N>_clean.mp4
donde N es el siguiente número disponible en esa carpeta.

Coste: $0 (delogo) o ~$0.015-0.04 (ProPainter Replicate, magic eraser).
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from src.api.dependencies import (
    get_current_user, get_product_repo, get_queue, get_user_repo,
)
from src.api.exceptions import (
    ProductNotFoundError, UserNotFoundError, ValidationError,
)
from src.api.temp_storage import upload_subdir
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus
from src.tiktok_shop.repos import ProductRepo, UserRepo


router = APIRouter(
    prefix="/api/v1/tiktok-shop/watermark-remover",
    tags=["tiktok-shop · sin marca"],
    dependencies=[Depends(get_current_user)],
)


_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_MAX_VIDEO_BYTES = 200 * 1024 * 1024
_WATERMARK_TYPES = {"veo_flow", "gemini_chat", "auto"}
_QUALITY_VALUES = {"fast", "magic"}


class WatermarkRemoverEnqueueResponse(BaseModel):
    """Confirmación de encolado. Para ver el estado/descargar el resultado
    el frontend usa la API de la cola (`/api/v1/queue/{job_id}`)."""
    job_id: str
    title: str
    position_in_queue: int
    watermark_type: str
    quality: str


def _position(queue: JobQueue, job_id: str) -> int:
    pending_or_running = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    for i, j in enumerate(pending_or_running):
        if j.id == job_id:
            return i
    return 0


@router.post("/enqueue", response_model=WatermarkRemoverEnqueueResponse)
async def enqueue_watermark_removal(
    file: Annotated[UploadFile, File(description="Vídeo .mp4/.mov/.mkv/.webm")],
    user_repo: Annotated[UserRepo, Depends(get_user_repo)],
    product_repo: Annotated[ProductRepo, Depends(get_product_repo)],
    queue: Annotated[JobQueue, Depends(get_queue)],
    user_id: Annotated[str, Form(description="Username TikTok destino")],
    product_id: Annotated[str, Form(description="Product ID destino")],
    watermark_type: Annotated[
        Literal["veo_flow", "gemini_chat", "auto"],
        Form(description="Tipo de marca de agua"),
    ] = "auto",
    quality: Annotated[
        Literal["fast", "magic"],
        Form(description="fast=delogo gratis · magic=ProPainter ~$0.015/clip"),
    ] = "magic",
) -> WatermarkRemoverEnqueueResponse:
    """Encola un job de quitar marca de agua. El procesado lo hace el worker
    de la cola — devuelve job_id para que el cliente lo tracke en /queue."""
    # ---------- Validación ----------
    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if filename.endswith(e)), "")
    if not ext:
        raise ValidationError(
            f"Formato no soportado: '{file.filename}'. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
        )
    if watermark_type not in _WATERMARK_TYPES:
        raise ValidationError(f"watermark_type inválido: '{watermark_type}'")
    if quality not in _QUALITY_VALUES:
        raise ValidationError(f"quality inválido: '{quality}'")

    contents = await file.read()
    if not contents:
        raise ValidationError("Archivo vacío.")
    if len(contents) > _MAX_VIDEO_BYTES:
        raise ValidationError(
            f"El vídeo pesa {len(contents) / 1024 / 1024:.1f} MB, máximo "
            f"{_MAX_VIDEO_BYTES / 1024 / 1024:.0f} MB.",
        )

    # ---------- Validar user + product existen ----------
    user = user_repo.get(user_id)
    if user is None:
        raise UserNotFoundError(
            f"Usuario '{user_id}' no existe", details={"user_id": user_id},
        )
    product = product_repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no existe",
            details={"product_id": product_id},
        )

    # ---------- Guardar input en temp ----------
    upload_dir = upload_subdir("watermark_remover")
    token = uuid.uuid4().hex[:10]
    safe_base = Path(file.filename or "video").stem.replace(" ", "_")[:60]
    in_path = upload_dir / f"in_{token}_{safe_base}{ext}"
    in_path.write_bytes(contents)

    # ---------- Encolar ----------
    title = f"{file.filename or 'video'} → @{user.username.lstrip('@')} / {product.name}"
    params = {
        "input_path": str(in_path),
        "user_id": user_id,
        "product_id": product_id,
        "watermark_type": watermark_type,
        "quality": quality,
        "source_filename": file.filename or "video",
        "video_duration_s": 10.0,  # estimación default — el runner usa esto solo para cost estimation si gpu_seconds=None
    }
    job = queue.enqueue(JobMode.TIKTOK_SHOP_WATERMARK, title=title, params=params)

    return WatermarkRemoverEnqueueResponse(
        job_id=job.id,
        title=title,
        position_in_queue=_position(queue, job.id),
        watermark_type=watermark_type,
        quality=quality,
    )
