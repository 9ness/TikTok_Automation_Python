"""CRUD de PublishedVideo. Scope por producto.

Layout Redis:
  - `published:{video_id}` → JSON del PublishedVideo
  - `published:index:{product_id}` → SET de video_ids del producto
"""

from __future__ import annotations

from src.tiktok_shop.models import PublishedVideo
from .redis_base import ShopRedis, get_shop_redis


class PublishedVideoRepo:
    PREFIX = "published"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(video_id: str) -> str:
        return f"published:{video_id}"

    @staticmethod
    def _index_key(product_id: str) -> str:
        return f"published:index:{product_id}"

    def list_by_product(self, product_id: str) -> list[PublishedVideo]:
        """Vídeos publicados del producto, más recientes primero."""
        ids = self.r.smembers(self._index_key(product_id))
        out: list[PublishedVideo] = []
        for vid in ids:
            data = self.r.get_json(self._key(vid))
            if not data:
                self.r.srem(self._index_key(product_id), vid)
                continue
            try:
                out.append(PublishedVideo.model_validate(data))
            except Exception as e:
                print(f"[PublishedVideoRepo] decode error {vid}: {e}")
        return sorted(out, key=lambda v: v.created_at, reverse=True)

    def get(self, video_id: str) -> PublishedVideo | None:
        data = self.r.get_json(self._key(video_id))
        if not data:
            return None
        try:
            return PublishedVideo.model_validate(data)
        except Exception as e:
            print(f"[PublishedVideoRepo] decode error {video_id}: {e}")
            return None

    def save(self, video: PublishedVideo) -> PublishedVideo:
        video.touch()
        self.r.set_json(self._key(video.id), video.model_dump())
        self.r.sadd(self._index_key(video.product_id), video.id)
        return video

    def delete(self, product_id: str, video_id: str) -> bool:
        """Borra un vídeo publicado. Solo si pertenece al producto."""
        v = self.get(video_id)
        if v is None or v.product_id != product_id:
            return False
        self.r.delete(self._key(video_id))
        self.r.srem(self._index_key(product_id), video_id)
        return True
