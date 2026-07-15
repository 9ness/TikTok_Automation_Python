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

import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user, get_queue
from src.queue.manager import JobQueue
from src.queue.models import JobMode
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
    "price": lambda c: (c.max_price or c.min_price),  # caro = menos competencia
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


# ── Calendario / Plan (Fase 2) ───────────────────────────────────────
_PER_DAY_DEFAULT = 10   # productos por día en la cola del calendario


def _pack_options(research: bool, n_carousels: int, n_photos: int) -> dict:
    return {
        "download_photos": n_photos > 0,
        "photos_to_download": n_photos,
        "research": research,
        "generate_video_presets": True,
        "n_carousels": n_carousels,
    }


def _light_pack_options() -> dict:
    """Pack LIGERO: solo análisis + hooks BOFU. Sin vídeos IA ni carruseles
    (las plantillas universales son estáticas, no necesitan generación)."""
    return {
        "download_photos": False,   # la foto ya viene de la URL
        "photos_to_download": 0,
        "analyze": True,
        "research": False,
        "generate_video_presets": False,
        "n_carousels": 0,
        "generate_nano_banana": False,
    }


def _reflow_plan(plan, per_day: int = _PER_DAY_DEFAULT) -> None:
    """Recompacta el calendario como una cola: ordena por día (estable,
    preserva el orden dentro del día) y reparte en bloques de `per_day`.
    Así, al borrar productos de un día, los posteriores suben para rellenar."""
    per_day = max(1, per_day)
    plan.entries.sort(key=lambda e: e.day)
    for i, e in enumerate(plan.entries):
        e.day = i // per_day + 1
    plan.days = max(1, (len(plan.entries) + per_day - 1) // per_day)


class ImportToCalendarRequest(BaseModel):
    product_id: str
    day: int = 1
    category: str = "otros"
    language: str = "es_ES"
    research: bool = True
    n_carousels: int = 2
    n_photos: int = 4


class CalendarActionResponse(BaseModel):
    ok: bool
    product_id: str | None = None
    slug: str | None = None
    job_id: str | None = None
    message: str = ""


@router.post("/import-to-calendar", response_model=CalendarActionResponse)
def import_to_calendar(
    body: ImportToCalendarRequest,
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> CalendarActionResponse:
    """Importa un candidato → Product, lo añade al día del calendario y
    encola la generación del pack (research + estilos + carruseles)."""
    from src.tiktok_shop.models.week_plan import PlanEntry, WeekPlan
    from src.tiktok_shop.repos import DiscoveryRepo, PlanRepo
    from src.tiktok_shop.services import discovery_service

    cand = DiscoveryRepo().get(body.product_id)
    if cand is None:
        return CalendarActionResponse(ok=False, message="Candidato no encontrado.")
    try:
        product = discovery_service.import_candidate(
            cand, category=body.category, language=body.language,
        )
    except Exception as e:
        return CalendarActionResponse(ok=False, message=f"Error importando: {e}")

    # Añadir al plan actual (o crear uno).
    prepo = PlanRepo()
    plan = prepo.get_current()
    if plan is None:
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plan = WeekPlan(label=f"Semana {date}", date=date, days=7)
    if not any(e.product_id == product.id for e in plan.entries):
        plan.entries.append(PlanEntry(
            day=max(1, body.day), product_id=product.id, slug=product.slug,
            name=product.name, score=cand.score.total, ads_verdict=cand.ads.verdict,
        ))
    plan.days = max(plan.days, body.day)
    prepo.save(plan, make_current=True)

    job = queue.enqueue(
        JobMode.TIKTOK_SHOP_PACK,
        title=f"📦 Pack: {product.name}",
        params={
            "product_id": product.id,
            "options": _pack_options(body.research, body.n_carousels, body.n_photos),
        },
        enqueued_by=operator or None,
    )
    return CalendarActionResponse(
        ok=True, product_id=product.id, slug=product.slug, job_id=job.id,
        message=f"'{product.name}' en el día {body.day}, generando pack…",
    )


class AutoDayRequest(BaseModel):
    """Llenar un día solo, con lo que está recibiendo ADS ahora mismo."""
    day: int = 1
    top_n: int = 5
    region: str = "ES"
    days_window: float = 3.0        # frescura de la inyección (días)
    video_pages: int = 8            # 10 vídeos por página, 1 request c/u
    max_influencers: int | None = 250   # «menos de 200-250» — repartir menos
    min_commission_eur: float = 3.0     # suelo en EUROS por venta, no en %
    # 3 por producto MIENTRAS SE APRENDE. El operador de 100€/día sube 1 y
    # dobla en el que vende, pero eso presupone saber YA qué vídeo funciona
    # (4 cuentas, meses en US). Con 1 vídeo, si no vende no sabes si falló el
    # producto o el creativo. Las 3 versiones son formatos DISTINTOS por
    # diseño (problem_video_director.md) → test A/B del creativo, no 3 copias.
    # Cuando se sepa qué formato gana → bajar a 1-2 y doblar en ganadores.
    videos_per_product: int = 3
    gens: list[str] | None = None       # qué generar: problem_videos por defecto


@router.post("/plan/auto-day", response_model=CalendarActionResponse)
def auto_day(
    body: AutoDayRequest,
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> CalendarActionResponse:
    """Botón "llenar el día": busca los productos con inyección de ADS FRESCA
    en España, se queda con los `top_n` mejores y los deja en el día `day` del
    calendario con sus prompts listos.

    Va por la cola porque tarda: ~18 requests a EchoTik + los prompts de cada
    producto (Gemini). El progreso se ve en el drawer de Cola.
    """
    job = queue.enqueue(
        JobMode.TIKTOK_SHOP_AUTO_DAY,
        title=f"🎯 Día {body.day}: top {body.top_n} con ADS frescos",
        params={
            "day": body.day,
            "top_n": body.top_n,
            "region": body.region,
            "days_window": body.days_window,
            "video_pages": body.video_pages,
            "max_influencers": body.max_influencers,
            "min_commission_eur": body.min_commission_eur,
            "options": _gen_options(body.gens, body.videos_per_product),
        },
        enqueued_by=operator or None,
    )
    return CalendarActionResponse(
        ok=True, product_id=None, slug=None, job_id=job.id,
        message=f"Buscando los {body.top_n} mejores productos con ADS frescos "
                f"para el día {body.day}…",
    )


class PlanGenerateRequest(BaseModel):
    per_day: int = 2
    days: int = 7
    research: bool = True
    n_carousels: int = 2
    n_photos: int = 4


@router.post("/plan/generate", response_model=CalendarActionResponse)
def plan_generate(
    body: PlanGenerateRequest,
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> CalendarActionResponse:
    """Encola el plan N/día: importa los top candidatos y construye sus packs."""
    n_products = max(1, body.per_day * body.days)
    job = queue.enqueue(
        JobMode.TIKTOK_SHOP_PLAN,
        title=f"🗓️ Plan {body.per_day}/día × {body.days}d",
        params={
            "n_products": n_products, "per_day": body.per_day, "days": body.days,
            "options": _pack_options(body.research, body.n_carousels, body.n_photos),
        },
        enqueued_by=operator or None,
    )
    return CalendarActionResponse(
        ok=True, job_id=job.id,
        message=f"Plan {body.per_day}/día encolado ({n_products} productos).",
    )


class PlanEntryOut(BaseModel):
    day: int
    product_id: str
    slug: str
    name: str
    score: float
    ads_verdict: str
    tested: bool
    tiktok_url: str = ""          # ficha del producto (para bajar fotos)
    presets_count: int = 0
    carousels_count: int = 0
    hooks_count: int = 0
    problem_videos_count: int = 0
    pack_ready: bool = False      # tiene algún contenido (hooks/vídeos-problema cuentan)
    ai_ready: bool = False        # tiene vídeos IA + carruseles generados


class WeekPlanOut(BaseModel):
    exists: bool
    id: str = ""
    label: str = ""
    days: int = 7
    entries: list[PlanEntryOut] = Field(default_factory=list)


@router.get("/plan", response_model=WeekPlanOut)
def get_plan(operator: Annotated[str, Depends(get_current_user)]) -> WeekPlanOut:
    """Devuelve el plan actual (calendario), enriqueciendo cada producto con
    sus prompts ya generados (presets + carruseles) en vivo desde Redis."""
    from src.tiktok_shop.repos import PlanRepo, ProductRepo

    plan = PlanRepo().get_current()
    if plan is None:
        return WeekPlanOut(exists=False)
    prepo = ProductRepo()
    # Batch: 1 roundtrip a Redis en vez de N gets (carga rápida del calendario).
    prods = prepo.get_many([e.product_id for e in plan.entries])
    out: list[PlanEntryOut] = []
    for e in plan.entries:
        prod = prods.get(e.product_id)
        n_pre = len(prod.video_presets) if prod else 0
        n_car = len(prod.carousels) if prod else 0
        n_hooks = len(prod.bofu_hooks) if prod else 0
        n_pv = len(prod.problem_videos) if prod else 0
        url = (prod.tiktok_shop.product_url or "") if prod else ""
        out.append(PlanEntryOut(
            day=e.day, product_id=e.product_id, slug=e.slug, name=e.name,
            score=e.score, ads_verdict=e.ads_verdict, tested=e.tested,
            tiktok_url=url, presets_count=n_pre, carousels_count=n_car,
            hooks_count=n_hooks, problem_videos_count=n_pv,
            pack_ready=(n_pre > 0 or n_car > 0 or n_hooks > 0 or n_pv > 0),
            ai_ready=(n_pre > 0 or n_car > 0),
        ))
    return WeekPlanOut(
        exists=True, id=plan.id, label=plan.label, days=plan.days, entries=out,
    )


def _gen_options(gens: list[str] | None, n_problem_videos: int = 3) -> dict:
    """Opciones de pack según los tipos de generación elegidos.
    gens ⊆ {"problem_videos", "bofu_hooks", "styles"}. Default: solo
    vídeos-problema (lo que el operador quiere activo ahora).

    `n_problem_videos`: cuántos conceptos por producto. El día automático usa
    1 (método del operador de 100€/día: 1 vídeo por producto, y si vende, se
    doblan los vídeos de ESE producto). Más vídeos del mismo producto no son
    apuestas nuevas — compiten por la misma bolsa de GMV Max.
    """
    gens = gens or ["problem_videos"]
    styles = "styles" in gens
    return {
        "download_photos": False,
        "photos_to_download": 0,
        "analyze": True,
        "research": False,
        "generate_video_presets": styles,
        "n_carousels": 2 if styles else 0,
        "generate_nano_banana": False,
        "generate_bofu_hooks": "bofu_hooks" in gens,
        "generate_problem_videos": "problem_videos" in gens,
        "n_problem_videos": max(1, min(5, n_problem_videos)),
    }


class AddUrlRequest(BaseModel):
    url: str
    name: str | None = None        # override si el scraper no saca nombre
    category: str | None = None
    language: str = "es_ES"
    per_day: int = _PER_DAY_DEFAULT
    # Tipos de generación a ejecutar YA: "problem_videos" | "bofu_hooks" | "styles".
    # Default vacío = NO generar al añadir (el operador elige después por producto).
    gens: list[str] = Field(default_factory=list)


def _scrape_create_product(
    url: str, name_override: str | None, category: str | None, language: str,
):
    """Scrapea la URL + crea (o reusa) el Product con foto. Devuelve
    (product | None, error_msg). No toca el plan ni genera prompts."""
    from src.tiktok_shop.config import (
        product_drive_folder,
        product_photos_generated_folder,
        product_photos_source_folder,
    )
    from src.tiktok_shop.models.product import Product, TikTokShopMeta, slugify
    from src.tiktok_shop.repos import ProductRepo
    from src.tiktok_shop.utils.url_scraper import scrape_product_url

    url = (url or "").strip()
    if not url:
        return None, "URL vacía."
    # La URL canónica (tiktok.com/view/product) la bloquea TikTok (Security
    # Check) → si ya tenemos nombre, saltamos el scrape HTTP (no da ni foto).
    is_canonical_blocked = "tiktok.com/view/product" in url
    data: dict = {}
    if not (name_override and is_canonical_blocked):
        try:
            data = scrape_product_url(url, use_gemini=False) or {}
        except Exception as e:
            data = {"warnings": str(e)}
    name = (name_override or data.get("name") or "").strip()
    if not name or name.lower() == "security check":
        return None, (
            "No pude leer el producto (TikTok bloquea la URL canónica). "
            "Añade el nombre o usa la share-URL de la app."
        )
    repo = ProductRepo()
    slug = slugify(name)
    product = repo.get_by_slug(slug)
    if product is not None:
        return product, ""
    cat = (category or data.get("category") or "otros").strip() or "otros"
    price = data.get("price_eur")
    product = Product(
        slug=slug, name=name[:200],
        brand=(data.get("brand") or None),
        category=cat, subcategory=(data.get("subcategory") or None),
        language=language, origin="manual",
        tiktok_shop=TikTokShopMeta(
            product_url=url, commission_rate=0.10,
            price_eur=float(price) if price else None,
        ),
    )
    try:
        from pathlib import Path
        Path(product_drive_folder(slug)).mkdir(parents=True, exist_ok=True)
        Path(product_photos_source_folder(slug)).mkdir(parents=True, exist_ok=True)
        Path(product_photos_generated_folder(slug)).mkdir(parents=True, exist_ok=True)
        product.drive_folder = product_drive_folder(slug)
    except OSError:
        pass
    img = data.get("image_url")
    if img:
        try:
            from src.tiktok_shop.utils.photo_downloader import download_image_to_product
            photo = download_image_to_product(
                product_slug=slug, image_url=img,
                photo_type="packshot", origin="tiktok_shop_url",
            )
            if photo is not None:
                product.photos.source.append(photo)
        except Exception:
            pass
    repo.save(product)
    return product, ""


def _queue_product(product, per_day: int) -> int:
    """Añade el product a la cola del plan (append + reflow). Devuelve el día."""
    from datetime import datetime, timezone

    from src.tiktok_shop.models.week_plan import PlanEntry, WeekPlan
    from src.tiktok_shop.repos import PlanRepo

    prepo = PlanRepo()
    plan = prepo.get_current()
    if plan is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plan = WeekPlan(label=f"Semana {date}", date=date, days=1)
    if not any(e.product_id == product.id for e in plan.entries):
        plan.entries.append(PlanEntry(
            day=10_000, product_id=product.id, slug=product.slug,
            name=product.name, score=0, ads_verdict="desconocida",
        ))
    _reflow_plan(plan, per_day)
    prepo.save(plan, make_current=True)
    return next((e.day for e in plan.entries if e.product_id == product.id), 1)


def _maybe_enqueue_gens(queue, product, gens, operator) -> str | None:
    """Encola un pack con las generaciones elegidas. None si gens vacío."""
    if not gens:
        return None
    job = queue.enqueue(
        JobMode.TIKTOK_SHOP_PACK,
        title=f"🎯 Generando: {product.name}",
        params={"product_id": product.id, "options": _gen_options(gens)},
        enqueued_by=operator or None,
    )
    return job.id


@router.post("/plan/add-url", response_model=CalendarActionResponse)
def add_url(
    body: AddUrlRequest,
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> CalendarActionResponse:
    """Añade UN producto a la cola desde su URL. Por defecto NO genera prompts
    (gens vacío) — el operador elige después qué generar por producto."""
    product, err = _scrape_create_product(body.url, body.name, body.category, body.language)
    if product is None:
        return CalendarActionResponse(ok=False, message=err)
    landed = _queue_product(product, body.per_day)
    job_id = _maybe_enqueue_gens(queue, product, body.gens, operator)
    tail = " Generando prompts…" if job_id else ""
    return CalendarActionResponse(
        ok=True, product_id=product.id, slug=product.slug, job_id=job_id,
        message=f"'{product.name}' añadido al día {landed} (cola).{tail}",
    )


class AddBatchRequest(BaseModel):
    # Texto multilínea: un producto por línea, "nombre — url" (o "url — nombre",
    # o solo url). Se parsea la URL y el resto es el nombre.
    raw: str
    per_day: int = _PER_DAY_DEFAULT
    language: str = "es_ES"
    gens: list[str] = Field(default_factory=list)


class BatchItemResult(BaseModel):
    line: str
    ok: bool
    name: str = ""
    day: int = 0
    message: str = ""


class AddBatchResponse(BaseModel):
    ok: bool
    added: int
    failed: int
    results: list[BatchItemResult] = Field(default_factory=list)


def _parse_batch_line(line: str) -> tuple[str, str]:
    """Extrae (url, name) de una línea flexible. La URL es el primer token
    http(s); el resto (sin separadores) es el nombre."""
    import re

    m = re.search(r"https?://\S+", line)
    if not m:
        return "", ""
    url = m.group(0).rstrip(".,;")
    name = (line[: m.start()] + " " + line[m.end():]).strip()
    name = name.strip(" —–-:|\t").strip()
    return url, name


@router.post("/plan/add-batch", response_model=AddBatchResponse)
def add_batch(
    body: AddBatchRequest,
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> AddBatchResponse:
    """Añade VARIOS productos a la cola de golpe (uno por línea), en orden.
    Por defecto NO genera prompts — se eligen después por producto."""
    lines = [ln.strip() for ln in (body.raw or "").splitlines() if ln.strip()]
    results: list[BatchItemResult] = []
    added = 0
    for ln in lines:
        url, name = _parse_batch_line(ln)
        if not url:
            results.append(BatchItemResult(line=ln, ok=False, message="Sin URL en la línea."))
            continue
        product, err = _scrape_create_product(url, name or None, None, body.language)
        if product is None:
            results.append(BatchItemResult(line=ln, ok=False, message=err))
            continue
        day = _queue_product(product, body.per_day)
        _maybe_enqueue_gens(queue, product, body.gens, operator)
        added += 1
        results.append(BatchItemResult(line=ln, ok=True, name=product.name, day=day))
    return AddBatchResponse(
        ok=added > 0, added=added, failed=len(results) - added, results=results,
    )


class PlanPackRequest(BaseModel):
    product_id: str
    research: bool = False
    n_carousels: int = 2
    n_photos: int = 4


@router.post("/plan/pack", response_model=CalendarActionResponse)
def plan_pack(
    body: PlanPackRequest,
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> CalendarActionResponse:
    """Re-encola el pack de un producto que YA está en el calendario pero
    quedó sin generar (sin candidato en DiscoveryRepo — usa el Product)."""
    from src.tiktok_shop.repos import ProductRepo

    product = ProductRepo().get(body.product_id)
    if product is None:
        return CalendarActionResponse(ok=False, message="Producto no encontrado.")
    job = queue.enqueue(
        JobMode.TIKTOK_SHOP_PACK,
        title=f"📦 Pack: {product.name}",
        params={
            "product_id": product.id,
            "options": _pack_options(body.research, body.n_carousels, body.n_photos),
        },
        enqueued_by=operator or None,
    )
    return CalendarActionResponse(
        ok=True, product_id=product.id, slug=product.slug, job_id=job.id,
        message=f"Generando pack de '{product.name}'…",
    )


class MarkTestedRequest(BaseModel):
    product_id: str
    tested: bool = True


@router.post("/plan/tested")
def mark_tested(
    body: MarkTestedRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> dict[str, bool]:
    from src.tiktok_shop.repos import PlanRepo

    repo = PlanRepo()
    plan = repo.get_current()
    if plan is None:
        return {"ok": False}
    changed = False
    for e in plan.entries:
        if e.product_id == body.product_id:
            e.tested = body.tested
            changed = True
    if changed:
        repo.save(plan, make_current=False)
    return {"ok": changed}


class RegenCarouselsRequest(BaseModel):
    product_id: str
    language: str = "es"          # "es" | "en"
    text_style: str | None = None  # "simple" | "box" | "outline" | None (auto)
    n_carousels: int = 2
    n_slides: int = 6


@router.post("/carousels/regenerate")
def regenerate_carousels(
    body: RegenCarouselsRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Regenera los carruseles de un producto en el idioma elegido (es/en)
    con el prompt mejorado (texto renderizado en la imagen, sin hashtags).
    Síncrono: solo Gemini (~10-15s/carrusel)."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.pipeline.carousel_director import generate_carousel
    from src.tiktok_shop.repos import ProductRepo

    repo = ProductRepo()
    product = repo.get(body.product_id)
    if product is None:
        return {"ok": False, "message": "Producto no encontrado."}

    n = max(1, min(6, body.n_carousels))
    start_job(
        job_id=f"carousel_{uuid.uuid4().hex[:10]}",
        program="tiktok_shop", mode="product_discovery",
        title=f"Carruseles {body.language}: {product.name}", user=operator or None,
    )
    carousels = []
    try:
        for _ in range(n):
            data = generate_carousel(
                product, n_slides=body.n_slides, language=body.language,
                text_style=body.text_style,
            )
            if data and data.get("slides"):
                carousels.append(data)
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass

    if carousels:
        product.carousels = carousels
        product.touch()
        repo.save(product)
    return {"ok": bool(carousels), "count": len(carousels), "language": body.language}


class RemoveEntryRequest(BaseModel):
    product_id: str


@router.post("/plan/remove")
def remove_from_plan(
    body: RemoveEntryRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Quita un producto del calendario (no borra el producto del catálogo,
    solo lo saca del plan). Para curar productos malos (agotados, fuera de
    temporada, etc.)."""
    from src.tiktok_shop.repos import PlanRepo

    repo = PlanRepo()
    plan = repo.get_current()
    if plan is None:
        return {"ok": False, "removed": 0}
    before = len(plan.entries)
    plan.entries = [e for e in plan.entries if e.product_id != body.product_id]
    removed = before - len(plan.entries)
    if removed:
        # Recompacta la cola: los productos de días posteriores suben.
        _reflow_plan(plan)
        repo.save(plan, make_current=False)
    return {"ok": removed > 0, "removed": removed}


class RemoveBatchRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    day: int | None = None   # si se pasa, borra TODO ese día (además de ids)


@router.post("/plan/remove-batch")
def remove_batch_from_plan(
    body: RemoveBatchRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Quita VARIOS productos del calendario de golpe (por ids y/o día entero)
    + 1 solo reflow + 1 solo guardado → rápido."""
    from src.tiktok_shop.repos import PlanRepo

    repo = PlanRepo()
    plan = repo.get_current()
    if plan is None:
        return {"ok": False, "removed": 0}
    ids = set(body.product_ids or [])
    before = len(plan.entries)
    plan.entries = [
        e for e in plan.entries
        if e.product_id not in ids and (body.day is None or e.day != body.day)
    ]
    removed = before - len(plan.entries)
    if removed:
        _reflow_plan(plan)
        repo.save(plan, make_current=False)
    return {"ok": removed > 0, "removed": removed}


@router.delete("/plan")
def delete_plan(operator: Annotated[str, Depends(get_current_user)]) -> dict[str, bool]:
    from src.tiktok_shop.repos import PlanRepo

    repo = PlanRepo()
    plan = repo.get_current()
    if plan is None:
        return {"ok": False}
    return {"ok": repo.delete(plan.id)}


class BofuHooksRequest(BaseModel):
    product_id: str
    language: str = "es"
    n: int = 10


@router.post("/hooks/bofu")
def bofu_hooks(
    body: BofuHooksRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Genera hooks BOFU simples (nombre del producto + empujón a la venta)
    para A/B testear. Texto en pantalla / opener del caption."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.repos import ProductRepo
    from src.tiktok_shop.services.hooks_generator import generate_bofu_hooks

    product = ProductRepo().get(body.product_id)
    if product is None:
        return {"ok": False, "hooks": [], "message": "Producto no encontrado."}
    start_job(
        job_id=f"bofuhooks_{uuid.uuid4().hex[:8]}",
        program="tiktok_shop", mode="product_discovery",
        title=f"Hooks BOFU: {product.name}", user=operator or None,
    )
    try:
        res = generate_bofu_hooks(product, n=body.n, language=body.language)
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass
    # Persistir en el producto para verlos siempre en el calendario.
    if res.get("hooks"):
        product.bofu_hooks = res["hooks"]
        product.touch()
        ProductRepo().save(product)
    return {"ok": True, **res}


class ProblemVideosRequest(BaseModel):
    product_id: str
    language: str = "es"
    n: int = 3


@router.post("/videos/problem")
def problem_videos(
    body: ProblemVideosRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Genera 2-3 conceptos de vídeo que atacan el PROBLEMA del cliente
    (MOFU/TOFU) listos para Veo 3: prompt + textos en pantalla + ángulo."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.repos import ProductRepo
    from src.tiktok_shop.services.problem_video_generator import (
        generate_problem_videos,
    )

    product = ProductRepo().get(body.product_id)
    if product is None:
        return {"ok": False, "videos": [], "message": "Producto no encontrado."}
    start_job(
        job_id=f"probvid_{uuid.uuid4().hex[:8]}",
        program="tiktok_shop", mode="product_discovery",
        title=f"Vídeos-problema: {product.name}", user=operator or None,
    )
    try:
        res = generate_problem_videos(product, n=body.n, language=body.language)
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass
    if res.get("videos"):
        product.problem_videos = res["videos"]
        product.problem_analysis = {
            "ideal_customer": res.get("ideal_customer", {}),
            "sale": res.get("sale", {}),
        }
        product.touch()
        ProductRepo().save(product)
    return {"ok": True, **res}


def _ready_dir(slug: str) -> str:
    from src.tiktok_shop.config import product_drive_folder
    return os.path.join(product_drive_folder(slug), "videos_ready")


@router.post("/videos/problem/upload")
def upload_problem_video(
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
    file: Annotated[UploadFile, File()],
    product_id: Annotated[str, Form()],
    concept_index: Annotated[int, Form()],
    zoom: Annotated[float, Form()] = 1.18,
) -> dict:
    """Sube el vídeo generado (Flow/Kling) de UN concepto → guarda el original
    y ENCOLA el procesado (zoom quita-marca + gancho + CTA + flecha). El
    resultado y cualquier error se ven en la Cola."""
    import shutil

    from src.tiktok_shop.repos import ProductRepo

    product = ProductRepo().get(product_id)
    if product is None or concept_index < 0 or concept_index >= len(product.problem_videos):
        return {"ok": False, "message": "Producto o concepto no encontrado."}

    ready_dir = _ready_dir(product.slug)
    os.makedirs(ready_dir, exist_ok=True)
    raw_path = os.path.join(ready_dir, f"concept_{concept_index}_raw.mp4")
    try:
        with open(raw_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        return {"ok": False, "message": f"Error guardando el vídeo: {e}"}

    job = queue.enqueue(
        JobMode.TIKTOK_SHOP_READY_VIDEO,
        title=f"🎬 Vídeo listo: {product.name} · v{concept_index + 1}",
        params={
            "product_id": product.id, "concept_index": concept_index,
            "raw_path": raw_path, "zoom": zoom,
        },
        enqueued_by=operator or None,
    )
    return {"ok": True, "job_id": job.id, "message": "En la cola, procesando…"}


@router.get("/videos/problem/ready")
def download_ready_video(
    product_id: str,
    concept_index: int,
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
):
    """Descarga el vídeo procesado (listo para subir a TikTok). Auth por
    query `api_key` (como las fotos) porque va en un <a href> que no manda
    headers."""
    from fastapi import HTTPException

    from src.api.config import get_settings
    from src.tiktok_shop.repos import ProductRepo

    settings = get_settings()
    if settings.api_key:
        provided = x_api_key or api_key
        if not provided or provided != settings.api_key:
            raise HTTPException(status_code=401, detail="API key inválida o ausente.")

    product = ProductRepo().get(product_id)
    if product is None:
        return {"ok": False, "message": "Producto no encontrado."}
    # Nombre único guardado en el concepto (producto_vN_fecha.mp4); fallback al
    # nombre antiguo por compatibilidad.
    fname = None
    if 0 <= concept_index < len(product.problem_videos):
        fname = (product.problem_videos[concept_index] or {}).get("ready_video")
    fname = fname or f"concept_{concept_index}.mp4"
    path = os.path.join(_ready_dir(product.slug), fname)
    if not os.path.exists(path):
        return {"ok": False, "message": "Aún no procesado."}
    return FileResponse(path, media_type="video/mp4", filename=fname)


@router.get("/video-templates")
def video_templates(
    operator: Annotated[str, Depends(get_current_user)],
    product_id: str = Query(default=""),
) -> dict:
    """Plantillas de vídeo reutilizables (sin coste IA). Si se pasa
    `product_id`, devuelve el prompt ya rellenado con el nombre del producto
    y filtra por su categoría/nicho; si no, todas con el placeholder {product}."""
    from src.tiktok_shop import video_templates as vt
    from src.tiktok_shop.repos import ProductRepo

    product = ProductRepo().get(product_id) if product_id else None
    niche = None
    name = ""
    if product is not None:
        niche = f"{product.category} {product.subcategory or ''} {product.name}"
        name = product.name
    tpls = vt.templates_for_niche(niche)
    return {
        "product_name": name,
        "templates": [
            {
                "id": t["id"],
                "name": t["name"],
                "niches": t["niches"],
                "notes": t["notes"],
                "prompt": vt.render_template(t["prompt"], name) if name else t["prompt"],
                "first_frame_prompt": vt.render_first_frame(t, name),
                "kling_prompt": vt.render_kling(t, name),
            }
            for t in tpls
        ],
    }


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
