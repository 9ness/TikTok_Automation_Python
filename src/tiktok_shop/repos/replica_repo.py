"""CRUD de ReplicaSession sobre Redis.

Cada sesión vive en `replica:<id>`; el índice `replica:index` lista todas.
Historial de réplicas virales generadas (standalone, sin producto).
"""

from __future__ import annotations

from src.tiktok_shop.models.replica_session import ReplicaSession

from .redis_base import ShopRedis, get_shop_redis


class ReplicaRepo:
    INDEX_KEY = "replica:index"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(replica_id: str) -> str:
        return f"replica:{replica_id}"

    def save(self, session: ReplicaSession) -> ReplicaSession:
        session.touch()
        self.r.set_json(self._key(session.id), session.model_dump())
        self.r.sadd(self.INDEX_KEY, session.id)
        return session

    def get(self, replica_id: str) -> ReplicaSession | None:
        data = self.r.get_json(self._key(replica_id))
        if not data:
            return None
        try:
            return ReplicaSession.model_validate(data)
        except Exception as e:
            print(f"[ReplicaRepo] decode error {replica_id}: {e}")
            return None

    def list_all(self) -> list[ReplicaSession]:
        ids = self.r.smembers(self.INDEX_KEY)
        if not ids:
            return []
        raws = self.r.mget_json([self._key(rid) for rid in ids])
        out: list[ReplicaSession] = []
        for data in raws:
            if not data:
                continue
            try:
                out.append(ReplicaSession.model_validate(data))
            except Exception as e:
                print(f"[ReplicaRepo] decode error: {e}")
        return sorted(out, key=lambda s: s.created_at, reverse=True)

    def delete(self, replica_id: str) -> bool:
        if not self.r.get_json(self._key(replica_id)):
            return False
        self.r.delete(self._key(replica_id))
        self.r.srem(self.INDEX_KEY, replica_id)
        return True
