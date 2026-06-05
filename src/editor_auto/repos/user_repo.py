"""CRUD de EditorUser sobre Redis."""

from __future__ import annotations

from src.editor_auto.models import EditorUser

from .redis_base import EditorRedis, get_editor_redis


class UserRepo:
    INDEX_KEY = "user:index"
    NAME_INDEX = "user:by_name:"
    ACCOUNT_EMAIL_INDEX = "user:by_account_email:"

    def __init__(self, redis: EditorRedis | None = None):
        self.r = redis or get_editor_redis()

    @staticmethod
    def _key(uid: str) -> str:
        return f"user:{uid}"

    def save(self, user: EditorUser) -> EditorUser:
        user.touch()
        self.r.set_json(self._key(user.id), user.model_dump())
        self.r.sadd(self.INDEX_KEY, user.id)
        if user.name:
            self.r.set_str(f"{self.NAME_INDEX}{user.name}", user.id)
        # Índice por email de cuenta web (puente con nebulabs-media). Permite
        # al box resolver el EditorUser desde el ticket firmado de la web.
        if user.account_email:
            self.r.set_str(
                f"{self.ACCOUNT_EMAIL_INDEX}{user.account_email.strip().lower()}",
                user.id,
            )
        return user

    def get_by_account_email(self, email: str) -> EditorUser | None:
        if not email:
            return None
        uid = self.r.get_str(f"{self.ACCOUNT_EMAIL_INDEX}{email.strip().lower()}")
        if not uid:
            return None
        return self.get(uid)

    def get(self, user_id: str) -> EditorUser | None:
        data = self.r.get_json(self._key(user_id))
        if not data:
            return None
        try:
            return EditorUser.model_validate(data)
        except Exception as e:
            print(f"[editor_auto.UserRepo] decode error {user_id}: {e}")
            return None

    def get_by_name(self, name: str) -> EditorUser | None:
        uid = self.r.get_str(f"{self.NAME_INDEX}{name}")
        if not uid:
            return None
        return self.get(uid)

    def list_all(self, include_deleted: bool = False) -> list[EditorUser]:
        ids = self.r.smembers(self.INDEX_KEY)
        users: list[EditorUser] = []
        for i in ids:
            u = self.get(i)
            if u is None:
                continue
            if u.deleted and not include_deleted:
                continue
            users.append(u)
        return sorted(users, key=lambda u: u.created_at, reverse=True)

    def delete(self, user_id: str, *, hard: bool = False) -> bool:
        u = self.get(user_id)
        if u is None:
            return False
        if hard:
            self.r.delete(self._key(user_id))
            self.r.srem(self.INDEX_KEY, user_id)
            if u.name:
                self.r.delete(f"{self.NAME_INDEX}{u.name}")
            return True
        u.deleted = True
        self.save(u)
        return True
