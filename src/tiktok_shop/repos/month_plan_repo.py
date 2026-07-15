"""CRUD del calendario por meses. `plan:month:<YYYY-MM>` + índice de meses.

Un documento por mes: cargar julio no lee junio. Es lo que evita que el
calendario se degrade a medida que se acumula histórico — el coste de abrir
un mes no depende de cuántos meses lleves.
"""

from __future__ import annotations

from src.tiktok_shop.models.month_plan import DayEntry, MonthPlan, month_of

from .redis_base import ShopRedis, get_shop_redis


class MonthPlanRepo:
    INDEX_KEY = "plan:months"          # set de "2026-07"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(month: str) -> str:
        return f"plan:month:{month}"

    def save(self, plan: MonthPlan) -> MonthPlan:
        plan.touch()
        self.r.set_json(self._key(plan.month), plan.model_dump())
        self.r.sadd(self.INDEX_KEY, plan.month)
        return plan

    def get(self, month: str) -> MonthPlan | None:
        data = self.r.get_json(self._key(month))
        if not data:
            return None
        try:
            return MonthPlan.model_validate(data)
        except Exception as e:  # noqa: BLE001
            print(f"[MonthPlanRepo] decode error {month}: {e}")
            return None

    def get_or_create(self, month: str) -> MonthPlan:
        return self.get(month) or MonthPlan(month=month)

    def months(self) -> list[str]:
        """Meses con datos, del más reciente al más antiguo."""
        return sorted(self.r.smembers(self.INDEX_KEY) or [], reverse=True)

    def add_entry(self, entry: DayEntry) -> MonthPlan:
        """Añade (o reemplaza) un producto en su día. Idempotente por
        (date, product_id) → re-lanzar el día automático no duplica."""
        plan = self.get_or_create(month_of(entry.date))
        plan.entries = [
            e for e in plan.entries
            if not (e.date == entry.date and e.product_id == entry.product_id)
        ]
        plan.entries.append(entry)
        return self.save(plan)

    def update_entry(self, date: str, product_id: str, **fields) -> DayEntry | None:
        """Marca resultado (uploaded/sold/sold_version/...). None si no existe."""
        plan = self.get(month_of(date))
        if plan is None:
            return None
        for e in plan.entries:
            if e.date == date and e.product_id == product_id:
                for k, v in fields.items():
                    if v is not None and hasattr(e, k):
                        setattr(e, k, v)
                self.save(plan)
                return e
        return None

    def remove_entries(
        self, *, date: str | None = None, product_ids: list[str] | None = None,
        month: str | None = None,
    ) -> int:
        """Borra por día entero y/o por productos concretos."""
        target = month or (month_of(date) if date else None)
        if not target:
            return 0
        plan = self.get(target)
        if plan is None:
            return 0
        ids = set(product_ids or [])
        before = len(plan.entries)
        plan.entries = [
            e for e in plan.entries
            if not ((date is None or e.date == date) and (not ids or e.product_id in ids))
        ]
        removed = before - len(plan.entries)
        if removed:
            self.save(plan)
        return removed

    def stats(self, months: list[str] | None = None) -> dict:
        """Agrega estadísticas de varios meses en 1 roundtrip (mget).

        Solo lee documentos de mes — nunca productos. Por eso escala: da igual
        cuántos productos haya, el coste es 1 lectura por mes.
        """
        ms = months or self.months()
        if not ms:
            return {"months": [], "products": 0, "uploaded": 0, "sold": 0,
                    "revenue_eur": 0.0, "conversion_pct": 0.0, "by_format": {}}
        raws = self.r.mget_json([self._key(m) for m in ms])
        totals = {"products": 0, "uploaded": 0, "sold": 0, "revenue_eur": 0.0}
        by_format: dict[str, dict[str, int]] = {}
        per_month: list[dict] = []
        for data in raws:
            if not data:
                continue
            try:
                plan = MonthPlan.model_validate(data)
            except Exception:  # noqa: BLE001
                continue
            s = plan.stats()
            per_month.append(s)
            for k in ("products", "uploaded", "sold"):
                totals[k] += s[k]
            totals["revenue_eur"] += s["revenue_eur"]
            for fmt, v in s["by_format"].items():
                by_format.setdefault(fmt, {"sold": 0})["sold"] += v["sold"]
        conv = (totals["sold"] / totals["uploaded"] * 100) if totals["uploaded"] else 0.0
        return {
            "months": sorted(ms, reverse=True),
            "per_month": sorted(per_month, key=lambda s: s["month"], reverse=True),
            "products": totals["products"],
            "uploaded": totals["uploaded"],
            "sold": totals["sold"],
            "revenue_eur": round(totals["revenue_eur"], 2),
            "conversion_pct": round(conv, 1),
            "by_format": dict(sorted(by_format.items(), key=lambda kv: -kv[1]["sold"])),
        }
