"""CRUD de Product sobre Redis."""

from __future__ import annotations

from src.tiktok_shop.models import Product
from .redis_base import ShopRedis, get_shop_redis


class ProductRepo:
    INDEX_KEY = "product:index"
    SLUG_INDEX = "product:by_slug:"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(pid: str) -> str:
        return f"product:{pid}"

    def save(self, product: Product) -> Product:
        product.touch()
        self.r.set_json(self._key(product.id), product.model_dump())
        self.r.sadd(self.INDEX_KEY, product.id)
        if product.slug:
            self.r.set_str(f"{self.SLUG_INDEX}{product.slug}", product.id)
        return product

    def get(self, product_id: str) -> Product | None:
        data = self.r.get_json(self._key(product_id))
        if not data:
            return None
        data = self._migrate_legacy_shape(data)
        try:
            return Product.model_validate(data)
        except Exception as e:
            print(f"[ProductRepo] decode error {product_id}: {e}")
            return None

    @staticmethod
    def _migrate_legacy_shape(data: dict) -> dict:
        """Normaliza productos guardados con el shape v1.

        Cambios v1 → v2:
          - `photos: [...]` (lista plana) → `photos: {source: [...], generated: []}`
            Los items existentes se asumen como originales.
          - `video_config.default_model` (model_id legacy) → `default_tier` (key del tier).
            Mapeo: `seedance_1_5_pro_fast` → "standard", `seedance_2_0_pro` → "pro",
            cualquier otro → "standard".
          - `video_config.avoid_packaging_close_up` → `has_complex_packaging`.

        La migración es no-destructiva: si el shape ya es v2, no toca nada.
        """
        photos = data.get("photos")
        if isinstance(photos, list):
            data["photos"] = {"source": photos, "generated": []}

        video_cfg = data.get("video_config")
        if isinstance(video_cfg, dict):
            if "default_model" in video_cfg and "default_tier" not in video_cfg:
                old = video_cfg.pop("default_model")
                video_cfg["default_tier"] = {
                    "seedance_1_5_pro_fast": "standard",
                    "seedance_2_0_pro": "pro",
                    "veo3_prompt_only": "veo3_prompt_only",
                }.get(old, "standard")
            if "avoid_packaging_close_up" in video_cfg and "has_complex_packaging" not in video_cfg:
                video_cfg["has_complex_packaging"] = video_cfg.pop("avoid_packaging_close_up")
        return data

    def get_by_slug(self, slug: str) -> Product | None:
        pid = self.r.get_str(f"{self.SLUG_INDEX}{slug}")
        if not pid:
            return None
        return self.get(pid)

    def list_all(self) -> list[Product]:
        ids = self.r.smembers(self.INDEX_KEY)
        if not ids:
            return []
        # mget_json: 1 roundtrip en vez de N. Crítico para dashboard.
        keys = [self._key(pid) for pid in ids]
        raws = self.r.mget_json(keys)
        products: list[Product] = []
        for data in raws:
            if not data:
                continue
            try:
                products.append(Product.model_validate(data))
            except Exception as e:
                print(f"[ProductRepo] decode error: {e}")
        return sorted(products, key=lambda p: p.created_at, reverse=True)

    def delete(self, product_id: str) -> bool:
        p = self.get(product_id)
        if p is None:
            return False
        self.r.delete(self._key(product_id))
        self.r.srem(self.INDEX_KEY, product_id)
        if p.slug:
            self.r.delete(f"{self.SLUG_INDEX}{p.slug}")
        return True
