"""CRUD de ReferralCode sobre Redis.

Las refs están indexadas por `code` (lookup directo al registrar un user)
y por `owner_user_id` (para mostrar las refs de un user en su perfil).
"""

from __future__ import annotations

from src.editor_auto.models import ReferralCode, ReferralUse

from .redis_base import EditorRedis, get_editor_redis


class ReferralRepo:
    INDEX_KEY = "referral:index"          # SET de codes
    OWNER_INDEX = "referral:by_owner:"    # STR owner_user_id → code

    def __init__(self, redis: EditorRedis | None = None):
        self.r = redis or get_editor_redis()

    @staticmethod
    def _key(code: str) -> str:
        return f"referral:{code}"

    def save(self, ref: ReferralCode) -> ReferralCode:
        self.r.set_json(self._key(ref.code), ref.model_dump())
        self.r.sadd(self.INDEX_KEY, ref.code)
        if ref.owner_user_id:
            self.r.set_str(f"{self.OWNER_INDEX}{ref.owner_user_id}", ref.code)
        return ref

    def get(self, code: str) -> ReferralCode | None:
        data = self.r.get_json(self._key(code))
        if not data:
            return None
        try:
            return ReferralCode.model_validate(data)
        except Exception as e:
            print(f"[editor_auto.ReferralRepo] decode error {code}: {e}")
            return None

    def get_by_owner(self, user_id: str) -> ReferralCode | None:
        code = self.r.get_str(f"{self.OWNER_INDEX}{user_id}")
        if not code:
            return None
        return self.get(code)

    def list_all(self) -> list[ReferralCode]:
        codes = self.r.smembers(self.INDEX_KEY)
        refs: list[ReferralCode] = []
        for c in codes:
            ref = self.get(c)
            if ref is not None:
                refs.append(ref)
        return sorted(refs, key=lambda r: r.created_at, reverse=True)

    def add_use(self, code: str, use: ReferralUse) -> ReferralCode | None:
        ref = self.get(code)
        if ref is None:
            return None
        ref.uses.append(use)
        return self.save(ref)

    def delete(self, code: str) -> bool:
        ref = self.get(code)
        if ref is None:
            return False
        self.r.delete(self._key(code))
        self.r.srem(self.INDEX_KEY, code)
        if ref.owner_user_id:
            self.r.delete(f"{self.OWNER_INDEX}{ref.owner_user_id}")
        return True
