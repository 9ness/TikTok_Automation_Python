"""Cliente EchoTik — ventas REALES por producto/vídeo de TikTok Shop.

EchoTik estima ventas y GMV a nivel de producto Y de vídeo individual,
con cobertura de España (region=ES) — algo que Apify/scraping barato no
da. Lo usamos como fuente primaria de "vídeos que MÁS VENDEN" (ranking
por ventas reales, no por engagement proxy).

Auth: Basic Auth (usuario+password de la API key, NO la cuenta web).
  ECHOTIK_API_USER / ECHOTIK_API_PASSWORD en .env.
Base URL: https://open.echotik.live/api/v2 (override ECHOTIK_API_BASE_URL).

Endpoints usados (verificados live 2026-05):
  GET /product/list?region=ES&keyword=...&page_num=1&page_size=N
      → productos con total_sale_cnt, total_sale_gmv_amt, total_video_cnt
  GET /product/video/list?product_id=...&region=ES&page_num=1&page_size=N
      → vídeos del producto con total_video_sale_cnt (unidades vendidas
        atribuidas al vídeo), total_video_sale_gmv_amt, play_addr (MP4).

Coste: ~€0.0001/request (pay-per-use). Free trial 100 requests.
Degradación: si no hay creds o la API falla, los helpers devuelven []
y el research cae al viral-engagement de Apify (nunca rompe).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import requests


DEFAULT_BASE_URL = "https://open.echotik.live/api/v2"
TIMEOUT_S = 60


def echotik_is_configured() -> bool:
    return bool(
        os.environ.get("ECHOTIK_API_USER", "").strip()
        and os.environ.get("ECHOTIK_API_PASSWORD", "").strip()
    )


def _base_url() -> str:
    return (os.environ.get("ECHOTIK_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _auth() -> tuple[str, str]:
    return (
        os.environ.get("ECHOTIK_API_USER", "").strip(),
        os.environ.get("ECHOTIK_API_PASSWORD", "").strip(),
    )


def _get(
    path: str, params: dict[str, Any],
    *, log_callback: Callable[[str], None] | None = None,
) -> Any:
    """GET con Basic Auth. Devuelve `data` del JSON (o None si error).
    Registra el coste (~€0.0001/request) en el job activo. Nunca lanza —
    loguea y devuelve None para que el research degrade con elegancia."""
    url = f"{_base_url()}/{path.lstrip('/')}"
    try:
        r = requests.get(url, params=params, auth=_auth(), timeout=TIMEOUT_S)
    except requests.RequestException as e:
        if log_callback:
            log_callback(f"  ⚠️ EchoTik network error: {e}")
        return None

    # Cost tracking — cada request cuenta (aunque falle ya consumió cuota).
    try:
        from src.cost_tracking import record_custom
        record_custom(
            kind="echotik", units=1, unit_label="requests",
            cost_usd=0.00012, detail=path,
        )
    except Exception:
        pass

    if r.status_code == 401:
        if log_callback:
            log_callback("  ⚠️ EchoTik 401 — credenciales inválidas o trial caducado")
        return None
    if r.status_code >= 400:
        if log_callback:
            log_callback(f"  ⚠️ EchoTik HTTP {r.status_code}: {r.text[:150]}")
        return None
    try:
        body = r.json()
    except ValueError:
        return None
    if body.get("code") not in (0, 200):
        if log_callback:
            log_callback(f"  ⚠️ EchoTik code={body.get('code')}: {body.get('message')}")
        return None
    return body.get("data")


# ═════════════════════════════════════════════════════════════════════
# Búsqueda de productos por keyword (con ventas)
# ═════════════════════════════════════════════════════════════════════
def search_products(
    keyword: str,
    *,
    region: str = "ES",
    limit: int = 10,
    category_id: str | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Busca productos por keyword/categoría en un mercado y los devuelve
    normalizados con sus ventas. Ordenados por unidades vendidas desc."""
    if not echotik_is_configured() or (not keyword.strip() and not category_id):
        return []
    if log_callback:
        log_callback(f"🛒 EchoTik: buscando '{keyword}' en [{region}]…")
    params: dict[str, Any] = {
        "region": region, "page_num": 1, "page_size": min(limit, 30),
    }
    if keyword.strip():
        params["keyword"] = keyword.strip()
    if category_id:
        params["category_id"] = category_id
    data = _get("product/list", params, log_callback=log_callback)
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for p in data:
        pid = str(p.get("product_id") or "")
        out.append({
            "product_id": pid,
            "name": p.get("product_name") or "",
            "cover_url": _first_cover_url(p.get("cover_url")),
            "tiktok_url": f"https://www.tiktok.com/view/product/{pid}" if pid else "",
            "units_sold": int(p.get("total_sale_cnt") or 0),
            "units_sold_7d": int(p.get("total_sale_7d_cnt") or 0),
            "units_sold_30d": int(p.get("total_sale_30d_cnt") or 0),
            "gmv": float(p.get("total_sale_gmv_amt") or 0),
            "gmv_30d": float(p.get("total_sale_gmv_30d_amt") or 0),
            "video_count": int(p.get("total_video_cnt") or 0),
            "video_sale_count": int(p.get("total_video_sale_cnt") or 0),
            "influencer_count": int(p.get("total_ifl_cnt") or 0),
            "rating": float(p.get("product_rating") or 0),
            "review_count": int(p.get("review_count") or 0),
            "min_price": float(p.get("min_price") or 0),
            "max_price": float(p.get("max_price") or 0),
            "commission_rate": p.get("product_commission_rate"),
            "category_id": str(p.get("category_id") or ""),
            "region": p.get("region") or region,
        })
    out.sort(key=lambda x: x["units_sold"], reverse=True)
    if log_callback:
        top = out[0] if out else {}
        log_callback(
            f"  ✓ {len(out)} productos. Top: {top.get('units_sold', 0)} uds · "
            f"€{top.get('gmv', 0):,.0f}"
        )
    return out


# ═════════════════════════════════════════════════════════════════════
# Vídeos de un producto con ventas POR VÍDEO
# ═════════════════════════════════════════════════════════════════════
def get_product_videos(
    product_id: str,
    *,
    region: str = "ES",
    limit: int = 10,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Devuelve los vídeos que promocionan un producto, con las ventas
    atribuidas a cada uno. Ordenados por unidades vendidas desc — los
    primeros son los que MÁS venden (mejor modelo a copiar)."""
    if not echotik_is_configured() or not product_id:
        return []
    if log_callback:
        log_callback(f"  🎯 EchoTik: vídeos con ventas del producto {product_id}…")
    data = _get(
        "product/video/list",
        {"product_id": product_id, "region": region, "page_num": 1, "page_size": min(limit, 30)},
        log_callback=log_callback,
    )
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for v in data:
        vid = str(v.get("video_id") or "")
        out.append({
            "video_id": vid,
            "mp4_url": v.get("play_addr") or "",
            # URL pública del TikTok (reconstruida; user_id + video_id).
            "url": _build_tiktok_url(v.get("user_id"), vid),
            "desc": v.get("video_desc") or "",
            "hashtags": _parse_hashtags(v.get("hash_tag")),
            "units_sold": int(v.get("total_video_sale_cnt") or 0),
            "gmv": float(v.get("total_video_sale_gmv_amt") or 0),
            "views": int(v.get("total_views_cnt") or 0),
            "likes": int(v.get("total_digg_cnt") or 0),
            "comments": int(v.get("total_comments_cnt") or 0),
            "shares": int(v.get("total_shares_cnt") or 0),
            "favorites": int(v.get("total_favorites_cnt") or 0),
            "duration_s": float(v.get("duration") or 0) / 1000.0
            if float(v.get("duration") or 0) > 1000 else float(v.get("duration") or 0),
            "create_time": v.get("create_time") or "",
        })
    out.sort(key=lambda x: x["units_sold"], reverse=True)
    if log_callback:
        sold = sum(1 for x in out if x["units_sold"] > 0)
        log_callback(f"  ✓ {len(out)} vídeos ({sold} con ventas registradas)")
    return out


def _first_cover_url(raw: Any) -> str:
    """cover_url viene como string JSON: '[{"url":"...","index":0}]'.
    Devuelve la primera url, o "" si no parsea."""
    if not raw:
        return ""
    if isinstance(raw, str):
        try:
            arr = json.loads(raw)
            if isinstance(arr, list) and arr:
                return str(arr[0].get("url") or "")
        except (ValueError, AttributeError):
            return raw if raw.startswith("http") else ""
    if isinstance(raw, list) and raw:
        return str(raw[0].get("url") or "") if isinstance(raw[0], dict) else ""
    return ""


def _build_tiktok_url(user_id: Any, video_id: str) -> str:
    if not video_id:
        return ""
    uid = str(user_id or "").strip()
    if uid:
        return f"https://www.tiktok.com/@{uid}/video/{video_id}"
    return f"https://www.tiktok.com/video/{video_id}"


def _parse_hashtags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(h) for h in raw][:10]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(h.get("name", h) if isinstance(h, dict) else h) for h in parsed][:10]
        except (ValueError, AttributeError):
            return [t.strip() for t in raw.replace("#", " ").split() if t.strip()][:10]
    return []


def download_video(mp4_url: str, dest_path: str, *, timeout_s: int = 120) -> str:
    """Descarga el MP4 (play_addr) a disco. Reutiliza el patrón de Apify."""
    if not mp4_url:
        raise ValueError("mp4_url vacío")
    r = requests.get(mp4_url, timeout=timeout_s, stream=True)
    if r.status_code >= 400:
        raise RuntimeError(f"download HTTP {r.status_code}")
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(64 * 1024):
            if chunk:
                f.write(chunk)
    return dest_path
