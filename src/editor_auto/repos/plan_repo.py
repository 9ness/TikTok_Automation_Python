"""CRUD de Plan sobre Redis."""

from __future__ import annotations

from src.editor_auto.models import Plan

from .redis_base import EditorRedis, get_editor_redis


class PlanRepo:
    INDEX_KEY = "plan:index"
    SLUG_INDEX = "plan:by_slug:"

    def __init__(self, redis: EditorRedis | None = None):
        self.r = redis or get_editor_redis()

    @staticmethod
    def _key(pid: str) -> str:
        return f"plan:{pid}"

    def save(self, plan: Plan) -> Plan:
        plan.touch()
        self.r.set_json(self._key(plan.id), plan.model_dump())
        self.r.sadd(self.INDEX_KEY, plan.id)
        if plan.slug:
            self.r.set_str(f"{self.SLUG_INDEX}{plan.slug}", plan.id)
        return plan

    def get(self, plan_id: str) -> Plan | None:
        data = self.r.get_json(self._key(plan_id))
        if not data:
            return None
        try:
            return Plan.model_validate(data)
        except Exception as e:
            print(f"[editor_auto.PlanRepo] decode error {plan_id}: {e}")
            return None

    def get_by_slug(self, slug: str) -> Plan | None:
        pid = self.r.get_str(f"{self.SLUG_INDEX}{slug}")
        if not pid:
            return None
        return self.get(pid)

    def list_all(self, only_active: bool = False) -> list[Plan]:
        ids = self.r.smembers(self.INDEX_KEY)
        plans: list[Plan] = []
        for i in ids:
            p = self.get(i)
            if p is None:
                continue
            if only_active and not p.is_active:
                continue
            plans.append(p)
        return sorted(plans, key=lambda p: (p.sort_order, p.price_eur_monthly))

    def delete(self, plan_id: str) -> bool:
        p = self.get(plan_id)
        if p is None:
            return False
        self.r.delete(self._key(plan_id))
        self.r.srem(self.INDEX_KEY, plan_id)
        if p.slug:
            self.r.delete(f"{self.SLUG_INDEX}{p.slug}")
        return True
