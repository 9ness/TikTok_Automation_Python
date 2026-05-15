"""CRUD de VideoGeneration sobre Redis (histórico de vídeos creados).

Incluye métodos de agregación de coste por usuario / producto / tier / mes,
usados por el dashboard del histórico.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from src.tiktok_shop.models import VideoGeneration
from .redis_base import ShopRedis, get_shop_redis


class GenerationRepo:
    INDEX_LIST = "generation:index"               # LIST FIFO (lpush nuevo)
    BY_USER_PREFIX = "generation:by_user:"        # SET por user_id
    BY_PRODUCT_PREFIX = "generation:by_product:"  # SET por product_id

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(gid: str) -> str:
        return f"generation:{gid}"

    def save(self, gen: VideoGeneration) -> VideoGeneration:
        # Primera vez → indexar; updates posteriores → solo update del JSON
        existing = self.r.get_json(self._key(gen.id))
        self.r.set_json(self._key(gen.id), gen.model_dump(mode="json"))
        if not existing:
            self.r.lpush(self.INDEX_LIST, gen.id)
            self.r.sadd(f"{self.BY_USER_PREFIX}{gen.user_id}", gen.id)
            self.r.sadd(f"{self.BY_PRODUCT_PREFIX}{gen.product_id}", gen.id)
        return gen

    def get(self, generation_id: str) -> VideoGeneration | None:
        data = self.r.get_json(self._key(generation_id))
        if not data:
            return None
        try:
            return VideoGeneration.model_validate(data)
        except Exception as e:
            print(f"[GenerationRepo] decode error {generation_id}: {e}")
            return None

    def list_recent(self, limit: int = 50) -> list[VideoGeneration]:
        ids = self.r.lrange(self.INDEX_LIST, 0, limit - 1)
        if not ids:
            return []
        # mget_json bate todos los GETs en 1 roundtrip a Upstash (antes N
        # sequential GETs → segundos en local). Si algún elemento es None
        # (key borrada) lo descartamos.
        keys = [self._key(gid) for gid in ids]
        raws = self.r.mget_json(keys)
        out: list[VideoGeneration] = []
        for data in raws:
            if not data:
                continue
            try:
                out.append(VideoGeneration.model_validate(data))
            except Exception as e:
                print(f"[GenerationRepo] decode error: {e}")
        return out

    def list_by_user(self, user_id: str) -> list[VideoGeneration]:
        ids = self.r.smembers(f"{self.BY_USER_PREFIX}{user_id}")
        out = [self.get(i) for i in ids]
        return sorted(
            (g for g in out if g is not None),
            key=lambda g: g.created_at,
            reverse=True,
        )

    def list_by_product(self, product_id: str) -> list[VideoGeneration]:
        ids = self.r.smembers(f"{self.BY_PRODUCT_PREFIX}{product_id}")
        out = [self.get(i) for i in ids]
        return sorted(
            (g for g in out if g is not None),
            key=lambda g: g.created_at,
            reverse=True,
        )

    # ----------------------------------------------------------------
    # AGREGACIONES DE COSTE
    # ----------------------------------------------------------------
    @staticmethod
    def _within(g: VideoGeneration, since: datetime | None, until: datetime | None) -> bool:
        if since is None and until is None:
            return True
        try:
            ts = datetime.fromisoformat((g.created_at or "").replace("Z", "+00:00"))
        except ValueError:
            return False
        if since and ts < since:
            return False
        if until and ts > until:
            return False
        return True

    def total_cost_by_user(
        self, user_id: str, *,
        since: datetime | None = None, until: datetime | None = None,
    ) -> float:
        gens = [g for g in self.list_by_user(user_id) if self._within(g, since, until)]
        return round(sum(g.cost.total for g in gens), 4)

    def total_cost_by_product(
        self, product_id: str, *,
        since: datetime | None = None, until: datetime | None = None,
    ) -> float:
        gens = [g for g in self.list_by_product(product_id) if self._within(g, since, until)]
        return round(sum(g.cost.total for g in gens), 4)

    def total_cost_by_tier(
        self, tier: str, *,
        since: datetime | None = None, until: datetime | None = None,
        scan_limit: int = 1000,
    ) -> float:
        gens = [
            g for g in self.list_recent(limit=scan_limit)
            if g.tier_used == tier and self._within(g, since, until)
        ]
        return round(sum(g.cost.total for g in gens), 4)

    def monthly_summary(self, *, scan_limit: int = 1000) -> dict[str, dict]:
        """Devuelve `{ "YYYY-MM": {total, by_tier, count} }` ordenado descendente."""
        out: dict[str, dict] = defaultdict(
            lambda: {"total": 0.0, "by_tier": defaultdict(float), "count": 0}
        )
        for g in self.list_recent(limit=scan_limit):
            try:
                ts = datetime.fromisoformat((g.created_at or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            month_key = ts.strftime("%Y-%m")
            out[month_key]["total"] += g.cost.total
            out[month_key]["by_tier"][g.tier_used] += g.cost.total
            out[month_key]["count"] += 1
        # Convert defaultdicts → dicts y redondear
        result = {}
        for month, info in sorted(out.items(), reverse=True):
            result[month] = {
                "total": round(info["total"], 4),
                "by_tier": {k: round(v, 4) for k, v in info["by_tier"].items()},
                "count": info["count"],
            }
        return result

    def current_month_summary(self) -> dict:
        """Resumen del mes en curso (UTC)."""
        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        all_months = self.monthly_summary()
        return all_months.get(month_key, {"total": 0.0, "by_tier": {}, "count": 0})
