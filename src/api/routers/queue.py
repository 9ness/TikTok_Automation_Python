"""Endpoints de la cola de jobs (lectura + cancelación + descarga de MP4)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import (
    JobNotFoundError,
    UnauthorizedError,
    ValidationError,
    VideoFileNotFoundError,
)
from src.api.schemas.queue import ActiveJobResponse, QueueStateResponse
from src.queue.manager import JobQueue
from src.queue.models import Job, JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/queue",
    tags=["queue"],
    dependencies=[Depends(get_current_user)],
)


_FINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


def _to_response(job: Job) -> ActiveJobResponse:
    return ActiveJobResponse(
        job_id=job.id,
        mode=job.mode.value,
        title=job.title,
        status=job.status.value,
        progress_percent=round(max(0.0, min(1.0, job.progress)) * 100, 2),
        current_step=job.progress_label or "",
        estimated_remaining_seconds=job.eta_s,
        elapsed_seconds=job.elapsed_s,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        enqueued_by=job.enqueued_by,
        error=job.error,
        result_path=job.result_path,
        params=_safe_params(job.params),
    )


def _safe_params(params: dict) -> dict:
    """Subset de params relevantes para el frontend. Excluye flags internos
    como `_cancel_requested` y `temp_folder`."""
    keys = {
        "user_id", "product_id", "tier", "duration", "resolution",
        "hook_category", "hook_text", "audience", "voice_id", "with_voice",
        "language", "is_shoppable", "ai_disclosure", "strategy", "n_angles",
        "regenerated_from",
    }
    return {k: v for k, v in (params or {}).items() if k in keys}


# ---------------------------------------------------------------------------
# GET /queue
# ---------------------------------------------------------------------------
def _parse_mode_filter(mode_csv: str | None) -> set[JobMode] | None:
    """Parse `?mode=tiktok_shop,presidents` → set de JobMode. Lanza
    ValidationError si algún valor no es válido."""
    if not mode_csv:
        return None
    raw_values = [m.strip() for m in mode_csv.split(",") if m.strip()]
    if not raw_values:
        return None
    try:
        return {JobMode(v) for v in raw_values}
    except ValueError as e:
        valid = sorted(m.value for m in JobMode)
        raise ValidationError(
            f"Modo desconocido en filtro: {e}. Modos válidos: {valid}",
            details={"input": mode_csv, "valid_modes": valid},
        )


@router.get("", response_model=QueueStateResponse)
def get_queue_state(
    queue: Annotated[JobQueue, Depends(get_queue)],
    mode: str | None = Query(
        default=None,
        description="CSV de modos para filtrar (ej. 'tiktok_shop,presidents'). Default: todos.",
    ),
    finished_limit: int = Query(default=5, ge=1, le=100),
) -> QueueStateResponse:
    mode_filter = _parse_mode_filter(mode)
    all_jobs = queue.get_all()
    if mode_filter is not None:
        all_jobs = [j for j in all_jobs if j.mode in mode_filter]
    active = [
        j for j in all_jobs
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    finished = [j for j in all_jobs if j.status in _FINAL_STATUSES]
    finished.sort(key=lambda j: j.finished_at or 0, reverse=True)
    return QueueStateResponse(
        active_jobs=[_to_response(j) for j in active],
        pending_count=sum(1 for j in active if j.status == JobStatus.PENDING),
        running_count=sum(1 for j in active if j.status == JobStatus.RUNNING),
        recent_completed=[_to_response(j) for j in finished[:finished_limit]],
    )


# ---------------------------------------------------------------------------
# GET /queue/{job_id}
# ---------------------------------------------------------------------------
@router.get("/{job_id}", response_model=ActiveJobResponse)
def get_job(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> ActiveJobResponse:
    for j in queue.get_all():
        if j.id == job_id:
            return _to_response(j)
    raise JobNotFoundError(
        f"Job '{job_id}' no encontrado.",
        details={"job_id": job_id},
    )


# ---------------------------------------------------------------------------
# DELETE /queue/{job_id} — cancel
# ---------------------------------------------------------------------------
@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_or_remove_job(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> Response:
    """- Si el job está activo (pending/running) → lo CANCELA.
    - Si el job está en estado final (completed/failed/cancelled) → lo
      QUITA del historial persistente (queue_state.json)."""
    job = next((j for j in queue.get_all() if j.id == job_id), None)
    if job is None:
        raise JobNotFoundError(
            f"Job '{job_id}' no encontrado.",
            details={"job_id": job_id},
        )
    if job.status in _FINAL_STATUSES:
        queue.remove(job_id)
    else:
        queue.cancel(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# DELETE /queue/recent — vacía el historial de jobs finalizados
# ---------------------------------------------------------------------------
@router.delete(
    "/recent/all",
    status_code=status.HTTP_200_OK,
)
def clear_recent(
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Elimina TODOS los jobs en estado final del historial persistente.
    Los jobs activos (pending/running) NO se tocan."""
    removed = queue.clear_finished()
    return {"removed": removed}


# ---------------------------------------------------------------------------
# Router secundario sin auth global — para <video src> / <a download> que
# no pueden mandar headers `X-API-Key`. Acepta `?api_key=` como fallback.
# ---------------------------------------------------------------------------
video_router = APIRouter(
    prefix="/api/v1/queue",
    tags=["queue"],
)


def _find_job(queue: JobQueue, job_id: str) -> Job:
    for j in queue.get_all():
        if j.id == job_id:
            return j
    raise JobNotFoundError(
        f"Job '{job_id}' no encontrado.",
        details={"job_id": job_id},
    )


def _auth_or_raise(settings: APISettings, header: str | None, query: str | None) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


@video_router.get("/{job_id}/video")
def stream_job_video(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    _auth_or_raise(settings, x_api_key, api_key)
    job = _find_job(queue, job_id)
    if not job.result_path:
        raise VideoFileNotFoundError(
            f"Job '{job_id}' no tiene MP4 asociado.",
            details={"job_id": job_id, "status": job.status.value},
        )
    path = Path(job.result_path)
    if not path.exists() or not path.is_file():
        raise VideoFileNotFoundError(
            f"Archivo no existe en disco: {job.result_path}",
            details={"job_id": job_id, "path": job.result_path},
        )
    return FileResponse(path=str(path), media_type="video/mp4", filename=path.name)


@video_router.get("/{job_id}/download")
def download_job_video(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    _auth_or_raise(settings, x_api_key, api_key)
    job = _find_job(queue, job_id)
    if not job.result_path:
        raise VideoFileNotFoundError(
            f"Job '{job_id}' no tiene MP4 asociado.",
            details={"job_id": job_id},
        )
    path = Path(job.result_path)
    if not path.exists() or not path.is_file():
        raise VideoFileNotFoundError(
            f"Archivo no existe en disco: {job.result_path}",
            details={"job_id": job_id, "path": job.result_path},
        )
    # FileResponse con `filename=` añade Content-Disposition: attachment
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=path.name,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@video_router.get("/{job_id}/drive-search-url")
def drive_search_url(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Devuelve una URL de búsqueda en Drive con el nombre del MP4.
    No requiere Drive API — solo construye `drive.google.com/drive/search?q=...`.

    El usuario tendrá que estar logueado en Drive en el navegador para que
    funcione. Si no encontramos el archivo localmente devolvemos None.
    """
    job = _find_job(queue, job_id)
    if not job.result_path:
        return {"url": None, "filename": None}
    filename = os.path.basename(job.result_path)
    from urllib.parse import quote
    return {
        "url": f"https://drive.google.com/drive/search?q={quote(filename)}",
        "filename": filename,
    }
