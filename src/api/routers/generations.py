"""Endpoints del histórico de generaciones + encolado + regeneración + stream MP4."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import (
    get_current_user,
    get_generation_repo,
    get_product_repo,
    get_queue,
    get_user_repo,
)
from src.api.exceptions import (
    GenerationNotFoundError,
    InvalidEnqueueRequestError,
    ProductNotFoundError,
    UnauthorizedError,
    UserNotFoundError,
    VideoFileNotFoundError,
)
from src.api.schemas.generation import (
    EnqueueRequest,
    EnqueueResponse,
    GenerationListResponse,
    GenerationResponse,
    RegenerateRequest,
    VideoMetadataResponse,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus
from src.tiktok_shop.config import (
    ATLAS_TIERS,
    DEFAULT_VIDEO_STRATEGY,
    RESOLUTIONS,
    VIDEO_MODELS,
    VIDEO_STRATEGIES,
)
from src.tiktok_shop.models import VideoGeneration
from src.tiktok_shop.repos import GenerationRepo, ProductRepo, UserRepo
from src.tiktok_shop.services.cost_calculator import estimate_cost
from src.tiktok_shop.services.regenerate_service import (
    build_regen_params,
    build_regen_title,
)


router = APIRouter(
    prefix="/api/v1/generations",
    tags=["generations"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(gen: VideoGeneration) -> GenerationResponse:
    return GenerationResponse.model_validate(gen.model_dump(mode="json"))


def _get_generation_or_404(repo: GenerationRepo, gen_id: str) -> VideoGeneration:
    gen = repo.get(gen_id)
    if gen is None:
        raise GenerationNotFoundError(
            f"Generación '{gen_id}' no encontrada.",
            details={"generation_id": gen_id},
        )
    return gen


# ---------------------------------------------------------------------------
# GET /generations
# ---------------------------------------------------------------------------
@router.get("", response_model=GenerationListResponse)
def list_generations(
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    username: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    include_deleted: bool = Query(default=False),
    user_repo: UserRepo = Depends(get_user_repo),
) -> GenerationListResponse:
    if username and product_id:
        # Filtrado combinado: parto del username y filtro por product_id
        u = _resolve_user(user_repo, username)
        gens = [g for g in repo.list_by_user(u.id) if g.product_id == product_id]
    elif username:
        u = _resolve_user(user_repo, username)
        gens = repo.list_by_user(u.id)
    elif product_id:
        gens = repo.list_by_product(product_id)
    else:
        gens = repo.list_recent(limit=max(limit + offset, 200))

    if not include_deleted:
        gens = [g for g in gens if not g.deleted]

    if status_filter:
        gens = [g for g in gens if g.generation_status.value == status_filter]

    # Ordenar por created_at desc (list_recent ya lo está; los otros también)
    gens.sort(key=lambda g: g.created_at or "", reverse=True)
    total = len(gens)
    page = gens[offset : offset + limit]
    return GenerationListResponse(
        items=[_to_response(g) for g in page],
        total=total,
        limit=limit,
        offset=offset,
    )


def _resolve_user(user_repo: UserRepo, username: str):
    """Resuelve username (con o sin `@`) a TikTokUser. 404 si no existe."""
    raw = username.strip()
    if not raw.startswith("@"):
        raw = f"@{raw}"
    u = user_repo.get_by_username(raw)
    if u is None:
        raise UserNotFoundError(
            f"Usuario '{raw}' no encontrado.",
            details={"username": raw},
        )
    return u


# ---------------------------------------------------------------------------
# GET /generations/{id}
# ---------------------------------------------------------------------------
@router.get("/{generation_id}", response_model=GenerationResponse)
def get_generation(
    generation_id: str,
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
) -> GenerationResponse:
    gen = _get_generation_or_404(repo, generation_id)
    return _to_response(gen)


# ---------------------------------------------------------------------------
# POST /generations/enqueue
# ---------------------------------------------------------------------------
@router.post(
    "/enqueue",
    response_model=EnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_generation(
    payload: EnqueueRequest,
    user_repo: Annotated[UserRepo, Depends(get_user_repo)],
    product_repo: Annotated[ProductRepo, Depends(get_product_repo)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> EnqueueResponse:
    user = _resolve_user(user_repo, payload.username)
    product = product_repo.get(payload.product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{payload.product_id}' no encontrado.",
            details={"product_id": payload.product_id},
        )
    if payload.product_id not in user.assigned_products:
        raise InvalidEnqueueRequestError(
            f"El producto no está asignado al usuario '{user.username}'.",
            details={"username": user.username, "product_id": payload.product_id},
        )
    if payload.tier not in VIDEO_MODELS:
        raise InvalidEnqueueRequestError(
            f"Tier desconocido: '{payload.tier}'.",
            details={"tier": payload.tier},
        )
    if payload.strategy not in VIDEO_STRATEGIES:
        raise InvalidEnqueueRequestError(
            f"Estrategia desconocida: '{payload.strategy}'.",
            details={"strategy": payload.strategy},
        )
    res_def = RESOLUTIONS.get(payload.resolution)
    if res_def is None:
        raise InvalidEnqueueRequestError(
            f"Resolución desconocida: '{payload.resolution}'.",
            details={"resolution": payload.resolution},
        )
    if payload.tier in ATLAS_TIERS and payload.tier not in res_def["tiers_supported"]:
        raise InvalidEnqueueRequestError(
            f"Resolución '{payload.resolution}' no soportada por tier '{payload.tier}'.",
            details={
                "resolution": payload.resolution,
                "tier": payload.tier,
                "supported": list(res_def["tiers_supported"]),
            },
        )
    if payload.voice_enabled and not payload.voice_id:
        raise InvalidEnqueueRequestError(
            "voice_id es obligatorio cuando voice_enabled=true.",
            details={"voice_enabled": True},
        )

    # Coste estimado (solo para tiers Atlas)
    if payload.tier in ATLAS_TIERS:
        cost = estimate_cost(
            tier=payload.tier,
            duration=payload.duration_seconds,
            resolution=payload.resolution,
            voice_chars=payload.duration_seconds * 18,  # ~18 chars/seg
            with_voice=payload.voice_enabled,
        )
        estimated_total = cost["total"]
    else:
        estimated_total = 0.0

    params = _build_enqueue_params(payload, user.id)
    title = _build_enqueue_title(payload, user.username, product.name)
    job = queue.enqueue(JobMode.TIKTOK_SHOP, title=title, params=params)

    position = _position_in_queue(queue, job.id)

    estimated_seconds = (
        payload.duration_seconds
        if payload.tier in ATLAS_TIERS
        else (8 if payload.tier == "veo3_prompt_only" else 0)
    )

    return EnqueueResponse(
        job_id=job.id,
        estimated_cost=estimated_total,
        estimated_duration_seconds=estimated_seconds,
        position_in_queue=position,
    )


def _build_enqueue_params(payload: EnqueueRequest, user_id: str) -> dict:
    duration = payload.duration_seconds
    if payload.tier == "veo3_prompt_only":
        duration = 8
    elif payload.tier == "nano_banana_prompt_only":
        duration = 0

    hook_category = payload.hook_category if not payload.hook_custom else "custom"
    hook_text = payload.hook_custom or ""

    clip_overrides = (
        [(o.clip_idx, o.photo_index) for o in payload.clip_photo_overrides]
        if payload.clip_photo_overrides else None
    )

    params: dict = {
        "user_id": user_id,
        "product_id": payload.product_id,
        "tier": payload.tier,
        "duration": duration,
        "resolution": payload.resolution,
        "hook_category": hook_category,
        "hook_text": hook_text,
        "audience": payload.target_audience,
        "voice_id": payload.voice_id or "Spanish_EnergeticBoy",
        "with_voice": payload.voice_enabled,
        "language": "es",
        "is_shoppable": payload.shoppable,
        "ai_disclosure": payload.ai_disclosure,
        "temp_folder": "./temp_work",
        "clip_photo_overrides": clip_overrides,
        "pro_ref_photo_overrides": payload.pro_ref_photo_overrides,
        "strategy": payload.strategy,
    }
    if payload.tier == "nano_banana_prompt_only" and payload.n_angles:
        params["n_angles"] = payload.n_angles
    return params


def _build_enqueue_title(
    payload: EnqueueRequest, username: str, product_name: str,
) -> str:
    model = VIDEO_MODELS[payload.tier]
    return f"{username} · {product_name} · {model['tier_color']} {model['name']}"


def _position_in_queue(queue: JobQueue, job_id: str) -> int:
    """0 = es el siguiente en correr (o ya está running). 1 = hay 1 antes. Etc."""
    jobs = queue.get_all()
    pending_or_running = [
        j for j in jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    for i, j in enumerate(pending_or_running):
        if j.id == job_id:
            return i
    return 0


# ---------------------------------------------------------------------------
# POST /generations/{id}/regenerate
# ---------------------------------------------------------------------------
@router.post(
    "/{generation_id}/regenerate",
    response_model=EnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
def regenerate_generation(
    generation_id: str,
    payload: RegenerateRequest,
    gen_repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
    user_repo: Annotated[UserRepo, Depends(get_user_repo)],
    product_repo: Annotated[ProductRepo, Depends(get_product_repo)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> EnqueueResponse:
    gen = _get_generation_or_404(gen_repo, generation_id)
    user = user_repo.get(gen.user_id)
    product = product_repo.get(gen.product_id)
    if user is None or product is None:
        raise InvalidEnqueueRequestError(
            "El usuario o producto original ya no existe — no se puede regenerar.",
            details={"user_id": gen.user_id, "product_id": gen.product_id},
        )

    is_with_changes = bool(payload.overrides)
    params = build_regen_params(gen, user, product, overrides=payload.overrides or None)

    # Validar tier/resolución/strategy si vienen en overrides
    tier = params.get("tier", gen.tier_used)
    if tier not in VIDEO_MODELS:
        raise InvalidEnqueueRequestError(
            f"Tier desconocido en overrides: '{tier}'.",
            details={"tier": tier},
        )
    strategy = params.get("strategy", DEFAULT_VIDEO_STRATEGY)
    if strategy not in VIDEO_STRATEGIES:
        raise InvalidEnqueueRequestError(
            f"Estrategia desconocida en overrides: '{strategy}'.",
            details={"strategy": strategy},
        )

    model = VIDEO_MODELS[tier]
    title = build_regen_title(
        gen, user, product,
        tier_label=f"{model['tier_color']} {model['name']}",
        is_with_changes=is_with_changes,
    )

    duration = int(params.get("duration") or gen.duration_seconds or 15)
    if tier in ATLAS_TIERS:
        cost = estimate_cost(
            tier=tier,
            duration=duration,
            resolution=params.get("resolution", gen.resolution),
            voice_chars=duration * 18,
            with_voice=bool(params.get("with_voice", True)),
        )
        estimated_total = cost["total"]
    else:
        estimated_total = 0.0

    job = queue.enqueue(JobMode.TIKTOK_SHOP, title=title, params=params)
    position = _position_in_queue(queue, job.id)

    return EnqueueResponse(
        job_id=job.id,
        estimated_cost=estimated_total,
        estimated_duration_seconds=(
            duration if tier in ATLAS_TIERS
            else (8 if tier == "veo3_prompt_only" else 0)
        ),
        position_in_queue=position,
    )


# ---------------------------------------------------------------------------
# DELETE /generations/{id} — soft delete
# ---------------------------------------------------------------------------
@router.delete(
    "/{generation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_generation(
    generation_id: str,
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
) -> Response:
    gen = _get_generation_or_404(repo, generation_id)
    gen.deleted = True
    repo.save(gen)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Router secundario sin auth global — `<video src>` no puede mandar headers.
# Acepta `?api_key=` query como fallback.
# ---------------------------------------------------------------------------
video_router = APIRouter(
    prefix="/api/v1/generations",
    tags=["generations"],
)


def _auth_or_raise(
    settings: APISettings, header: str | None, query: str | None
) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


@video_router.get("/{generation_id}/video")
def stream_video(
    generation_id: str,
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    _auth_or_raise(settings, x_api_key, api_key)
    gen = _get_generation_or_404(repo, generation_id)
    if not gen.local_path:
        raise VideoFileNotFoundError(
            f"La generación '{generation_id}' no tiene archivo de vídeo asociado.",
            details={"generation_id": generation_id},
        )
    path = Path(gen.local_path)
    if not path.exists() or not path.is_file():
        raise VideoFileNotFoundError(
            f"Archivo no encontrado en disco: {gen.local_path}",
            details={"generation_id": generation_id, "path": gen.local_path},
        )
    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=path.name,
    )


# ---------------------------------------------------------------------------
# GET /generations/{id}/metadata
# ---------------------------------------------------------------------------
@router.get(
    "/{generation_id}/metadata",
    response_model=VideoMetadataResponse,
)
def video_metadata(
    generation_id: str,
    repo: Annotated[GenerationRepo, Depends(get_generation_repo)],
) -> VideoMetadataResponse:
    gen = _get_generation_or_404(repo, generation_id)

    file_size: int | None = None
    if gen.local_path and os.path.exists(gen.local_path):
        try:
            file_size = os.path.getsize(gen.local_path)
        except OSError:
            file_size = None

    return VideoMetadataResponse(
        generation_id=gen.id,
        duration_seconds=gen.duration_seconds,
        resolution=gen.resolution,
        file_size_bytes=file_size,
        clip_count=gen.num_clips or len(gen.video_prompts) or 1,
        photos_used=list(gen.photos_used or []),
        voice_id=gen.voice_used.voice_id if gen.voice_used else None,
        voiceover_script=gen.voiceover_script or None,
        cost=gen.cost.model_dump(),
        tiktok_shop_metadata=gen.tiktok_shop_metadata.model_dump(),
        drive_path=gen.local_path,
        drive_url=gen.drive_url,
        metadata_path=gen.metadata_path,
        completed_at=gen.completed_at,
    )
