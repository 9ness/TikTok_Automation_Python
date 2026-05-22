"""Endpoint `POST /api/v1/tiktok-shop/replicate-viral`.

Análisis síncrono de un vídeo viral subido por el usuario para extraer una
config preset reutilizable. NO encola jobs — devuelve la config y deja al
cliente decidir si la guarda como preset (vía PUT /presets/...).

Coste típico (Gemini 2.5 Flash): ~$0.004 / vídeo. Pro ~5x más.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.api.dependencies import get_current_user, get_product_repo, get_user_repo
from src.api.exceptions import (
    APIError,
    InvalidEnqueueRequestError,
    ProductNotFoundError,
    UserNotFoundError,
    ValidationError,
)
from src.api.schemas.shop_preset import ReplicateViralResponse
from src.api.temp_storage import upload_subdir
from src.tiktok_shop.repos import ProductRepo, UserRepo


router = APIRouter(
    prefix="/api/v1/tiktok-shop",
    tags=["tiktok-shop · replicar viral"],
    dependencies=[Depends(get_current_user)],
)


_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500 MB

_VALID_KINDS = {"auto_video", "veo3", "nano_banana"}


async def _accept_video_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if filename.endswith(e)), "")
    if not ext:
        raise ValidationError(
            f"Formato no soportado: '{file.filename}'. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            details={"filename": file.filename},
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
    return contents, ext


@router.post("/replicate-viral", response_model=ReplicateViralResponse)
async def replicate_viral(
    user_repo: Annotated[UserRepo, Depends(get_user_repo)],
    product_repo: Annotated[ProductRepo, Depends(get_product_repo)],
    file: Annotated[UploadFile, File(...)],
    user_id: Annotated[str, Form(..., min_length=1)],
    product_id: Annotated[str, Form(..., min_length=1)],
    target_kind: Annotated[
        Literal["auto_video", "veo3", "nano_banana"], Form(...),
    ] = "auto_video",
    same_product: Annotated[bool, Form()] = True,
    gemini_model: Annotated[str, Form()] = "gemini-2.5-flash",
) -> ReplicateViralResponse:
    if target_kind not in _VALID_KINDS:
        raise ValidationError(
            f"target_kind inválido: '{target_kind}'.",
            details={"target_kind": target_kind},
        )

    user = user_repo.get(user_id)
    if user is None:
        raise UserNotFoundError(
            f"Usuario '{user_id}' no encontrado.",
            details={"user_id": user_id},
        )
    product = product_repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    if product_id not in user.assigned_products:
        raise InvalidEnqueueRequestError(
            f"El producto no está asignado al usuario '{user.username}'.",
            details={"username": user.username, "product_id": product_id},
        )

    contents, ext = await _accept_video_upload(file)
    folder = upload_subdir("viral_replica")
    dest = folder / f"viral_in_{int(time.time())}{ext}"
    try:
        dest.write_bytes(contents)
    except OSError as e:
        raise APIError(
            f"No se pudo escribir el vídeo en disco: {e}",
            details={"path": str(dest)},
        )

    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.pipeline.viral_analyzer import analyze_viral_video

    # Cost tracking: registra el coste real de los Gemini calls del análisis.
    import uuid as _uuid
    start_job(
        job_id=f"viral_{_uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="viral_replica",
        title=f"Viral replica: {product.slug}",
        product_id=product_id,
        user=user.username,
    )
    try:
        result = analyze_viral_video(
            str(dest),
            target_kind=target_kind,
            same_product=same_product,
            gemini_model=gemini_model,
            product=product,
        )
    except RuntimeError as e:
        try:
            finalize_and_persist()
        except Exception:
            pass
        raise APIError(f"Análisis viral falló: {e}", details={"video": file.filename})
    finally:
        # No conservamos el vídeo del usuario — análisis síncrono, sin
        # persistencia. Si el endpoint vuelve a fallar el cleanup también
        # se hace ahí. Si el user quiere reintentar, sube otra vez.
        try:
            Path(dest).unlink(missing_ok=True)
        except OSError:
            pass
        try:
            finalize_and_persist()
        except Exception:
            pass

    return ReplicateViralResponse(**result)
