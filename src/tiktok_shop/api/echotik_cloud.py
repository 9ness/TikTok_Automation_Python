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
import time
from typing import Any, Callable

import requests


DEFAULT_BASE_URL = "https://open.echotik.live/api/v2"
# v3 es la ÚNICA versión documentada (opendocs.echotik.live). La usamos solo
# para `echotik/video/list`, que expone `is_ad` — v2 no tiene ese campo.
# El resto sigue en v2 porque está validado en vivo (2026-06) y v3 no se ha
# podido verificar campo a campo (cuota agotada).
V3_BASE_URL = "https://open.echotik.live/api/v3"
TIMEOUT_S = 60


def echotik_is_configured() -> bool:
    usuario, password = _auth()
    return bool(usuario and password)


# ── Seguimiento de cuota agotada ─────────────────────────────────────
# Se marca cuando la API devuelve "Usage Limit Exceeded / Increase Quota"
# (trial de 100 llamadas agotado). Se limpia en la siguiente llamada con
# éxito. El banner del Radar lo lee para avisar al operador al instante.
_LAST_QUOTA_ERROR: tuple[float, str] | None = None


def _mark_quota_error(text: str) -> bool:
    """Si `text` indica cuota agotada, marca el flag y devuelve True."""
    global _LAST_QUOTA_ERROR
    low = (text or "").lower()
    if "usage limit" in low or "increase quota" in low or "quota" in low:
        import time
        _LAST_QUOTA_ERROR = (time.time(), text[:200])
        # Deja constancia en el banco de cuentas: es lo que permite saber que
        # esta cuenta está seca y cuándo vuelve a tener llamadas.
        try:
            from src.tiktok_shop.repos import echotik_cuentas_repo

            echotik_cuentas_repo.marcar_sin_cuota(_auth()[0])
        except Exception:
            pass
        _invalidar_quota_cache()
        return True
    return False


_QUOTA_CACHE: tuple[float, bool] | None = None
_QUOTA_TTL_S = 5.0


def _invalidar_quota_cache() -> None:
    global _QUOTA_CACHE
    _QUOTA_CACHE = None


def quota_exhausted() -> bool:
    """True si la cuenta EN USO se quedó sin cuota.

    Manda lo que dice el banco de cuentas (Redis), no la global del proceso.
    La API corre con varios workers y la global era un desastre en las dos
    direcciones: la marcaba uno solo (los demás seguían gastando llamadas), y
    al cambiar de cuenta NO se limpiaba — el bucle de enlaces se paraba antes
    de la primera llamada, con la cuenta nueva intacta, diciendo "sin cuota a
    mitad" sin haber hecho ninguna.

    La global se queda como respaldo para cuando la cuenta no está en el banco
    o Redis no responde.
    """
    global _QUOTA_CACHE
    ahora = time.monotonic()
    if _QUOTA_CACHE and ahora - _QUOTA_CACHE[0] < _QUOTA_TTL_S:
        return _QUOTA_CACHE[1]
    seca = _LAST_QUOTA_ERROR is not None
    try:
        from src.tiktok_shop.repos import echotik_cuentas_repo

        c = echotik_cuentas_repo.buscar(_auth()[0])
        if c:
            seca = not echotik_cuentas_repo.disponible(c)
    except Exception:
        pass
    _QUOTA_CACHE = (ahora, seca)
    return seca


def last_quota_error_msg() -> str:
    return _LAST_QUOTA_ERROR[1] if _LAST_QUOTA_ERROR else ""


def _base_url() -> str:
    return (os.environ.get("ECHOTIK_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


# Las credenciales del plan de EchoTik caducan cada pocos días (el operador
# renueva la cuenta de pruebas), así que se pueden cambiar EN CALIENTE desde la
# UI y quedan en Redis. Sin esto había que editar el `.env` del VPS y recrear
# el container, que solo puede hacer quien tiene SSH.
CREDS_KEY = "echotik:credenciales"
_CREDS_CACHE: tuple[float, tuple[str, str]] | None = None
_CREDS_TTL_S = 30.0


def guardar_credenciales(usuario: str, password: str) -> bool:
    """Guarda las credenciales en Redis y vacía la caché."""
    global _CREDS_CACHE
    from src.tiktok_shop.repos.redis_base import get_shop_redis

    ok = get_shop_redis().set_json(
        CREDS_KEY,
        {"usuario": (usuario or "").strip(), "password": (password or "").strip()},
    )
    _CREDS_CACHE = None
    # Toda cuenta que se pone en uso entra en el banco: es la única forma de
    # que dentro de un mes se sepa que existió y que ya le renovó la cuota.
    try:
        from src.tiktok_shop.repos import echotik_cuentas_repo

        echotik_cuentas_repo.guardar(usuario, password)
    except Exception:
        pass
    return bool(ok)


def _creds_de_redis() -> tuple[str, str]:
    global _CREDS_CACHE
    ahora = time.monotonic()
    if _CREDS_CACHE and ahora - _CREDS_CACHE[0] < _CREDS_TTL_S:
        return _CREDS_CACHE[1]
    par = ("", "")
    try:
        from src.tiktok_shop.repos.redis_base import get_shop_redis

        d = get_shop_redis().get_json(CREDS_KEY) or {}
        par = ((d.get("usuario") or "").strip(), (d.get("password") or "").strip())
    except Exception:
        par = ("", "")
    _CREDS_CACHE = (ahora, par)
    return par


def _auth() -> tuple[str, str]:
    """Credenciales: manda lo guardado en Redis; el `.env` es el respaldo."""
    usuario, password = _creds_de_redis()
    if usuario and password:
        return usuario, password
    return (
        os.environ.get("ECHOTIK_API_USER", "").strip(),
        os.environ.get("ECHOTIK_API_PASSWORD", "").strip(),
    )


def _get(
    path: str, params: dict[str, Any],
    *, base: str | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> Any:
    """GET con Basic Auth. Devuelve `data` del JSON (o None si error).
    Registra el coste (~€0.0001/request) en el job activo. Nunca lanza —
    loguea y devuelve None para que el research degrade con elegancia.

    `base` permite apuntar a otra versión de la API (ver V3_BASE_URL).
    """
    url = f"{(base or _base_url()).rstrip('/')}/{path.lstrip('/')}"
    creds = _auth()
    try:
        r = requests.get(url, params=params, auth=creds, timeout=TIMEOUT_S)
    except requests.RequestException as e:
        if log_callback:
            log_callback(f"  ⚠️ EchoTik network error: {e}")
        return None

    # Consumida: la petición ha salido, así que cuenta contra las 100/mes de
    # ESTA cuenta aunque el servidor conteste un error. Es lo que permite saber
    # luego cuándo renueva y a cuál volver.
    try:
        from src.tiktok_shop.repos import echotik_cuentas_repo

        echotik_cuentas_repo.registrar_uso(creds[0])
    except Exception:
        pass

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
        if _mark_quota_error(r.text) and log_callback:
            log_callback("  🚫 EchoTik SIN CUOTA (trial agotado) — amplía plan API")
        elif log_callback:
            log_callback(f"  ⚠️ EchoTik HTTP {r.status_code}: {r.text[:150]}")
        return None
    try:
        body = r.json()
    except ValueError:
        return None
    if body.get("code") not in (0, 200):
        if _mark_quota_error(str(body.get("message"))) and log_callback:
            log_callback("  🚫 EchoTik SIN CUOTA (trial agotado) — amplía plan API")
        elif log_callback:
            log_callback(f"  ⚠️ EchoTik code={body.get('code')}: {body.get('message')}")
        return None
    # Éxito → la cuenta tiene cuota. Se limpia la marca en los DOS sitios: la
    # global de este proceso y la del banco, que es la que ven los demás
    # workers.
    global _LAST_QUOTA_ERROR
    _LAST_QUOTA_ERROR = None
    try:
        from src.tiktok_shop.repos import echotik_cuentas_repo

        echotik_cuentas_repo.marcar_con_cuota(creds[0])
    except Exception:
        pass
    _invalidar_quota_cache()
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

    # EchoTik impone page_size MÁXIMO 10. Para devolver hasta `limit`
    # productos paginamos (cada página = 1 request). Cap defensivo a 50.
    PAGE = 10
    target = min(limit, 50)
    pages = (target + PAGE - 1) // PAGE
    raw: list[dict[str, Any]] = []
    for page_num in range(1, pages + 1):
        params: dict[str, Any] = {
            "region": region, "page_num": page_num, "page_size": PAGE,
        }
        if keyword.strip():
            params["keyword"] = keyword.strip()
        if category_id:
            params["category_id"] = category_id
        data = _get("product/list", params, log_callback=log_callback)
        if not isinstance(data, list) or not data:
            break  # sin más resultados o error → paramos
        raw.extend(data)
        if len(data) < PAGE:
            break  # última página

    out: list[dict[str, Any]] = []
    for p in raw[:target]:
        pid = str(p.get("product_id") or "")
        out.append({
            "product_id": pid,
            "name": p.get("product_name") or "",
            "cover_url": _first_cover_url(p.get("cover_url")),
            "tiktok_url": f"https://www.tiktok.com/view/product/{pid}" if pid else "",
            "units_sold": int(p.get("total_sale_cnt") or 0),
            "units_sold_7d": int(p.get("total_sale_7d_cnt") or 0),
            "units_sold_30d": int(p.get("total_sale_30d_cnt") or 0),
            "units_sold_60d": int(p.get("total_sale_60d_cnt") or 0),
            "units_sold_90d": int(p.get("total_sale_90d_cnt") or 0),
            "gmv": float(p.get("total_sale_gmv_amt") or 0),
            "gmv_30d": float(p.get("total_sale_gmv_30d_amt") or 0),
            "video_count": int(p.get("total_video_cnt") or 0),
            "video_sale_count": int(p.get("total_video_sale_cnt") or 0),
            "live_sale_count": int(p.get("total_live_sale_cnt") or 0),
            "influencer_count": int(p.get("total_ifl_cnt") or 0),
            "rating": float(p.get("product_rating") or 0),
            "review_count": int(p.get("review_count") or 0),
            "min_price": float(p.get("min_price") or 0),
            "max_price": float(p.get("max_price") or 0),
            "commission_pct": _to_pct(p.get("product_commission_rate")),
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
# Ranking REAL de productos más vendidos (por ventas, no por keyword)
# ═════════════════════════════════════════════════════════════════════
def get_product_ranklist(
    *,
    region: str = "ES",
    date: str,
    rank_field: int = 1,   # 1 = por unidades vendidas (verificado)
    rank_type: int = 1,    # 1 = ranking diario (el que tiene datos en ES)
    category_id: str | None = None,
    limit: int = 10,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Ranking REAL de lo más vendido en un mercado/fecha, ordenado por
    ventas descendente (endpoint /product/ranklist). `date` = 'YYYY-MM-DD'.
    Devuelve el mismo shape normalizado que search_products."""
    if not echotik_is_configured():
        return []
    params: dict[str, Any] = {
        "region": region, "date": date, "page_num": 1,
        "page_size": min(limit, 10),
        "product_rank_field": rank_field, "rank_type": rank_type,
    }
    if category_id:
        params["category_id"] = category_id
    data = _get("product/ranklist", params, log_callback=log_callback)
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
            "units_sold_7d": 0,
            "units_sold_30d": 0,
            "gmv": float(p.get("total_sale_gmv_amt") or 0),
            "gmv_30d": 0.0,
            "video_count": int(p.get("total_video_cnt") or 0),
            "video_sale_count": 0,
            "influencer_count": int(p.get("total_ifl_cnt") or 0),
            "rating": float(p.get("product_rating") or 0),
            "review_count": int(p.get("review_count") or 0),
            "min_price": float(p.get("min_price") or 0),
            "max_price": float(p.get("max_price") or 0),
            "commission_pct": _to_pct(p.get("product_commission_rate")),
            "category_id": str(p.get("category_id") or ""),
            "region": p.get("region") or region,
        })
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
        {"product_id": product_id, "region": region, "page_num": 1, "page_size": min(limit, 10)},
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


# ═════════════════════════════════════════════════════════════════════
# Vídeos de un producto CON LA ETIQUETA DE ANUNCIO REAL  (v3, `is_ad`)
# ═════════════════════════════════════════════════════════════════════
def get_product_ad_videos(
    product_id: str,
    *,
    region: str = "ES",
    limit: int = 10,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Vídeos de un producto con `is_ad` — la etiqueta de ANUNCIO real.

    Por qué esto es la señal buena (y no el proxy de engagement):

      * v3 `echotik/video/list` documenta `is_ad` como «是否投流视频，
        1=投流视频，0=非投流视频» → 投流 = "inyección de tráfico pagado".
        Es literalmente la inyección de ADS que buscamos, no una inferencia.
      * TikTok Ads documenta que, EN LA UE (España incluida), los vídeos de
        afiliado de un producto metido en una campaña **GMV Max** reciben
        etiqueta de contenido comercial de forma AUTOMÁTICA
        (ads.tiktok.com/help/article/about-product-gmv-max) → la proporción
        de vídeos con `is_ad=1` es la huella pública de GMV Max en ese
        producto. Es la misma cuenta que el operador hace a mano contando
        etiquetas lilas "AD" en Kalodata.

    Una sola request devuelve etiqueta Y ventas por vídeo → hace innecesario
    el doble sondeo EchoTik+Apify de `ads_signal` (Apify solo daba etiqueta,
    y su `isAd` es casi siempre False por construcción).

    Devuelve la MISMA forma que consume `ads_signal.ads_injection_signal`:
    `{views, likes, comments, shares, units_sold, gmv, ad_flag}`, con
    `ad_flag` bool (None si la API no trae el campo → no lo inventamos).

    ⚠️ SIN VERIFICAR EN VIVO: la cuota del trial (100 req) está agotada, así
    que no se ha podido confirmar que `is_ad` venga poblado para region=ES.
    Ver `scripts/verify_echotik_is_ad.py` — un solo comando lo zanja.
    """
    if not echotik_is_configured() or not product_id:
        return []
    if log_callback:
        log_callback(f"  🏷️ EchoTik v3: etiqueta AD (is_ad) del producto {product_id}…")
    # OJO: sin filtro `is_ad` a propósito. Necesitamos el TOTAL y los
    # marcados para calcular la proporción; filtrar daría solo el numerador
    # y costaría 2 requests en vez de 1.
    data = _get(
        "echotik/video/list",
        {"product_id": product_id, "region": region, "page_num": 1,
         "page_size": min(limit, 10)},
        base=V3_BASE_URL,
        log_callback=log_callback,
    )
    rows = data if isinstance(data, list) else (
        data.get("list") if isinstance(data, dict) and isinstance(data.get("list"), list) else None
    )
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    for v in rows:
        out.append({
            "video_id": str(v.get("video_id") or ""),
            "url": _build_tiktok_url(v.get("user_id"), str(v.get("video_id") or "")),
            "ad_flag": _to_ad_flag(v.get("is_ad")),
            "units_sold": int(v.get("total_video_sale_cnt") or 0),
            "gmv": float(v.get("total_video_sale_gmv_amt") or 0),
            "views": int(v.get("total_views_cnt") or 0),
            "likes": int(v.get("total_digg_cnt") or 0),
            "comments": int(v.get("total_comments_cnt") or 0),
            "shares": int(v.get("total_shares_cnt") or 0),
            "create_time": v.get("create_time") or "",
        })
    out.sort(key=lambda x: x["views"], reverse=True)
    if log_callback:
        flagged = sum(1 for x in out if x["ad_flag"] is True)
        known = sum(1 for x in out if isinstance(x["ad_flag"], bool))
        if known:
            log_callback(f"  ✓ {flagged}/{known} vídeos con etiqueta AD (is_ad=1)")
        else:
            log_callback("  ⚠️ la API no devolvió `is_ad` — sin etiqueta real")
    return out


def get_fresh_ad_videos(
    *,
    region: str = "ES",
    page: int = 1,
    page_size: int = 10,
    only_ads: bool = True,
    only_selling: bool = True,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Vídeos con inyección de ADS, **del más nuevo al más viejo**.

    Es el motor del descubrimiento invertido: en vez de buscar productos y
    mirar si tienen ads, preguntamos qué se está inyectando AHORA. Cada fila
    trae `video_products` con el producto al que apunta.

    ⚠️ EL SORT ES OBLIGATORIO, no cosmético. Sin `video_sort_field=2` +
    `sort_type=1` el orden por defecto devuelve vídeos de 400-1200 días de
    antigüedad — eso es lo que nos hizo creer que el crawl de ES venía viejo
    (learnings:193). Con el sort, lo más nuevo es de ~1 día. Verificado en
    vivo 2026-07-15.

    Valores válidos (doc oficial):
      `video_sort_field`: 1=total_digg_cnt · 2=create_time · 3=total_views_cnt
      `sort_type`: 0=asc · 1=desc   (¡2 devuelve HTTP 500!)
      `sales_flag`: 1=vídeo que vende (带货视频) · `is_ad`: 1=投流视频
    """
    if not echotik_is_configured():
        return []
    params: dict[str, Any] = {
        "region": region,
        "video_sort_field": 2,   # create_time
        "sort_type": 1,          # descendente → lo más nuevo primero
        "page_num": max(1, page),
        "page_size": min(page_size, 10),
    }
    if only_ads:
        params["is_ad"] = 1
    if only_selling:
        params["sales_flag"] = 1
    data = _get("echotik/video/list", params, base=V3_BASE_URL, log_callback=log_callback)
    rows = data if isinstance(data, list) else (
        data.get("list") if isinstance(data, dict) and isinstance(data.get("list"), list) else None
    )
    return rows or []


def get_products_detail(
    product_ids: list[str],
    *,
    log_callback: Callable[[str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Métricas de varios productos → `{product_id: dict}`.

    `echotik/product/detail` acepta **10 IDs por request** (sin `region`), lo
    que hace el escaneo baratísimo: 40 productos = 4 requests. Trocea solo.

    Trae los ejes que decide la estrategia (verificado poblado en ES):
      `total_ifl_cnt` · `total_ifl_video_7d_cnt` (creadores ACTIVOS 7d) ·
      `total_video_cnt` · `total_video_7d_cnt` · `total_views_7d_cnt` ·
      `product_commission_rate` · `min_price` · `sales_trend_flag`.
    NO fiarse de `total_sale_7d_cnt`/`_30d_cnt`: vienen a 0 en ES.

    ~40% de los IDs no están fichados por EchoTik → simplemente no salen en
    el dict (el llamante los salta).
    """
    ids = [str(p) for p in product_ids if p]
    if not echotik_is_configured() or not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 10):  # el endpoint capa a 10 por request
        chunk = ids[i:i + 10]
        data = _get(
            "echotik/product/detail", {"product_ids": ",".join(chunk)},
            base=V3_BASE_URL, log_callback=log_callback,
        )
        rows = data if isinstance(data, list) else (
            data.get("list") if isinstance(data, dict) and isinstance(data.get("list"), list) else None
        )
        for r in rows or []:
            pid = str(r.get("product_id") or "")
            if pid:
                out[pid] = r
    if log_callback:
        log_callback(f"  ✓ {len(out)}/{len(ids)} productos con métricas")
    return out


def get_seller_names(
    seller_ids: list[str],
    *,
    log_callback: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """`{seller_id: nombre de la tienda}`. 10 por request, como product/detail.

    Necesario porque la URL canónica del producto está muerta: el operador
    busca por nombre en el Centro de Afiliados y varias tiendas pueden vender
    lo mismo — la tienda es lo que identifica el producto exacto.
    """
    ids = [str(s) for s in seller_ids if s]
    if not echotik_is_configured() or not ids:
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(ids), 10):
        data = _get(
            "echotik/seller/detail", {"seller_ids": ",".join(ids[i:i + 10])},
            base=V3_BASE_URL, log_callback=log_callback,
        )
        rows = data if isinstance(data, list) else (
            data.get("list") if isinstance(data, dict) and isinstance(data.get("list"), list) else None
        )
        for r in rows or []:
            sid = str(r.get("seller_id") or "")
            if sid:
                out[sid] = str(r.get("seller_name") or r.get("shop_name") or "")
    return out


def get_video_ad_detail(
    video_id: str,
    *,
    log_callback: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    """Etiquetas de anuncio CRUDAS de TikTok para un vídeo (v3 `realtime/*`).

    A diferencia de `get_product_ad_videos` (que lee el `is_ad` calculado por
    EchoTik, T+1), esto pide a EchoTik que scrapee el vídeo EN VIVO y nos
    devuelva el estado del front-end de TikTok tal cual. Sirve para dos cosas:

      1. **Cruzar** el `is_ad` de EchoTik contra la etiqueta ORIGINAL de
         TikTok → saber si EchoTik lo mide o se lo inventa (no documentado).
      2. Salir del T+1 cuando el crawl de ES viene viejo.

    Campos relevantes (de la doc oficial):
      `is_ads` (bool) · `is_paid_content` (bool) · `branded_content_type` (int)
      `commerce_info.ad_source` (int) · `commerce_info.bc_label_test_text`
      (str — el ejemplo de la propia doc es "Comisión pagada", en español).

    Cuesta 1 request POR VÍDEO (vs 1 por producto en `get_product_ad_videos`)
    → usar para muestreo/validación, no para barrer.
    """
    if not echotik_is_configured() or not video_id:
        return None
    data = _get(
        "realtime/video/detail", {"video_id": str(video_id)},
        base=V3_BASE_URL, log_callback=log_callback,
    )
    if not isinstance(data, dict):
        return None
    commerce = data.get("commerce_info") if isinstance(data.get("commerce_info"), dict) else {}
    return {
        "video_id": str(video_id),
        "is_ads": data.get("is_ads"),
        "is_paid_content": data.get("is_paid_content"),
        "branded_content_type": data.get("branded_content_type"),
        "ad_source": (commerce or {}).get("ad_source"),
        "bc_label": (commerce or {}).get("bc_label_test_text") or "",
        # Cualquier etiqueta comercial visible = TikTok declara el vídeo como
        # comercial. En la UE eso se aplica AUTOMÁTICAMENTE a los vídeos de
        # afiliado de un producto en campaña GMV Max.
        "any_commercial_label": bool(
            data.get("is_ads") or data.get("is_paid_content")
            or (commerce or {}).get("bc_label_test_text")
        ),
    }


def _to_ad_flag(raw: Any) -> bool | None:
    """`is_ad` (1=anuncio, 0=no) → bool. None si falta/ilegible.

    None significa "no lo sé", NO "no es anuncio" — `ads_signal` distingue
    ambos y solo pondera la señal cuando existe de verdad.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    try:
        return int(raw) == 1
    except (TypeError, ValueError):
        return None


def _to_pct(rate: Any) -> float:
    """Normaliza product_commission_rate a porcentaje. La API lo da como
    fracción (0.1 → 10%). Tolerante a string/None/0."""
    try:
        v = float(rate)
    except (TypeError, ValueError):
        return 0.0
    # Si viene como fracción (<=1) lo pasamos a %, si ya viene como % (>1) tal cual.
    return round(v * 100, 1) if v <= 1 else round(v, 1)


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


# Alias públicos — los usan los services (`fresh_ads_discovery`) para
# normalizar respuestas crudas de la API sin tocar helpers privados.
def to_pct(rate: Any) -> float:
    """Comisión de EchoTik → porcentaje (0.1 → 10.0)."""
    return _to_pct(rate)


def first_cover_url(raw: Any) -> str:
    """`cover_url` (string JSON) → primera URL, o ""."""
    return _first_cover_url(raw)


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
