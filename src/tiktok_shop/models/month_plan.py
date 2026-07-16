"""Calendario real por FECHAS + resultado de cada vídeo.

## Por qué sustituye a `week_plan`

`WeekPlan` numeraba los días 1..N dentro de un plan "actual". Eso no es un
calendario: no sabes si el día 3 fue el 17 de julio o el 2 de agosto, y todo
el histórico vive en una sola clave que crece sin fin.

Aquí cada mes es su propio documento (`plan:month:2026-07`):
  - Cargar julio NO lee junio → el calendario no se degrada con el histórico.
  - Cada mes está acotado (~30 días × N productos).

## Por qué el formato ganador se guarda AQUÍ y no se mira en el Product

`sold_format` está DENORMALIZADO a propósito. La alternativa —guardar solo
`sold_version=2` e ir al Product a preguntar qué formato era esa versión—
tiene dos fallos: obligaría a leer N productos para pintar estadísticas (lento
justo cuando hay histórico, que es cuando sirven), y se rompería al regenerar
los prompts (los índices cambian → el histórico mentiría). Guardando la
cadena en el momento de marcar, las estadísticas se calculan leyendo solo
meses, y el pasado queda congelado aunque el producto cambie.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    """Fecha de hoy (UTC) en YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def month_of(date_iso: str) -> str:
    """'2026-07-15' → '2026-07'."""
    return (date_iso or "")[:7]


class DayEntry(BaseModel):
    """Un producto asignado a un DÍA CONCRETO, con lo que pasó al probarlo."""

    date: str                       # "2026-07-15"
    product_id: str
    slug: str = ""
    name: str = ""

    # Del Radar, congelado al añadirlo (por qué se eligió ese día).
    score: float = 0.0
    ads_verdict: str = ""
    influencer_count: int = 0
    commission_eur: float = 0.0
    # La URL canónica de TikTok está bloqueada → el operador busca por nombre
    # en el Centro de Afiliados y necesita la tienda para saber cuál es.
    seller_name: str = ""

    # ── Resultado (lo marca el operador) ─────────────────────────────
    uploaded: bool = False          # ¿llegué a subir el vídeo?
    sold: bool = False              # ¿vendió?
    sold_version: int | None = None  # índice del vídeo-problema que vendió
    sold_format: str = ""           # DENORMALIZADO — ver docstring del módulo
    revenue_eur: float = 0.0        # GMV o comisión, lo que el operador anote
    note: str = ""

    added_at: str = Field(default_factory=_now_iso)


class MonthPlan(BaseModel):
    """Todos los productos de un mes. 1 documento = 1 lectura de Redis."""

    month: str                      # "2026-07"
    region: str = "ES"
    entries: list[DayEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()

    def by_date(self) -> dict[str, list[DayEntry]]:
        out: dict[str, list[DayEntry]] = {}
        for e in self.entries:
            out.setdefault(e.date, []).append(e)
        return out

    def stats(self) -> dict:
        """Resumen del mes. Solo lee entradas — nunca toca productos."""
        total = len(self.entries)
        uploaded = sum(1 for e in self.entries if e.uploaded)
        sold = sum(1 for e in self.entries if e.sold)
        revenue = sum(e.revenue_eur for e in self.entries)
        by_format: dict[str, dict[str, int]] = {}
        for e in self.entries:
            if not e.sold or not e.sold_format:
                continue
            by_format.setdefault(e.sold_format, {"sold": 0})["sold"] += 1
        return {
            "month": self.month,
            "products": total,
            "uploaded": uploaded,
            "sold": sold,
            "revenue_eur": round(revenue, 2),
            "conversion_pct": round(sold / uploaded * 100, 1) if uploaded else 0.0,
            "by_format": by_format,
        }
