"""CRUD de TikTokUser sobre Redis."""

from __future__ import annotations

from src.tiktok_shop.models import TikTokUser
from .redis_base import ShopRedis, get_shop_redis


class UserRepo:
    INDEX_KEY = "user:index"
    USERNAME_INDEX = "user:by_username:"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(uid: str) -> str:
        return f"user:{uid}"

    def save(self, user: TikTokUser) -> TikTokUser:
        user.touch()
        self.r.set_json(self._key(user.id), user.model_dump())
        self.r.sadd(self.INDEX_KEY, user.id)
        if user.username:
            self.r.set_str(f"{self.USERNAME_INDEX}{user.username}", user.id)
        return user

    def get(self, user_id: str) -> TikTokUser | None:
        data = self.r.get_json(self._key(user_id))
        if not data:
            return None
        try:
            return TikTokUser.model_validate(data)
        except Exception as e:
            print(f"[UserRepo] decode error {user_id}: {e}")
            return None

    def get_by_username(self, username: str) -> TikTokUser | None:
        if not username.startswith("@"):
            username = f"@{username}"
        uid = self.r.get_str(f"{self.USERNAME_INDEX}{username}")
        if not uid:
            return None
        return self.get(uid)

    def list_all(self) -> list[TikTokUser]:
        ids = self.r.smembers(self.INDEX_KEY)
        users = [self.get(i) for i in ids]
        return sorted(
            (u for u in users if u is not None),
            key=lambda u: u.created_at,
            reverse=True,
        )

    def delete(self, user_id: str) -> bool:
        u = self.get(user_id)
        if u is None:
            return False
        self.r.delete(self._key(user_id))
        self.r.srem(self.INDEX_KEY, user_id)
        if u.username:
            self.r.delete(f"{self.USERNAME_INDEX}{u.username}")
        return True

    def assign_product(self, user_id: str, product_id: str) -> bool:
        u = self.get(user_id)
        if u is None:
            return False
        if product_id not in u.assigned_products:
            u.assigned_products.append(product_id)
            self.save(u)
        return True

    def unassign_product(self, user_id: str, product_id: str) -> bool:
        u = self.get(user_id)
        if u is None:
            return False
        if product_id in u.assigned_products:
            u.assigned_products.remove(product_id)
            self.save(u)
        return True
