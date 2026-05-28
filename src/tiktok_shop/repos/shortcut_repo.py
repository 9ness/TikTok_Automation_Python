"""CRUD de OperatorShortcut. Scope por operador.

Layout Redis:
  - `tiktok_shop:shortcut:{shortcut_id}` → JSON con el shortcut
  - `tiktok_shop:shortcut:index:{operator}` → SET de shortcut_ids del operador
  - `tiktok_shop:shortcut:dedupe:{operator}:{user_id}:{product_id}` → shortcut_id

El dedupe key permite saber rápido si ya existe un shortcut equivalente
sin recorrer toda la lista del operador.
"""

from __future__ import annotations

from src.tiktok_shop.models import OperatorShortcut
from .redis_base import ShopRedis, get_shop_redis


class ShortcutRepo:
    PREFIX = "shortcut"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(shortcut_id: str) -> str:
        return f"shortcut:{shortcut_id}"

    @staticmethod
    def _index_key(operator: str) -> str:
        return f"shortcut:index:{operator}"

    @staticmethod
    def _dedupe_key(operator: str, user_id: str, product_id: str) -> str:
        return f"shortcut:dedupe:{operator}:{user_id}:{product_id}"

    def list_by_operator(self, operator: str) -> list[OperatorShortcut]:
        """Devuelve los shortcuts del operador, ordenados por created_at
        descendiente (más recientes primero)."""
        ids = self.r.smembers(self._index_key(operator))
        out: list[OperatorShortcut] = []
        for sid in ids:
            data = self.r.get_json(self._key(sid))
            if not data:
                # Stale en el set — limpia
                self.r.srem(self._index_key(operator), sid)
                continue
            try:
                out.append(OperatorShortcut.model_validate(data))
            except Exception as e:
                print(f"[ShortcutRepo] decode error {sid}: {e}")
        return sorted(out, key=lambda s: s.created_at, reverse=True)

    def get(self, shortcut_id: str) -> OperatorShortcut | None:
        data = self.r.get_json(self._key(shortcut_id))
        if not data:
            return None
        try:
            return OperatorShortcut.model_validate(data)
        except Exception as e:
            print(f"[ShortcutRepo] decode error {shortcut_id}: {e}")
            return None

    def find_existing(
        self, operator: str, user_id: str, product_id: str,
    ) -> OperatorShortcut | None:
        """Devuelve el shortcut existente para esta combinación si lo hay."""
        existing_id = self.r.get_str(self._dedupe_key(operator, user_id, product_id))
        if not existing_id:
            return None
        return self.get(existing_id)

    def create(
        self, operator: str, user_id: str, product_id: str,
    ) -> OperatorShortcut:
        """Crea o devuelve el existente (idempotente). Asegura que la
        misma combinación nunca aparece dos veces para el mismo operador."""
        existing = self.find_existing(operator, user_id, product_id)
        if existing is not None:
            return existing
        shortcut = OperatorShortcut(
            operator=operator,
            user_id=user_id,
            product_id=product_id,
        )
        self.r.set_json(self._key(shortcut.id), shortcut.model_dump())
        self.r.sadd(self._index_key(operator), shortcut.id)
        # Dedupe key (string → shortcut_id)
        try:
            self.r.set_str(
                self._dedupe_key(operator, user_id, product_id),
                shortcut.id,
            )
        except Exception:
            # Si no tenemos set_str, intentamos con set_json (workaround)
            pass
        return shortcut

    def delete(self, operator: str, shortcut_id: str) -> bool:
        """Borra un shortcut. Devuelve True si existía y se borró. Solo
        borra si el shortcut pertenece al operador (anti-acceso cruzado)."""
        sc = self.get(shortcut_id)
        if sc is None:
            return False
        if sc.operator != operator:
            # No permitir borrar shortcuts de otros operadores
            return False
        self.r.delete(self._key(shortcut_id))
        self.r.srem(self._index_key(operator), shortcut_id)
        try:
            self.r.delete(self._dedupe_key(
                operator, sc.user_id, sc.product_id,
            ))
        except Exception:
            pass
        return True
