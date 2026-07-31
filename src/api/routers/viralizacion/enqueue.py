"""Endpoints del Programa 4 — Viralización.

- GET  /api/v1/viralizacion/ponentes   → ponentes disponibles + nº de audios
                                          + pool de gancho/paisaje libre.
- POST /api/v1/viralizacion/generate   → valida y encola un batch.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import InvalidEnqueueRequestError
from src.api.schemas.viralizacion import (
    CarpetasListResponse,
    PonenteInfo,
    PonentesListResponse,
    RoundPlan,
    RoundPlanResponse,
    StyleChoice,
    AudioItem,
    AudiosListResponse,
    CuentaEjemplo,
    CuentasEjemploRequest,
    CuentasEjemploResponse,
    StylesListResponse,
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
        # cache_only: el escaneo de cara tarda minutos y no puede bloquear el GET.
        try:
            hooks_available, hooks_total = allocator.count_available_hooks(
                slug, cache_only=True
            )
        except Exception:
            hooks_available, hooks_total = 0, 0
        try:
            paisajes_available, paisajes_total = allocator.count_available_paisajes(
                slug, cache_only=True
            )
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


@router.get("/carpetas", response_model=CarpetasListResponse)
def list_carpetas() -> CarpetasListResponse:
    """Carpetas ya creadas bajo VIRALIZACION.

    La UI las ofrece en un desplegable para no tener que recordar el nombre
    exacto (y poder acumular tandas en la misma carpeta).
    """
    from src.viralizacion.services import drive_uploader

    return CarpetasListResponse(items=drive_uploader.list_carpetas())


@router.get("/cuentas-ejemplo", response_model=CuentasEjemploResponse)
def get_cuentas_ejemplo() -> CuentasEjemploResponse:
    """Cuentas de TikTok de referencia que mira el operador."""
    from src.viralizacion.repos import cuentas_repo

    return CuentasEjemploResponse(
        ok=True,
        cuentas=[CuentaEjemplo(**c) for c in cuentas_repo.get_cuentas()],
    )


@router.post("/cuentas-ejemplo", response_model=CuentasEjemploResponse)
def set_cuentas_ejemplo(body: CuentasEjemploRequest) -> CuentasEjemploResponse:
    """Guarda la lista entera (la UI manda siempre el conjunto completo)."""
    from src.viralizacion.repos import cuentas_repo

    try:
        guardadas = cuentas_repo.save_cuentas(
            [c.model_dump() for c in body.cuentas]
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return CuentasEjemploResponse(
        ok=True, cuentas=[CuentaEjemplo(**c) for c in guardadas],
    )


@router.get("/audios", response_model=AudiosListResponse)
def list_audios(ponente: Annotated[str, Query()]) -> AudiosListResponse:
    """Audios del banco de un ponente, del más largo al más corto.

    Se ordenan por duración porque es el criterio con el que el operador
    elige: los largos retienen más y son los que le viralizan.
    """
    from src.viralizacion import config
    from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration

    if not config.is_known_ponente(ponente):
        raise APIError(f"Ponente desconocido: {ponente!r}", status_code=400)
    items = [
        AudioItem(nombre=a.name, duracion_s=round(ffprobe_duration(a), 1))
        for a in config.ponente_audio_files(ponente)
    ]
    items.sort(key=lambda a: a.duracion_s, reverse=True)
    return AudiosListResponse(items=items)


@router.get("/estilos", response_model=StylesListResponse)
def list_estilos() -> StylesListResponse:
    from src.viralizacion.pipeline import styles

    return StylesListResponse(
        items=[StyleChoice(**c) for c in styles.style_choices()]
    )


@router.get("/plan", response_model=RoundPlanResponse)
def round_plan(
    ponente: Annotated[str, Query()],
    cantidad: Annotated[int, Query(ge=1)],
) -> RoundPlanResponse:
    """Cuántos vídeos caen en cada ronda, para dibujar un selector por ronda.

    Con 8 audios y 10 vídeos salen 2 rondas: la 1 con 8 vídeos y la 2 con 2.
    Sin esto el operador no puede saber cuántos estilos tiene que elegir.
    """
    from src.viralizacion import config
    from src.viralizacion.pipeline import styles
    from src.viralizacion.pipeline.batch import _rounds_per_audio

    n_audios = len(config.ponente_audio_files(ponente))
    if n_audios <= 0:
        raise InvalidEnqueueRequestError(
            f"El ponente '{ponente}' no tiene audios.", details={"ponente": ponente}
        )

    per_audio = _rounds_per_audio(int(cantidad), n_audios)
    max_rondas = max(per_audio) if per_audio else 0
    rounds = [
        RoundPlan(
            ronda=r,
            n_videos=sum(1 for x in per_audio if x >= r),
            default_style=styles.get_style_for_round(r).key,
        )
        for r in range(1, max_rondas + 1)
    ]
    return RoundPlanResponse(total_videos=int(cantidad), rounds=rounds)


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

    errors = preflight_check(ponentes, cantidad, body.audios or None)
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
        "round_styles": [s for s in (body.round_styles or []) if s],
        "styles_pool": [s for s in (body.styles_pool or []) if s],
        "audios": {k: list(v) for k, v in (body.audios or {}).items() if v},
    }
    job = queue.enqueue(JobMode.VIRALIZACION_BATCH, title=title, params=params)

    return ViralizacionGenerateResponse(
        job_id=job.id,
        title=title,
        position_in_queue=_position_in_queue(queue, job.id),
        total_videos=total_videos,
    )
