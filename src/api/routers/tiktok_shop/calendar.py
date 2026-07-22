"""Calendario por FECHAS reales + resultados + estadísticas.

## La regla que hace que esto escale

**La vista de MES no lee productos.** Devuelve solo lo que ya está en la
entrada (fecha, nombre, subido, vendido). Con 200 productos/mes eso es 1
lectura de Redis, cueste lo que cueste el histórico.

**La vista de DÍA sí los lee** (prompts, fotos, contadores), pero un día son
~6-20 productos → acotado.

Si algún día alguien mete el enriquecimiento en `/months` o `/month`, el
calendario volverá a arrastrarse en cuanto haya un par de meses. Era el
problema del `/radar/plan` viejo, que enriquecía TODAS las entradas.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user

router = APIRouter(
    prefix="/api/v1/tiktok-shop/calendar",
    tags=["tiktok-shop · calendario"],
    dependencies=[Depends(get_current_user)],
)


# ── Schemas ──────────────────────────────────────────────────────────
class DayEntryOut(BaseModel):
    date: str
    product_id: str
    slug: str = ""
    name: str = ""
    score: float = 0.0
    ads_verdict: str = ""
    influencer_count: int = 0
    commission_eur: float = 0.0
    seller_name: str = ""
    uploaded: bool = False
    sold: bool = False
    sold_version: int | None = None
    sold_format: str = ""
    revenue_eur: float = 0.0
    note: str = ""


class DayEntryDetailOut(DayEntryOut):
    """Solo para la vista de UN día — lee el Product (más caro)."""
    problem_videos_count: int = 0
    presets_count: int = 0
    carousels_count: int = 0
    hooks_count: int = 0
    pack_ready: bool = False
    # URL canónica de TikTok Shop (shop/pdp/<id>). La bloquea a bots (Security
    # Check) pero SÍ abre en la app del operador — verificado. Vacía si no hay
    # product_id de TikTok.
    product_url: str = ""


class MonthOut(BaseModel):
    month: str
    exists: bool = True
    entries: list[DayEntryOut] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class OutcomeRequest(BaseModel):
    """Marcar qué pasó con un producto. Todo opcional → parche parcial."""
    date: str
    product_id: str
    uploaded: bool | None = None
    sold: bool | None = None
    sold_version: int | None = None   # índice del vídeo-problema que vendió
    revenue_eur: float | None = None
    note: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────
@router.get("/months", response_model=list[str])
def list_months(operator: Annotated[str, Depends(get_current_user)]) -> list[str]:
    """Meses con datos, del más reciente al más antiguo. 1 lectura."""
    from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo

    return MonthPlanRepo().months()


@router.get("/month/{month}", response_model=MonthOut)
def get_month(
    month: str,
    operator: Annotated[str, Depends(get_current_user)],
) -> MonthOut:
    """Un mes entero (YYYY-MM). NO lee productos — ver docstring del módulo."""
    from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo

    plan = MonthPlanRepo().get(month)
    if plan is None:
        return MonthOut(month=month, exists=False, stats={})
    return MonthOut(
        month=month, exists=True,
        entries=[DayEntryOut(**e.model_dump()) for e in plan.entries],
        stats=plan.stats(),
    )


@router.get("/day/{date}", response_model=list[DayEntryDetailOut])
def get_day(
    date: str,
    operator: Annotated[str, Depends(get_current_user)],
) -> list[DayEntryDetailOut]:
    """Los productos de UN día, enriquecidos con lo que tiene generado.
    Aquí sí se leen los productos: un día son pocos (batch, 1 roundtrip)."""
    from src.tiktok_shop.models.month_plan import month_of
    from src.tiktok_shop.repos import ProductRepo
    from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo

    plan = MonthPlanRepo().get(month_of(date))
    if plan is None:
        return []
    entries = [e for e in plan.entries if e.date == date]
    if not entries:
        return []
    prods = ProductRepo().get_many([e.product_id for e in entries])
    out: list[DayEntryDetailOut] = []
    for e in entries:
        p = prods.get(e.product_id)
        n_pv = len(getattr(p, "problem_videos", []) or []) if p else 0
        n_pre = len(p.video_presets) if p else 0
        n_car = len(p.carousels) if p else 0
        n_hooks = len(getattr(p, "bofu_hooks", []) or []) if p else 0
        tid = (getattr(getattr(p, "tiktok_shop", None), "product_id", "") or "") if p else ""
        url = f"https://www.tiktok.com/shop/pdp/{tid}" if tid else ""
        out.append(DayEntryDetailOut(
            **e.model_dump(),
            problem_videos_count=n_pv, presets_count=n_pre,
            carousels_count=n_car, hooks_count=n_hooks,
            pack_ready=bool(n_pv or n_pre or n_car or n_hooks),
            product_url=url,
        ))
    return out


@router.post("/outcome", response_model=DayEntryOut)
def set_outcome(
    body: OutcomeRequest,
    operator: Annotated[str, Depends(get_current_user)],
) -> DayEntryOut:
    """Marca qué pasó: subido / vendió / qué versión vendió / cuánto.

    Si viene `sold_version`, resolvemos el FORMATO de esa versión y lo
    guardamos en la entrada. Es lo que permite luego decir "dramatización
    vende 7 veces más que POV" sin leer productos — y deja el histórico
    congelado aunque se regeneren los prompts (los índices cambiarían).
    """
    from src.tiktok_shop.repos import ProductRepo
    from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo

    fields: dict = {
        "uploaded": body.uploaded, "sold": body.sold,
        "revenue_eur": body.revenue_eur, "note": body.note,
    }
    if body.sold_version is not None:
        fields["sold_version"] = body.sold_version
        prod = ProductRepo().get(body.product_id)
        pvs = (getattr(prod, "problem_videos", []) or []) if prod else []
        if 0 <= body.sold_version < len(pvs):
            pv = pvs[body.sold_version]
            fields["sold_format"] = str(pv.get("format") or pv.get("concept") or "")
        # Marcar una versión implica que vendió (salvo que digan lo contrario).
        if body.sold is None:
            fields["sold"] = True

    entry = MonthPlanRepo().update_entry(body.date, body.product_id, **fields)
    if entry is None:
        # No reventamos: el front muestra el error y el operador reintenta.
        return DayEntryOut(date=body.date, product_id=body.product_id,
                           note="no encontrado en el calendario")
    return DayEntryOut(**entry.model_dump())


@router.get("/stats")
def stats(
    operator: Annotated[str, Depends(get_current_user)],
    months: Annotated[str | None, Query(description="CSV: 2026-07,2026-06")] = None,
) -> dict:
    """Estadísticas agregadas. Solo lee documentos de mes (1 mget)."""
    from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo

    ms = [m.strip() for m in months.split(",")] if months else None
    return MonthPlanRepo().stats(ms)


@router.delete("/entries")
def remove_entries(
    operator: Annotated[str, Depends(get_current_user)],
    date: Annotated[str | None, Query()] = None,
    month: Annotated[str | None, Query()] = None,
    product_ids: Annotated[str | None, Query(description="CSV")] = None,
) -> dict[str, int]:
    """Borra un día entero, o productos concretos de un día."""
    from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo

    ids = [p.strip() for p in product_ids.split(",")] if product_ids else None
    return {"removed": MonthPlanRepo().remove_entries(
        date=date, month=month, product_ids=ids,
    )}
