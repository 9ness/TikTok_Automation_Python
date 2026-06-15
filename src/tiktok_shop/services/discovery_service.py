"""Radar de Productos — descubrimiento automático de ganadores.

Orquesta la estrategia del operador de 100€/día:

  1. SCAN  — EchoTik ranklist (top ventas ES) y/o keywords del operador.
  2. SCORE — `ads_signal.score_product` puntúa cada candidato (demanda,
             pocos creadores, inyección de ADS, momentum, comisión).
  3. ADS   — (opcional, 1 request/producto) `get_product_videos` →
             `ads_injection_signal` detecta inyección de ADS real.
  4. FILTER— `DiscoveryFilters` descarta saturados / sin demanda.
  5. SAVE  — persiste candidatos en Redis (Radar sobrevive sesiones).
  6. IMPORT— `import_candidate` convierte un candidato en `Product` real
             (Redis + carpeta Drive + foto cover) listo para generar.

Degrada con elegancia: sin EchoTik configurado, `discover()` loguea aviso y
devuelve []. Nunca rompe la UI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from src.tiktok_shop.api import echotik_cloud
from src.tiktok_shop.models import Product
from src.tiktok_shop.models.discovery import AdsSignal, DiscoveredProduct
from src.tiktok_shop.models.product import (
    TikTokShopMeta, VideoConfig, slugify,
)
from src.tiktok_shop.repos.discovery_repo import DiscoveryRepo
from src.tiktok_shop.repos.product_repo import ProductRepo
from src.tiktok_shop.services import ads_signal as ads_mod
from src.tiktok_shop.services.ads_signal import (
    AdsParams, DiscoveryFilters, ScoreParams,
)


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


# ═════════════════════════════════════════════════════════════════════
# SCAN + SCORE
# ═════════════════════════════════════════════════════════════════════
def discover(
    *,
    region: str = "ES",
    keywords: list[str] | None = None,
    use_ranklist: bool = True,
    ranklist_date: str | None = None,
    per_source_limit: int = 20,
    deep_ads_check: bool = True,
    deep_ads_top_n: int = 15,
    ads_videos_per_product: int = 10,
    ads_provider: str = "echotik",   # "echotik" (engagement+ventas) | "apify" (etiqueta AD real)
    filters: DiscoveryFilters | None = None,
    score_params: ScoreParams | None = None,
    ads_params: AdsParams | None = None,
    persist: bool = True,
    log_callback: LogCallback = _noop,
) -> list[DiscoveredProduct]:
    """Escanea EchoTik, puntúa y devuelve candidatos ordenados por score.

    Args:
        keywords: nichos/keywords a escanear (ej. ["ventilador techo",
            "creatina", "crocs"]). Cada uno = 1+ requests EchoTik.
        use_ranklist: además de keywords, trae el top ventas del día (ES).
        deep_ads_check: para el top `deep_ads_top_n` por score preliminar,
            consulta sus vídeos y calcula la señal de ADS real.
        filters: descarta candidatos que no cumplen (pocos creadores, etc.).
        persist: guarda los candidatos en Redis (Radar persistente).
    """
    if not echotik_cloud.echotik_is_configured():
        log_callback(
            "⚠️ EchoTik no configurado (ECHOTIK_API_USER / ECHOTIK_API_PASSWORD). "
            "El Radar no puede descubrir productos."
        )
        return []

    filters = filters or DiscoveryFilters()
    fparams = score_params or ScoreParams()

    # ── 1. SCAN ──────────────────────────────────────────────────────
    raw_by_id: dict[str, dict] = {}

    if use_ranklist:
        date = ranklist_date or _yesterday_iso()
        log_callback(f"🏆 Ranklist top ventas {region} [{date}]…")
        for p in echotik_cloud.get_product_ranklist(
            region=region, date=date, limit=per_source_limit,
            log_callback=log_callback,
        ):
            pid = p.get("product_id")
            if pid:
                p.setdefault("_category_label", "Top ventas")
                raw_by_id.setdefault(pid, p)

    for kw in (keywords or []):
        kw = kw.strip()
        if not kw:
            continue
        log_callback(f"🔎 Buscando '{kw}' en {region}…")
        for p in echotik_cloud.search_products(
            kw, region=region, limit=per_source_limit, log_callback=log_callback,
        ):
            pid = p.get("product_id")
            if not pid:
                continue
            if pid in raw_by_id:
                continue
            p.setdefault("_category_label", kw)
            raw_by_id[pid] = p

    if not raw_by_id:
        log_callback("  ∅ Sin productos en el scan.")
        return []
    log_callback(f"  ✓ {len(raw_by_id)} productos únicos encontrados.")

    # ── 2. SCORE preliminar (sin vídeos) ─────────────────────────────
    candidates: list[DiscoveredProduct] = []
    for pid, p in raw_by_id.items():
        score = ads_mod.score_product(p, params=fparams)
        candidates.append(_to_candidate(p, score))

    candidates.sort(key=lambda c: c.score.total, reverse=True)

    # ── 3. ADS deep-check sobre el top preliminar ────────────────────
    if deep_ads_check:
        top = candidates[: max(0, deep_ads_top_n)]
        prov = "Apify (etiqueta AD real)" if ads_provider == "apify" else "EchoTik (engagement+ventas)"
        log_callback(f"📢 Deduciendo GMV Max en top {len(top)} productos · vía {prov}…")
        for c in top:
            videos = _fetch_ads_videos(
                c, region=region, provider=ads_provider,
                limit=ads_videos_per_product, log_callback=log_callback,
            )
            c.ads = ads_mod.ads_injection_signal(videos, params=ads_params)
            # Re-score con la señal de ADS deducida
            c.score = ads_mod.score_product(
                _candidate_metrics(c), params=fparams, ads=c.ads,
            )
        candidates.sort(key=lambda c: c.score.total, reverse=True)

    # ── 4. FILTER ────────────────────────────────────────────────────
    kept = [
        c for c in candidates
        if filters.passes(_candidate_metrics(c), c.score, c.ads)
    ]
    log_callback(
        f"🎯 {len(kept)}/{len(candidates)} pasan filtros "
        f"(min_score={filters.min_score}, max_creadores={filters.max_influencers})."
    )

    # ── 5. SAVE ──────────────────────────────────────────────────────
    if persist and kept:
        repo = DiscoveryRepo()
        for c in kept:
            repo.upsert_scored(c)
        log_callback(f"💾 {len(kept)} candidatos guardados en el Radar.")

    return kept


# ═════════════════════════════════════════════════════════════════════
# IMPORT — candidato → Product real
# ═════════════════════════════════════════════════════════════════════
def import_candidate(
    candidate: DiscoveredProduct,
    *,
    category: str = "otros",
    language: str = "es_ES",
    download_cover: bool = True,
    log_callback: LogCallback = _noop,
) -> Product:
    """Convierte un candidato del Radar en un `Product` persistido (Redis +
    carpeta Drive + foto cover). Marca el candidato como importado.

    Si ya fue importado antes, devuelve el `Product` existente (no duplica).
    """
    prod_repo = ProductRepo()
    disc_repo = DiscoveryRepo()

    if candidate.imported and candidate.imported_product_id:
        existing = prod_repo.get(candidate.imported_product_id)
        if existing:
            log_callback(f"↩️ '{candidate.name}' ya estaba importado.")
            return existing

    slug = _unique_slug(candidate.name or candidate.product_id, prod_repo)
    price = candidate.min_price or candidate.max_price or None
    product = Product(
        slug=slug,
        name=candidate.name or f"Producto {candidate.product_id}",
        category=category,
        language=language,
        origin="radar",
        tiktok_shop=TikTokShopMeta(
            product_url=candidate.tiktok_url or None,
            product_id=candidate.product_id,
            commission_rate=round((candidate.commission_pct or 0.0) / 100.0, 4),
            price_eur=price,
        ),
        video_config=VideoConfig(),
    )

    # Cover photo → photos_source (best-effort, nunca rompe).
    if download_cover and candidate.cover_url:
        try:
            from src.tiktok_shop.utils.photo_downloader import (
                download_image_to_product,
            )
            photo = download_image_to_product(
                product_slug=slug, image_url=candidate.cover_url,
                photo_type="packshot", origin="tiktok_shop_url",
            )
            if photo:
                product.photos.source.append(photo)
                log_callback(f"  🖼️ Cover descargada para '{product.name}'.")
        except Exception as e:
            log_callback(f"  ⚠️ Cover no descargada ({e}) — sigo.")

    prod_repo.save(product)
    log_callback(f"✅ Importado '{product.name}' (slug: {slug}).")

    candidate.imported = True
    candidate.imported_product_id = product.id
    disc_repo.save(candidate)
    return product


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════
def _fetch_ads_videos(
    candidate, *, region: str, provider: str, limit: int,
    log_callback: LogCallback,
) -> list[dict]:
    """Trae los vídeos del producto para deducir GMV Max, según provider:

    - "apify": busca en TikTok por nombre del producto y lee la ETIQUETA AD
      real (branded content) de cada vídeo. No trae ventas (TikTok no las
      expone) — la señal viene de la etiqueta + views/engagement.
    - "echotik" (default): vídeos del producto con ventas atribuidas
      (engagement + units_sold). Más barato (parte de EchoTik), sin etiqueta AD.
    """
    if provider == "apify":
        from src.tiktok_shop.api import apify_cloud
        if not apify_cloud.apify_is_configured():
            log_callback("  ⚠️ Apify no configurado — caigo a EchoTik para ADS")
        else:
            country = (region or "ES").upper()
            return apify_cloud.search_product_ad_videos(
                candidate.name, limit=limit, country=country,
                log_callback=log_callback,
            )
    return echotik_cloud.get_product_videos(
        candidate.product_id, region=region, limit=limit, log_callback=log_callback,
    )


def _yesterday_iso() -> str:
    """EchoTik ranklist diario suele tener datos consolidados de ayer."""
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def _to_candidate(p: dict, score) -> DiscoveredProduct:
    return DiscoveredProduct(
        product_id=str(p.get("product_id") or ""),
        name=p.get("name") or "",
        cover_url=p.get("cover_url") or "",
        tiktok_url=p.get("tiktok_url") or "",
        region=p.get("region") or "ES",
        category_id=str(p.get("category_id") or ""),
        category_label=str(p.get("_category_label") or ""),
        units_sold=int(p.get("units_sold") or 0),
        units_sold_7d=int(p.get("units_sold_7d") or 0),
        units_sold_30d=int(p.get("units_sold_30d") or 0),
        gmv=float(p.get("gmv") or 0.0),
        gmv_30d=float(p.get("gmv_30d") or 0.0),
        video_count=int(p.get("video_count") or 0),
        video_sale_count=int(p.get("video_sale_count") or 0),
        influencer_count=int(p.get("influencer_count") or 0),
        rating=float(p.get("rating") or 0.0),
        review_count=int(p.get("review_count") or 0),
        min_price=float(p.get("min_price") or 0.0),
        max_price=float(p.get("max_price") or 0.0),
        commission_pct=float(p.get("commission_pct") or 0.0),
        score=score,
    )


def _candidate_metrics(c: DiscoveredProduct) -> dict:
    """Reconstruye el dict de métricas que consumen score_product/filters."""
    return {
        "units_sold": c.units_sold,
        "units_sold_7d": c.units_sold_7d,
        "units_sold_30d": c.units_sold_30d,
        "gmv": c.gmv,
        "gmv_30d": c.gmv_30d,
        "video_count": c.video_count,
        "video_sale_count": c.video_sale_count,
        "influencer_count": c.influencer_count,
        "commission_pct": c.commission_pct,
    }


def _unique_slug(name: str, repo: ProductRepo) -> str:
    """Slug único: si ya existe en Redis, sufija _2, _3…"""
    base = slugify(name)
    slug = base
    n = 2
    while repo.get_by_slug(slug) is not None:
        slug = f"{base}_{n}"
        n += 1
    return slug
