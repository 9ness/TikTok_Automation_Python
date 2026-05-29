"""Endpoints del feedback loop de rendimiento.

El operador registra vídeos que YA publicó (URL + hook/ángulo usado),
refresca métricas vía Apify y anota pedidos/ingresos. El motor agrega
los ángulos ganadores y los inyecta en la generación de presets.

Uso desde frontend `/tiktok-shop/generate` (modo Rendimiento):
  - POST  .../performance               → registrar vídeo publicado
  - GET   .../performance               → lista + dashboard agregado
  - POST  .../performance/{vid}/refresh → re-scrape métricas TikTok
  - PUT   .../performance/{vid}         → editar pedidos/ingresos/notas
  - DELETE.../performance/{vid}         → borrar
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user, get_product_repo
from src.api.exceptions import ProductNotFoundError, ValidationError
from src.tiktok_shop.models import PublishedVideo, parse_tiktok_video_id
from src.tiktok_shop.repos import ProductRepo, PublishedVideoRepo


router = APIRouter(
    prefix="/api/v1/tiktok-shop/products",
    tags=["tiktok-shop · performance"],
    dependencies=[Depends(get_current_user)],
)


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class PublishedVideoRequest(BaseModel):
    tiktok_url: str = Field(min_length=4, max_length=400)
    hook_text: str = Field(default="", max_length=300)
    angle: str = Field(default="", max_length=50)
    kind: str = Field(default="", max_length=20)
    preset_id: str | None = None
    sound_used: str = Field(default="", max_length=150)
    orders: int = Field(default=0, ge=0)
    revenue_eur: float = Field(default=0.0, ge=0)
    notes: str = Field(default="", max_length=500)
    posted_at: str | None = None
    refresh_now: bool = True  # scrapear métricas al registrar


class PublishedVideoUpdate(BaseModel):
    hook_text: str | None = Field(default=None, max_length=300)
    angle: str | None = Field(default=None, max_length=50)
    kind: str | None = Field(default=None, max_length=20)
    sound_used: str | None = Field(default=None, max_length=150)
    orders: int | None = Field(default=None, ge=0)
    revenue_eur: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class PublishedVideoResponse(BaseModel):
    id: str
    product_id: str
    tiktok_url: str
    tiktok_id: str
    hook_text: str
    angle: str
    kind: str
    preset_id: str | None
    sound_used: str
    views: int
    likes: int
    comments: int
    shares: int
    orders: int
    revenue_eur: float
    notes: str
    posted_at: str | None
    metrics_updated_at: str | None
    created_at: str


class PerformanceListResponse(BaseModel):
    items: list[PublishedVideoResponse]
    summary: dict[str, Any]


def _to_resp(v: PublishedVideo) -> PublishedVideoResponse:
    return PublishedVideoResponse(
        id=v.id, product_id=v.product_id, tiktok_url=v.tiktok_url,
        tiktok_id=v.tiktok_id, hook_text=v.hook_text, angle=v.angle,
        kind=v.kind, preset_id=v.preset_id, sound_used=v.sound_used,
        views=v.views, likes=v.likes, comments=v.comments, shares=v.shares,
        orders=v.orders, revenue_eur=v.revenue_eur, notes=v.notes,
        posted_at=v.posted_at, metrics_updated_at=v.metrics_updated_at,
        created_at=v.created_at,
    )


def _require_product(repo: ProductRepo, product_id: str):
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    return product


# ──────────────────────────────────────────────────────────────────
# GET — lista + dashboard
# ──────────────────────────────────────────────────────────────────
@router.get("/{product_id}/performance", response_model=PerformanceListResponse)
def list_performance(
    product_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> PerformanceListResponse:
    _require_product(repo, product_id)
    from src.tiktok_shop.services.performance_service import aggregate_performance

    videos = PublishedVideoRepo().list_by_product(product_id)
    return PerformanceListResponse(
        items=[_to_resp(v) for v in videos],
        summary=aggregate_performance(videos),
    )


# ──────────────────────────────────────────────────────────────────
# POST — registrar vídeo publicado
# ──────────────────────────────────────────────────────────────────
@router.post(
    "/{product_id}/performance",
    response_model=PublishedVideoResponse,
    status_code=201,
)
def add_performance(
    product_id: str,
    payload: PublishedVideoRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
    operator: Annotated[str, Depends(get_current_user)],
) -> PublishedVideoResponse:
    _require_product(repo, product_id)
    url = payload.tiktok_url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValidationError("La URL debe empezar por http(s)://", details={"url": url})

    prepo = PublishedVideoRepo()
    video = PublishedVideo(
        product_id=product_id,
        operator=operator or "",
        tiktok_url=url,
        tiktok_id=parse_tiktok_video_id(url),
        hook_text=payload.hook_text.strip(),
        angle=payload.angle.strip(),
        kind=payload.kind.strip(),
        preset_id=payload.preset_id,
        sound_used=payload.sound_used.strip(),
        orders=payload.orders,
        revenue_eur=payload.revenue_eur,
        notes=payload.notes.strip(),
        posted_at=payload.posted_at,
    )

    if payload.refresh_now:
        _refresh_with_cost(video, product_id)

    prepo.save(video)
    return _to_resp(video)


# ──────────────────────────────────────────────────────────────────
# POST — refrescar métricas
# ──────────────────────────────────────────────────────────────────
@router.post(
    "/{product_id}/performance/{video_id}/refresh",
    response_model=PublishedVideoResponse,
)
def refresh_performance(
    product_id: str,
    video_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> PublishedVideoResponse:
    _require_product(repo, product_id)
    prepo = PublishedVideoRepo()
    video = prepo.get(video_id)
    if video is None or video.product_id != product_id:
        raise ValidationError("Vídeo no encontrado en este producto.")
    _refresh_with_cost(video, product_id)
    prepo.save(video)
    return _to_resp(video)


def _refresh_with_cost(video: PublishedVideo, product_id: str) -> None:
    """Refresca métricas envolviendo en un job de cost tracking para
    registrar el coste Apify."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.services.performance_service import refresh_video_metrics

    start_job(
        job_id=f"perf_refresh_{uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="performance_refresh",
        title=f"Refresh metrics: {video.tiktok_url[:40]}",
        product_id=product_id,
    )
    try:
        refresh_video_metrics(video)
    except Exception as e:
        print(f"[performance] refresh falló: {e}")
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
# PUT — editar campos manuales
# ──────────────────────────────────────────────────────────────────
@router.put(
    "/{product_id}/performance/{video_id}",
    response_model=PublishedVideoResponse,
)
def update_performance(
    product_id: str,
    video_id: str,
    payload: PublishedVideoUpdate,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> PublishedVideoResponse:
    _require_product(repo, product_id)
    prepo = PublishedVideoRepo()
    video = prepo.get(video_id)
    if video is None or video.product_id != product_id:
        raise ValidationError("Vídeo no encontrado en este producto.")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            setattr(video, key, value)
    prepo.save(video)
    return _to_resp(video)


# ──────────────────────────────────────────────────────────────────
# DELETE
# ──────────────────────────────────────────────────────────────────
@router.delete("/{product_id}/performance/{video_id}", status_code=204)
def delete_performance(
    product_id: str,
    video_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> None:
    _require_product(repo, product_id)
    ok = PublishedVideoRepo().delete(product_id, video_id)
    if not ok:
        raise ValidationError("Vídeo no encontrado en este producto.")
