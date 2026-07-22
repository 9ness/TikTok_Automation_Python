"""Cliente ScrapeCreators — búsqueda de productos de TikTok Shop por nicho.

Por qué existe: EchoTik-España lleva caído (devuelve ventas a 0) desde el
"risk control" de TikTok. ScrapeCreators SÍ devuelve productos españoles con
ventas reales (verificado julio 2026), y encima con FOTO que carga (las de
EchoTik daban 403). Su límite: NO da nº de creadores ni señal de ADS → solo
sirve para DESCUBRIR productos que venden; la tendencia/competencia se
verifica en el Centro de Afiliados (gratis).

Precio: pago único 47$ = 25.000 créditos (no caducan) + 100 gratis. 1 crédito
por búsqueda (devuelve ~30 productos). Clave en `SCRAPECREATORS_API_KEY`.

Endpoint: GET /v1/tiktok/shop/search?query=&region=ES&page=
Solo acepta query + region + page (sin ordenar/filtrar) → el orden por ventas
lo hacemos aquí. `region=ES` soportado (aviso "non-US no fiable" NO se cumple
para España, comprobado).
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
import json
from typing import Any

BASE = "https://api.scrapecreators.com"
TIMEOUT_S = 45


def is_configured() -> bool:
    return bool(os.environ.get("SCRAPECREATORS_API_KEY", "").strip())


def _get(path: str, params: dict) -> dict | None:
    key = os.environ.get("SCRAPECREATORS_API_KEY", "").strip()
    if not key:
        return None
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"x-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def _price(p: dict) -> float:
    pi = p.get("product_price_info") or {}
    for k in ("sale_price_format", "sale_price_decimal", "single_product_price_format"):
        try:
            v = float(pi.get(k) or 0)
            if v > 0:
                return v
        except (TypeError, ValueError):
            continue
    return 0.0


def _image(p: dict) -> str:
    im = p.get("image") or {}
    ul = im.get("url_list") or []
    return ul[0] if ul else ""


def _sold(p: dict) -> int:
    si = p.get("sold_info")
    if isinstance(si, dict):
        return int(si.get("sold_count") or 0)
    return int(p.get("sold_count") or 0)


def search_shop_products(
    query: str, *, region: str = "ES", page: int = 1,
    min_sold: int = 0, min_price: float = 0.0, max_price: float = 0.0,
) -> tuple[list[dict[str, Any]], int | None]:
    """Busca productos por nicho. Devuelve (productos, créditos_restantes).

    Cada producto normalizado: {product_id, title, sold, price, image, seller}.
    Ordenados por ventas desc. Filtros opcionales (min ventas, rango de precio).
    """
    if not query.strip():
        return [], None
    d = _get("/v1/tiktok/shop/search",
             {"query": query.strip(), "region": region, "page": max(1, page)})
    if not d:
        return [], None
    credits = d.get("credits_remaining")
    out: list[dict[str, Any]] = []
    for p in (d.get("products") or []):
        pid = str(p.get("product_id") or "")
        if not pid:
            continue
        sold = _sold(p)
        price = _price(p)
        if sold < min_sold:
            continue
        if min_price and price < min_price:
            continue
        if max_price and price > max_price:
            continue
        se = p.get("seller_info")
        out.append({
            "product_id": pid,
            "title": p.get("title") or "",
            "sold": sold,
            "price": round(price, 2),
            "image": _image(p),
            "seller": se.get("shop_name", "") if isinstance(se, dict) else "",
        })
    out.sort(key=lambda x: x["sold"], reverse=True)
    return out, credits
