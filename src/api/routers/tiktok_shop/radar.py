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
    pack_ready: bool = False      # tiene algún contenido (hooks ya cuenta)
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
    out: list[PlanEntryOut] = []
    for e in plan.entries:
        prod = prepo.get(e.product_id)
        n_pre = len(prod.video_presets) if prod else 0
        n_car = len(prod.carousels) if prod else 0
        n_hooks = len(prod.bofu_hooks) if prod else 0
        url = (prod.tiktok_shop.product_url or "") if prod else ""
        out.append(PlanEntryOut(
            day=e.day, product_id=e.product_id, slug=e.slug, name=e.name,
            score=e.score, ads_verdict=e.ads_verdict, tested=e.tested,
            tiktok_url=url, presets_count=n_pre, carousels_count=n_car,
            hooks_count=n_hooks,
            pack_ready=(n_pre > 0 or n_car > 0 or n_hooks > 0),
            ai_ready=(n_pre > 0 or n_car > 0),
        ))
    return WeekPlanOut(
        exists=True, id=plan.id, label=plan.label, days=plan.days, entries=out,
    )


class AddUrlRequest(BaseModel):
    url: str
    name: str | None = None        # override si el scraper no saca nombre
    category: str | None = None
    language: str = "es_ES"
    per_day: int = _PER_DAY_DEFAULT


@router.post("/plan/add-url", response_model=CalendarActionResponse)
def add_url(
    body: AddUrlRequest,
    operator: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> CalendarActionResponse:
    """Añade un producto a la COLA del calendario desde su URL de TikTok Shop.

    Scrapea nombre+foto de la URL (share-URL de la app), crea el producto,
    lo coloca en el primer hueco libre (per_day) recompactando la cola, y
    encola un pack LIGERO (solo hooks BOFU; las plantillas son estáticas)."""
    from src.tiktok_shop.config import (
        product_drive_folder,
        product_photos_generated_folder,
        product_photos_source_folder,
    )
    from src.tiktok_shop.models.product import Product, TikTokShopMeta, slugify
    from src.tiktok_shop.models.week_plan import PlanEntry, WeekPlan
    from src.tiktok_shop.repos import PlanRepo, ProductRepo
    from src.tiktok_shop.utils.url_scraper import scrape_product_url

    url = (body.url or "").strip()
    if not url:
        return CalendarActionResponse(ok=False, message="Pega una URL de TikTok Shop.")

    # 1) Scrape (share-URL de la app trae name+image vía og_info) ─────────
    data: dict = {}
    try:
        data = scrape_product_url(url, use_gemini=False) or {}
    except Exception as e:  # nunca debería, scrape es defensivo
        data = {"warnings": str(e)}

    name = (body.name or data.get("name") or "").strip()
    if not name or name.lower() == "security check":
        return CalendarActionResponse(
            ok=False,
            message=(
                "No pude leer el producto de esa URL (TikTok la bloquea). "
                "Usa la share-URL del botón Compartir de la app de TikTok, "
                "o añade el nombre a mano."
            ),
        )

    repo = ProductRepo()
    slug = slugify(name)
    product = repo.get_by_slug(slug)
    if product is None:
        category = (body.category or data.get("category") or "otros").strip() or "otros"
        price = data.get("price_eur")
        product = Product(
            slug=slug, name=name[:200],
            brand=(data.get("brand") or None),
            category=category, subcategory=(data.get("subcategory") or None),
            language=body.language, origin="manual",
            tiktok_shop=TikTokShopMeta(
                product_url=url, commission_rate=0.10,
                price_eur=float(price) if price else None,
            ),
        )
        # Carpetas + foto de la URL (best-effort, no aborta) ──────────────
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
                from src.tiktok_shop.utils.photo_downloader import (
                    download_image_to_product,
                )
                photo = download_image_to_product(
                    product_slug=slug, image_url=img,
                    photo_type="packshot", origin="tiktok_shop_url",
                )
                if photo is not None:
                    product.photos.source.append(photo)
            except Exception:
                pass
        repo.save(product)

    # 2) Colocar en la cola (append + reflow) ─────────────────────────────
    prepo = PlanRepo()
    plan = prepo.get_current()
    if plan is None:
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plan = WeekPlan(label=f"Semana {date}", date=date, days=1)
    if not any(e.product_id == product.id for e in plan.entries):
        plan.entries.append(PlanEntry(
            day=10_000, product_id=product.id, slug=product.slug,
            name=product.name, score=0, ads_verdict="desconocida",
        ))
    _reflow_plan(plan, body.per_day)
    prepo.save(plan, make_current=True)
    landed = next((e.day for e in plan.entries if e.product_id == product.id), 1)

    # 3) Pack LIGERO en background (solo hooks BOFU) ──────────────────────
    job = queue.enqueue(
        JobMode.TIKTOK_SHOP_PACK,
        title=f"🎣 Hooks: {product.name}",
        params={"product_id": product.id, "options": _light_pack_options()},
        enqueued_by=operator or None,
    )
    return CalendarActionResponse(
        ok=True, product_id=product.id, slug=product.slug, job_id=job.id,
        message=f"'{product.name}' añadido al día {landed} (cola). Generando hooks…",
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
