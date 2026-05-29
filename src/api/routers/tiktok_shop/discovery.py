"""Endpoint de descubrimiento de productos (EchoTik).

Busca productos que VENDEN de verdad en un mercado (ES por defecto) por
keyword/categoría, ordenados por ventas reales. El frontend muestra los
resultados y permite añadirlos a "Mis productos" en 1 clic (con URL +
foto de portada ya rellenadas).

Coste: 1 request EchoTik por búsqueda (~€0.0001). Cost tracking en job
mode="product_discovery".
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.api.dependencies import get_current_user
from src.api.exceptions import ValidationError


router = APIRouter(
    prefix="/api/v1/tiktok-shop/discovery",
    tags=["tiktok-shop · discovery"],
    dependencies=[Depends(get_current_user)],
)


class DiscoveredProduct(BaseModel):
    product_id: str
    name: str
    cover_url: str
    tiktok_url: str
    units_sold: int
    units_sold_7d: int
    units_sold_30d: int
    gmv: float
    gmv_30d: float
    video_count: int
    influencer_count: int
    rating: float
    review_count: int
    min_price: float
    max_price: float
    commission_pct: float
    category_id: str
    region: str


class DiscoveryResponse(BaseModel):
    configured: bool
    region: str
    query: str
    sort: str
    items: list[DiscoveredProduct]
    hint: str = ""


_SORT_KEYS = {
    "sales": "units_sold",
    "sales_7d": "units_sold_7d",
    "sales_30d": "units_sold_30d",
    "gmv": "gmv",
    "commission": "commission_pct",
    "price_asc": "min_price",
    "price_desc": "max_price",
    "rating": "rating",
}


@router.get("/products", response_model=DiscoveryResponse)
def discover_products(
    operator: Annotated[str, Depends(get_current_user)],
    keyword: str = Query(default="", max_length=120),
    category_id: str = Query(default=""),
    region: str = Query(default="ES"),
    sort: str = Query(default="sales"),
    min_commission: float = Query(default=0, ge=0, le=100),
    max_price: float = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=30),
) -> DiscoveryResponse:
    """Busca productos en EchoTik por keyword/categoría y los devuelve
    ordenados por la métrica `sort` (client-side, sobre datos reales)."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.api import echotik_cloud

    if not echotik_cloud.echotik_is_configured():
        return DiscoveryResponse(
            configured=False, region=region, query=keyword, sort=sort, items=[],
            hint=("EchoTik no configurado. Define ECHOTIK_API_USER / "
                  "ECHOTIK_API_PASSWORD en .env."),
        )

    if not keyword.strip() and not category_id.strip():
        raise ValidationError(
            "Necesito una palabra clave o una categoría para buscar.",
            details={},
        )

    start_job(
        job_id=f"discovery_{uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="product_discovery",
        title=f"Discover: {keyword or category_id} [{region}]",
        user=operator or None,
    )
    try:
        products = echotik_cloud.search_products(
            keyword.strip() or " ",
            region=region,
            limit=limit,
            category_id=category_id.strip() or None,
        )
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass

    # Filtros client-side (sobre datos reales del page devuelto).
    if min_commission > 0:
        products = [p for p in products if (p.get("commission_pct") or 0) >= min_commission]
    if max_price > 0:
        products = [p for p in products if 0 < (p.get("min_price") or 0) <= max_price]

    sort_key = _SORT_KEYS.get(sort, "units_sold")
    reverse = sort != "price_asc"
    products.sort(key=lambda p: p.get(sort_key) or 0, reverse=reverse)

    items = [DiscoveredProduct(**p) for p in products]
    hint = ""
    if not items:
        hint = f"Sin resultados para '{keyword}' en {region}."
    elif all(p.units_sold == 0 for p in items):
        hint = ("Estos productos aún no tienen ventas registradas en "
                f"{region}. Prueba otra keyword o revisa otro mercado.")
    return DiscoveryResponse(
        configured=True, region=region, query=keyword, sort=sort,
        items=items, hint=hint,
    )


# Nichos que se escanean para el ranking cruzado "Top ventas". Las
# keywords deben ir EN EL IDIOMA del mercado — buscar "cocina" en US
# devuelve productos en español, no los top reales de EE.UU.
_TOP_NICHES_ES = ["belleza", "fitness", "cocina", "hogar", "salud", "tecnología"]
_TOP_NICHES_EN = ["beauty", "fitness", "kitchen", "home", "health", "gadgets"]
_TOP_NICHES_BY_REGION = {
    "ES": _TOP_NICHES_ES,
    "MX": _TOP_NICHES_ES,
    "US": _TOP_NICHES_EN,
    "GB": _TOP_NICHES_EN,
    "IT": ["bellezza", "fitness", "cucina", "casa", "salute", "gadget"],
    "FR": ["beauté", "fitness", "cuisine", "maison", "santé", "gadgets"],
    "DE": ["beauty", "fitness", "küche", "haushalt", "gesundheit", "gadgets"],
}


def _niches_for(region: str) -> list[str]:
    return _TOP_NICHES_BY_REGION.get(region.upper(), _TOP_NICHES_EN)


@router.get("/top-sellers", response_model=DiscoveryResponse)
def top_sellers(
    operator: Annotated[str, Depends(get_current_user)],
    region: str = Query(default="ES"),
    limit: int = Query(default=30, ge=1, le=60),
) -> DiscoveryResponse:
    """Ranking cruzado de lo más vendido: escanea N nichos (1 request c/u),
    junta, dedup por product_id y ordena por unidades vendidas. La API no
    expone un ranking global, así que lo construimos sumando nichos."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.api import echotik_cloud

    if not echotik_cloud.echotik_is_configured():
        return DiscoveryResponse(
            configured=False, region=region, query="top-sellers", sort="sales",
            items=[], hint="EchoTik no configurado.",
        )

    niches = _niches_for(region)
    start_job(
        job_id=f"topsellers_{uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="product_discovery",
        title=f"Top sellers [{region}] x{len(niches)} nichos",
        user=operator or None,
    )
    merged: dict[str, dict[str, Any]] = {}
    try:
        for niche in niches:
            for p in echotik_cloud.search_products(niche, region=region, limit=10):
                pid = p.get("product_id")
                if not pid:
                    continue
                # Nos quedamos con la entrada de más ventas si se repite.
                if pid not in merged or (p.get("units_sold") or 0) > (
                    merged[pid].get("units_sold") or 0
                ):
                    merged[pid] = p
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass

    products = sorted(
        merged.values(), key=lambda p: p.get("units_sold") or 0, reverse=True,
    )[:limit]
    items = [DiscoveredProduct(**p) for p in products]
    return DiscoveryResponse(
        configured=True, region=region, query="🔥 Top ventas",
        sort="sales", items=items,
        hint="" if items else "Sin datos de ventas en este momento.",
    )
