"""CRUD de DiscoveredProduct (candidatos del Radar) sobre Redis.

Persiste los candidatos descubiertos para que el Radar sobreviva entre
sesiones. Keyed por `product_id` de TikTok Shop (estable), así un re-scan
actualiza el candidato existente en vez de duplicarlo.
"""

from __future__ import annotations

from src.tiktok_shop.models.discovery import DiscoveredProduct
from .redis_base import ShopRedis, get_shop_redis


class DiscoveryRepo:
    INDEX_KEY = "discovery:index"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(product_id: str) -> str:
        return f"discovery:{product_id}"

    def save(self, cand: DiscoveredProduct) -> DiscoveredProduct:
        cand.touch()
        self.r.set_json(self._key(cand.product_id), cand.model_dump())
        self.r.sadd(self.INDEX_KEY, cand.product_id)
        return cand

    def get(self, product_id: str) -> DiscoveredProduct | None:
        data = self.r.get_json(self._key(product_id))
        if not data:
            return None
        try:
            return DiscoveredProduct.model_validate(data)
        except Exception as e:
            print(f"[DiscoveryRepo] decode error {product_id}: {e}")
            return None

    def upsert_scored(self, cand: DiscoveredProduct) -> DiscoveredProduct:
        """Guarda preservando el estado de importación si ya existía (un
        re-scan no debe borrar `imported`/`imported_product_id`)."""
        existing = self.get(cand.product_id)
        if existing and existing.imported:
            cand.imported = True
            cand.imported_product_id = existing.imported_product_id
        return self.save(cand)

    def list_all(self) -> list[DiscoveredProduct]:
        ids = self.r.smembers(self.INDEX_KEY)
        if not ids:
            return []
        raws = self.r.mget_json([self._key(pid) for pid in ids])
        out: list[DiscoveredProduct] = []
        for data in raws:
            if not data:
                continue
            try:
                out.append(DiscoveredProduct.model_validate(data))
            except Exception as e:
                print(f"[DiscoveryRepo] decode error: {e}")
        # Mejor score primero; a igualdad, descubierto más reciente.
        return sorted(
            out, key=lambda c: (c.score.total, c.discovered_at), reverse=True,
        )

    def delete(self, product_id: str) -> bool:
        if not self.get(product_id):
            return False
        self.r.delete(self._key(product_id))
        self.r.srem(self.INDEX_KEY, product_id)
        return True

    def clear_non_imported(self) -> int:
        """Borra candidatos NO importados (limpieza del Radar). Devuelve
        cuántos borró. Los importados se conservan como histórico."""
        n = 0
        for cand in self.list_all():
            if not cand.imported:
                if self.delete(cand.product_id):
                    n += 1
        return n
