"""Modelo del Plan Semanal — calendario de productos a probar por día.

Lo genera `creation_pack.plan_week` y lo renderiza el calendario del Radar
(`ui/tab_radar.py` → sub-tab 📅 Calendario). Cada `PlanEntry` es un producto
asignado a un día (1..N), con su score y un flag `tested` que el operador
marca cuando lo sube.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanEntry(BaseModel):
    day: int                       # 1..days
    product_id: str
    slug: str
    name: str
    score: float = 0.0
    ads_verdict: str = ""
    carousels: int = 0
    presets: int = 0
    tested: bool = False           # el operador lo marca al subirlo
    note: str = ""


class WeekPlan(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    label: str = ""                # ej. "Semana 2026-06-15"
    date: str = ""                 # YYYY-MM-DD de creación
    days: int = 7
    region: str = "ES"
    entries: list[PlanEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()

    def by_day(self) -> dict[int, list[PlanEntry]]:
        out: dict[int, list[PlanEntry]] = {}
        for e in self.entries:
            out.setdefault(e.day, []).append(e)
        return out

    def progress(self) -> tuple[int, int]:
        """(probados, total)."""
        done = sum(1 for e in self.entries if e.tested)
        return done, len(self.entries)
