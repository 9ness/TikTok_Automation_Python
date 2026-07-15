#!/usr/bin/env python
"""Migra el WeekPlan (día 1..N) al calendario por fechas reales.

El plan viejo numeraba los días 1,2,3… sin saber a qué fecha correspondían.
Al migrar hay que ELEGIR una fecha, y la elección es una convención: el día 1
es HOY, el día 2 mañana, etc. No hay forma de recuperar la fecha real de los
días pasados porque nunca se guardó — así que no se inventa histórico: se
coloca el plan pendiente de hoy en adelante.

El WeekPlan viejo NO se borra (queda como respaldo por si algo sale mal).

Uso:
    python scripts/migrate_plan_to_months.py            # ENSAYO (no escribe)
    python scripts/migrate_plan_to_months.py --apply    # escribe de verdad
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for candidate in (
    os.path.expanduser("~/TikTok_Automation_Python/.env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
):
    if os.path.exists(candidate):
        load_dotenv(candidate)
        break

from src.tiktok_shop.models.month_plan import DayEntry, month_of  # noqa: E402
from src.tiktok_shop.repos import PlanRepo  # noqa: E402
from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo  # noqa: E402

APPLY = "--apply" in sys.argv


def main() -> int:
    old = PlanRepo().get_current()
    if old is None:
        print("no hay WeekPlan actual — nada que migrar")
        return 0

    base = datetime.now(timezone.utc).date()
    print(f"WeekPlan {old.label!r} (id={old.id}) · {len(old.entries)} entradas")
    print(f"convención: día 1 = {base.isoformat()} (hoy), día 2 = mañana, …\n")

    repo = MonthPlanRepo()
    plans: dict[str, list[DayEntry]] = {}
    for e in old.entries:
        date = (base + timedelta(days=max(1, e.day) - 1)).isoformat()
        entry = DayEntry(
            date=date, product_id=e.product_id, slug=e.slug, name=e.name,
            score=e.score, ads_verdict=e.ads_verdict,
            # `tested` del modelo viejo significaba "lo subí" → uploaded.
            # No se puede inferir si vendió: eso no se guardaba.
            uploaded=bool(e.tested), note=e.note or "",
        )
        plans.setdefault(month_of(date), []).append(entry)

    for month, entries in sorted(plans.items()):
        by_date: dict[str, int] = {}
        for e in entries:
            by_date[e.date] = by_date.get(e.date, 0) + 1
        print(f"  {month}: {len(entries)} entradas → {dict(sorted(by_date.items()))}")

    if not APPLY:
        print("\n🔎 ENSAYO — no se ha escrito nada. Relanza con --apply.")
        return 0

    for month, entries in plans.items():
        plan = repo.get_or_create(month)
        existing = {(e.date, e.product_id) for e in plan.entries}
        plan.entries.extend(e for e in entries if (e.date, e.product_id) not in existing)
        repo.save(plan)
        print(f"  ✓ guardado {month} ({len(plan.entries)} entradas)")
    print(f"\n✅ migrado. El WeekPlan viejo ({old.id}) sigue intacto como respaldo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
