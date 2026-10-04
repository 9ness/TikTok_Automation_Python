"""CRUD de EditorUser sobre Redis."""

from __future__ import annotations

import threading
import time

from src.editor_auto.models import EditorUser

from .redis_base import EditorRedis, get_editor_redis


# La lista de usuarios la piden cada pocos segundos el vigilante de `entrada/`
# (cada 30 s), el contador de carpetas del menú y el barrido de borradores. En
# Upstash cada comando se paga, así que se guarda en memoria un rato y se tira al
# guardar o borrar un usuario (la API es un solo proceso: ver Dockerfile.api).
_LISTA_TTL_S = 300.0
_lista_cache: dict[str, tuple[float, list[EditorUser]]] = {}
_lista_lock = threading.Lock()


def _invalidar_lista() -> None:
    with _lista_lock:
        _lista_cache.clear()


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
        _invalidar_lista()
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
        _invalidar_lista()
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
        clave = getattr(self.r, "prefix", "") or ""
        with _lista_lock:
            hit = _lista_cache.get(clave)
        if hit and time.time() - hit[0] < _LISTA_TTL_S:
            todos = hit[1]
        else:
            ids = sorted(self.r.smembers(self.INDEX_KEY))
            mget = getattr(self.r, "mget_json", None)
            claves = [self._key(i) for i in ids]
            datos = (mget(claves) if mget else [self.r.get_json(k) for k in claves]) if ids else []
            todos = []
            for i, data in zip(ids, datos):
                if not data:
                    continue
                try:
                    todos.append(EditorUser.model_validate(data))
                except Exception as e:
                    print(f"[editor_auto.UserRepo] decode error {i}: {e}")
            todos.sort(key=lambda u: u.created_at, reverse=True)
            if ids and len(todos) == len(ids):  # no cachear un resultado roto
                with _lista_lock:
                    _lista_cache[clave] = (time.time(), todos)
        users = [u.model_copy(deep=True) for u in todos if include_deleted or not u.deleted]
        return users

    def delete(self, user_id: str, *, hard: bool = False) -> bool:
        _invalidar_lista()
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
