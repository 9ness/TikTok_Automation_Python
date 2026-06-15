"""CRUD de WeekPlan sobre Redis + puntero al plan "actual".

`plan:current` guarda el id del plan que el calendario muestra por defecto.
Cada plan vive en `plan:<id>`; el índice `plan:index` lista todos.
"""

from __future__ import annotations

from src.tiktok_shop.models.week_plan import WeekPlan
from .redis_base import ShopRedis, get_shop_redis


class PlanRepo:
    INDEX_KEY = "plan:index"
    CURRENT_KEY = "plan:current"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(plan_id: str) -> str:
        return f"plan:{plan_id}"

    def save(self, plan: WeekPlan, *, make_current: bool = True) -> WeekPlan:
        plan.touch()
        self.r.set_json(self._key(plan.id), plan.model_dump())
        self.r.sadd(self.INDEX_KEY, plan.id)
        if make_current:
            self.r.set_str(self.CURRENT_KEY, plan.id)
        return plan

    def get(self, plan_id: str) -> WeekPlan | None:
        data = self.r.get_json(self._key(plan_id))
        if not data:
            return None
        try:
            return WeekPlan.model_validate(data)
        except Exception as e:
            print(f"[PlanRepo] decode error {plan_id}: {e}")
            return None

    def get_current(self) -> WeekPlan | None:
        pid = self.r.get_str(self.CURRENT_KEY)
        return self.get(pid) if pid else None

    def set_current(self, plan_id: str) -> None:
        self.r.set_str(self.CURRENT_KEY, plan_id)

    def list_all(self) -> list[WeekPlan]:
        ids = self.r.smembers(self.INDEX_KEY)
        if not ids:
            return []
        raws = self.r.mget_json([self._key(pid) for pid in ids])
        out: list[WeekPlan] = []
        for data in raws:
            if not data:
                continue
            try:
                out.append(WeekPlan.model_validate(data))
            except Exception as e:
                print(f"[PlanRepo] decode error: {e}")
        return sorted(out, key=lambda p: p.created_at, reverse=True)

    def delete(self, plan_id: str) -> bool:
        if not self.get(plan_id):
            return False
        self.r.delete(self._key(plan_id))
        self.r.srem(self.INDEX_KEY, plan_id)
        if self.r.get_str(self.CURRENT_KEY) == plan_id:
            self.r.delete(self.CURRENT_KEY)
        return True
