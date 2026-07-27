"""Endpoints del Programa 4 — Viralización.

- GET  /api/v1/viralizacion/ponentes   → ponentes disponibles + nº de audios
                                          + pool de gancho/paisaje libre.
- POST /api/v1/viralizacion/generate   → valida y encola un batch.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import InvalidEnqueueRequestError
from src.api.schemas.viralizacion import (
    PonenteInfo,
    PonentesListResponse,
    ViralizacionGenerateRequest,
    ViralizacionGenerateResponse,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/viralizacion",
    tags=["viralizacion"],
    dependencies=[Depends(get_current_user)],
)


def _position_in_queue(queue: JobQueue, job_id: str) -> int:
    pending_or_running = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    for i, j in enumerate(pending_or_running):
        if j.id == job_id:
            return i
    return 0


@router.get("/ponentes", response_model=PonentesListResponse)
def list_ponentes() -> PonentesListResponse:
    from src.viralizacion import config
    from src.viralizacion.services import allocator

    items: list[PonenteInfo] = []
    for slug, meta in config.PONENTES.items():
        n_audios = len(config.ponente_audio_files(slug))
        try:
            hooks_available, hooks_total = allocator.count_available_hooks(slug)
        except Exception:
            hooks_available, hooks_total = 0, 0
        try:
            paisajes_available, paisajes_total = allocator.count_available_paisajes(slug)
        except Exception:
            paisajes_available, paisajes_total = 0, 0
        items.append(PonenteInfo(
            slug=slug,
            label=meta["label"],
            n_audios=n_audios,
            hooks_available=hooks_available,
            hooks_total=hooks_total,
            paisajes_available=paisajes_available,
            paisajes_total=paisajes_total,
        ))
    return PonentesListResponse(items=items)


@router.post(
    "/generate",
    response_model=ViralizacionGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate(
    queue: Annotated[JobQueue, Depends(get_queue)],
    body: ViralizacionGenerateRequest,
) -> ViralizacionGenerateResponse:
    from src.viralizacion.pipeline.batch import preflight_check

    ponentes = [p.strip() for p in body.ponentes if p.strip()]
    cantidad = {k: int(v) for k, v in body.cantidad.items() if int(v) > 0}
    total_videos = sum(cantidad.get(p, 0) for p in ponentes)

    if not ponentes or total_videos <= 0:
        raise InvalidEnqueueRequestError(
            "Debes seleccionar al menos un ponente con cantidad > 0.",
            details={"ponentes": ponentes, "cantidad": cantidad},
        )

    errors = preflight_check(ponentes, cantidad)
    if errors:
        raise InvalidEnqueueRequestError(
            "Validación previa falló:\n- " + "\n- ".join(errors),
            details={"errors": errors},
        )

    labels = ", ".join(f"{p}×{cantidad.get(p, 0)}" for p in ponentes)
    title = f"🚀 Viralización 1K · {labels} · {body.nombre_cuenta}"

    params: dict[str, Any] = {
        "ponentes": ponentes,
        "cantidad": cantidad,
        "nombre_cuenta": body.nombre_cuenta,
        "music_rounds": int(body.music_rounds),
    }
    job = queue.enqueue(JobMode.VIRALIZACION_BATCH, title=title, params=params)

    return ViralizacionGenerateResponse(
        job_id=job.id,
        title=title,
        position_in_queue=_position_in_queue(queue, job.id),
        total_videos=total_videos,
    )
