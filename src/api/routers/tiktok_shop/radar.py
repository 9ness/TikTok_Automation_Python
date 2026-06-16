"""Radar de Productos — descubrimiento avanzado para la web.

A diferencia de `discovery.py` (búsqueda simple por keyword), el Radar:
  - Escanea VARIOS países (multi-región) + keywords en una pasada.
  - Puntúa cada producto (WinnerScore: pocos creadores + GMV Max + demanda
    + momentum + comisión) y DEDUCE si está impulsado con GMV Max.
  - Persiste los candidatos (sobreviven sesiones) y permite importarlos a
    `Product` con un clic.

Reutiliza todo el motor de `src.tiktok_shop.services.{discovery_service,
ads_signal}`. Cost tracking en job mode="product_discovery".
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user
from src.tiktok_shop.models.discovery import DiscoveredProduct


router = APIRouter(
    prefix="/api/v1/tiktok-shop/radar",
    tags=["tiktok-shop · radar"],
    dependencies=[Depends(get_current_user)],
)


# ── Schemas ──────────────────────────────────────────────────────────
class RadarScanRequest(BaseModel):
    regions: list[str] = Field(default_factory=lambda: ["ES"])
    keywords: list[str] = Field(default_factory=list)
    per_source_limit: int = Field(default=10, ge=5, le=30)
    deep_ads: bool = True
    ads_provider: str = "echotik"   # echotik | apify
    deep_ads_top_n: int = Field(default=8, ge=1, le=20)
    # Filtros
    max_influencers: int = 200
    min_gmv_eur: float = 300.0
    min_units_sold: int = 5
    min_commission_pct: float = 0.0
    min_score: float = 25.0
    require_ads_signal: bool = False
    require_video_driven: bool = False
    min_growth_pct: float | None = None


class RadarScanResponse(BaseModel):
    configured: bool
    scanned_regions: list[str]
    found: int
    items: list[DiscoveredProduct]
    quota_exhausted: bool = False
    hint: str = ""


class RadarImportRequest(BaseModel):
    product_id: str
    category: str = "otros"
    language: str = "es_ES"


class RadarImportResponse(BaseModel):
    ok: bool
    product_id: str | None = None
    slug: str | None = None
    message: str = ""


_SORT_KEYS = {
    "score": lambda c: c.score.total,
    "commission": lambda c: c.commission_pct,
    "gmv": lambda c: (c.gmv_30d or c.gmv),
    "gmv_max": lambda c: c.ads.gmv_max_likelihood,
    "growth": lambda c: (c.growth_pct if c.growth_pct is not None else -999),
    "creators": lambda c: -c.influencer_count,   # menos = mejor
}


# ── Endpoints ────────────────────────────────────────────────────────
@router.post("/scan", response_model=RadarScanResponse)
def scan(
    body: RadarScanRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> RadarScanResponse:
    """Escanea los países indicados, puntúa, deduce GMV Max, filtra y
    persiste los candidatos. Devuelve los que pasan filtros."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.api import echotik_cloud
    from src.tiktok_shop.services import discovery_service
    from src.tiktok_shop.services.ads_signal import DiscoveryFilters, ScoreParams

    if not echotik_cloud.echotik_is_configured():
        return RadarScanResponse(
            configured=False, scanned_regions=[], found=0, items=[],
            hint="EchoTik no configurado (ECHOTIK_API_USER / ECHOTIK_API_PASSWORD).",
        )

    regions = [r.strip().upper() for r in body.regions if r.strip()] or ["ES"]
    keywords = [k.strip() for k in body.keywords if k.strip()]
    filters = DiscoveryFilters(
        max_influencers=body.max_influencers,
        min_gmv_eur=body.min_gmv_eur,
        min_units_sold=body.min_units_sold,
        min_commission_pct=body.min_commission_pct,
        min_score=body.min_score,
        require_ads_signal=body.require_ads_signal,
        require_video_driven=body.require_video_driven,
        min_growth_pct=body.min_growth_pct,
    )
    score_params = ScoreParams(comp_zero_above=max(60, body.max_influencers + 50))

    start_job(
        job_id=f"radar_{uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="product_discovery",
        title=f"Radar scan {','.join(regions)}",
        user=operator or None,
    )
    all_items: list[DiscoveredProduct] = []
    try:
        for code in regions:
            results = discovery_service.discover(
                region=code,
                keywords=keywords,
                use_ranklist=False,
                per_source_limit=body.per_source_limit,
                deep_ads_check=body.deep_ads,
                deep_ads_top_n=body.deep_ads_top_n,
                ads_provider=body.ads_provider,
                filters=filters,
                score_params=score_params,
                persist=True,
            )
            all_items.extend(results)
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass

    all_items.sort(key=lambda c: c.score.total, reverse=True)
    exhausted = echotik_cloud.quota_exhausted()
    hint = ""
    if not all_items:
        hint = (
            "🚫 EchoTik sin cuota (trial agotado)." if exhausted
            else "Sin ganadores. Baja filtros (comisión/score) o prueba otras keywords."
        )
    return RadarScanResponse(
        configured=True, scanned_regions=regions, found=len(all_items),
        items=all_items, quota_exhausted=exhausted, hint=hint,
    )


@router.get("/candidates", response_model=list[DiscoveredProduct])
def candidates(
    operator: Annotated[str, Depends(get_current_user)],
    sort: str = Query(default="score"),
) -> list[DiscoveredProduct]:
    """Lista los candidatos persistidos del Radar, ordenados por `sort`
    (score | commission | gmv | gmv_max | growth | creators)."""
    from src.tiktok_shop.repos import DiscoveryRepo

    items = DiscoveryRepo().list_all()
    key = _SORT_KEYS.get(sort, _SORT_KEYS["score"])
    items.sort(key=key, reverse=True)
    return items


@router.post("/import", response_model=RadarImportResponse)
def import_candidate(
    body: RadarImportRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> RadarImportResponse:
    """Importa un candidato (por product_id) a 'Mis productos'."""
    from src.tiktok_shop.repos import DiscoveryRepo
    from src.tiktok_shop.services import discovery_service

    cand = DiscoveryRepo().get(body.product_id)
    if cand is None:
        return RadarImportResponse(ok=False, message="Candidato no encontrado.")
    try:
        product = discovery_service.import_candidate(
            cand, category=body.category, language=body.language,
        )
        return RadarImportResponse(
            ok=True, product_id=product.id, slug=product.slug,
            message=f"Importado '{product.name}'.",
        )
    except Exception as e:
        return RadarImportResponse(ok=False, message=f"Error: {e}")


@router.post("/clear")
def clear_non_imported(
    operator: Annotated[str, Depends(get_current_user)],
) -> dict[str, int]:
    """Borra los candidatos NO importados del Radar."""
    from src.tiktok_shop.repos import DiscoveryRepo

    return {"deleted": DiscoveryRepo().clear_non_imported()}


_ECHOTIK_REGIONS = [
    {"code": "ES", "label": "🇪🇸 España"},
    {"code": "DE", "label": "🇩🇪 Alemania"},
    {"code": "FR", "label": "🇫🇷 Francia"},
    {"code": "IT", "label": "🇮🇹 Italia"},
    {"code": "GB", "label": "🇬🇧 Reino Unido"},
    {"code": "US", "label": "🇺🇸 EE.UU."},
    {"code": "BR", "label": "🇧🇷 Brasil"},
    {"code": "MX", "label": "🇲🇽 México"},
]


@router.get("/regions")
def regions(operator: Annotated[str, Depends(get_current_user)]) -> dict:
    """Países soportados por EchoTik para el selector del Radar."""
    return {
        "regions": _ECHOTIK_REGIONS,
        "unsupported_eu": [
            "Austria", "Bélgica", "Grecia", "Hungría", "Países Bajos",
            "Polonia", "Portugal", "Chequia",
        ],
    }
