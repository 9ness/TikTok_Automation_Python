"""Endpoints del nicho 🛡️ Quitar Copy.

1 endpoint:
- POST /enqueue (multipart con file + form params)
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import APIError, ValidationError
from src.api.schemas.creator_reward.copyright import (
    CleanModeValue,
    CopyrightEnqueueResponse,
)
from src.api.temp_storage import to_relative, upload_subdir
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/creator-reward/copyright",
    tags=["creator-reward · copyright"],
    dependencies=[Depends(get_current_user)],
)


_ALLOWED_VIDEO_EXTS = {".mp4", ".mov"}
_MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500 MB
_ALLOWED_HOOK_Y_PCT = (0.20, 0.45, 0.75)


def _position_in_queue(queue: JobQueue, job_id: str) -> int:
    pending_or_running = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    for i, j in enumerate(pending_or_running):
        if j.id == job_id:
            return i
    return 0


@router.post(
    "/enqueue",
    response_model=CopyrightEnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enqueue_copyright(
    queue: Annotated[JobQueue, Depends(get_queue)],
    file: Annotated[UploadFile, File(...)],
    clean_mode: Annotated[CleanModeValue, Form()] = "Subtítulos Virales",
    hook_y_pct: Annotated[float, Form()] = 0.20,
    hook_color: Annotated[str, Form()] = "#FDD002",
    upscale_1080p: Annotated[bool, Form()] = False,
    font_path: Annotated[str | None, Form()] = None,
) -> CopyrightEnqueueResponse:
    """Sube un MP4/MOV, lo guarda en `temp_work/api_uploads/copyright/`,
    y encola el job de limpieza."""
    if not any(abs(hook_y_pct - v) < 1e-6 for v in _ALLOWED_HOOK_Y_PCT):
        raise ValidationError(
            f"hook_y_pct debe ser uno de {_ALLOWED_HOOK_Y_PCT} (recibido: {hook_y_pct}).",
            details={"hook_y_pct": hook_y_pct, "allowed": list(_ALLOWED_HOOK_Y_PCT)},
        )
    filename = (file.filename or "").lower()
    ext = ""
    for candidate in _ALLOWED_VIDEO_EXTS:
        if filename.endswith(candidate):
            ext = candidate
            break
    if not ext:
        raise ValidationError(
            f"Formato no soportado: '{file.filename}'. Acepta: .mp4, .mov.",
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

    folder = upload_subdir("copyright")
    dest = folder / f"clean_in_{int(time.time())}{ext}"
    try:
        dest.write_bytes(contents)
    except OSError as e:
        raise APIError(
            f"No se pudo escribir el archivo en disco: {e}",
            details={"path": str(dest)},
        )

    rel_path = to_relative(dest)

    # Cargar config para que el runner tenga `paths.output_folder`
    try:
        from src.utils import load_config
        cfg = load_config()
    except Exception as e:
        raise APIError(
            f"No se pudo cargar config/config.json: {e}",
            details={"hint": "Verifica TIKTOK_ROOT_PATH."},
        )

    title = f"{file.filename} · {clean_mode}"
    params: dict[str, Any] = {
        "input_path": str(dest),  # runner necesita path absoluto
        "config": cfg,
        "clean_mode": clean_mode,
        "hook_y_pct": hook_y_pct,
        "hook_color": hook_color,
        "upscale_1080p": upscale_1080p,
        "font_path": font_path,
    }
    job = queue.enqueue(JobMode.COPYRIGHT, title=title, params=params)

    return CopyrightEnqueueResponse(
        job_id=job.id,
        title=title,
        position_in_queue=_position_in_queue(queue, job.id),
        input_path_relative=rel_path,
    )
