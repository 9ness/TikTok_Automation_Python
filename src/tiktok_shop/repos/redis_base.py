"""Wrapper Upstash REST especializado para TikTok Shop.

Reusa `UpstashRedis` de pronosticos como base, pero con prefijo distinto
(`tiktok_shop:`) y añade los comandos que necesitan los repos del nicho:
DEL, KEYS, SADD, SREM, SMEMBERS, LPUSH, LRANGE.

Nota: Upstash REST permite chainear comandos por path (ej. `/sadd/{key}/{m}`).
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import requests

from src.tiktok_shop.config import redis_prefix


class ShopRedis:
    """Cliente Redis con prefijo `tiktok_shop:` por defecto.

    Si Upstash no está configurado, las funciones devuelven valores neutros
    (None / [] / False) y emiten un warning a stderr — la UI degrada limpiamente
    como hace `configs_store`.
    """

    def __init__(self) -> None:
        import os

        self.url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
        self.token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
        self.prefix = redis_prefix()

    def is_available(self) -> bool:
        return bool(self.url and self.token)

    # ---- helpers ----
    def _full_key(self, key: str) -> str:
        if self.prefix and not key.startswith(self.prefix):
            return f"{self.prefix}{key}"
        return key

    def _enc(self, s: str) -> str:
        return urllib.parse.quote(s, safe="")

    def _headers(self, content_type: str | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.token}"}
        if content_type:
            h["Content-Type"] = content_type
        return h

    def _get(self, path: str, *, timeout: float = 10) -> Any:
        if not self.is_available():
            return None
        try:
            r = requests.get(f"{self.url}/{path}", headers=self._headers(), timeout=timeout)
            r.raise_for_status()
            return r.json().get("result")
        except Exception as e:
            print(f"[ShopRedis] GET {path} error: {e}")
            return None

    def _post(self, path: str, body: bytes | None = None, *, timeout: float = 10) -> Any:
        if not self.is_available():
            return None
        try:
            r = requests.post(
                f"{self.url}/{path}",
                headers=self._headers("text/plain" if body else None),
                data=body,
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json().get("result")
        except Exception as e:
            print(f"[ShopRedis] POST {path} error: {e}")
            return None

    # ---- comandos ----
    def get_json(self, key: str) -> dict | None:
        raw = self._get(f"get/{self._enc(self._full_key(key))}")
        if raw is None:
            return None
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: dict | list) -> bool:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        result = self._post(f"set/{self._enc(self._full_key(key))}", body=body)
        return result == "OK"

    def get_str(self, key: str) -> str | None:
        return self._get(f"get/{self._enc(self._full_key(key))}")

    def set_str(self, key: str, value: str) -> bool:
        result = self._post(
            f"set/{self._enc(self._full_key(key))}",
            body=value.encode("utf-8"),
        )
        return result == "OK"

    def delete(self, key: str) -> bool:
        result = self._get(f"del/{self._enc(self._full_key(key))}")
        return bool(result)

    def keys(self, pattern: str) -> list[str]:
        # pattern relativo al prefijo (ej. "user:*") — añadimos prefijo
        full = self._full_key(pattern)
        result = self._get(f"keys/{self._enc(full)}")
        if not result:
            return []
        return [k[len(self.prefix):] if k.startswith(self.prefix) else k for k in result]

    def sadd(self, key: str, member: str) -> bool:
        result = self._post(
            f"sadd/{self._enc(self._full_key(key))}/{self._enc(member)}"
        )
        return result is not None

    def srem(self, key: str, member: str) -> bool:
        result = self._post(
            f"srem/{self._enc(self._full_key(key))}/{self._enc(member)}"
        )
        return result is not None

    def smembers(self, key: str) -> list[str]:
        result = self._get(f"smembers/{self._enc(self._full_key(key))}")
        return list(result or [])

    def lpush(self, key: str, value: str) -> int:
        result = self._post(
            f"lpush/{self._enc(self._full_key(key))}/{self._enc(value)}"
        )
        try:
            return int(result or 0)
        except (TypeError, ValueError):
            return 0

    def lrange(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        result = self._get(f"lrange/{self._enc(self._full_key(key))}/{start}/{stop}")
        return list(result or [])

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        """LTRIM key start stop — recorta la lista en sitio."""
        result = self._post(f"ltrim/{self._enc(self._full_key(key))}/{start}/{stop}")
        return result == "OK"


# Singleton perezoso
_INSTANCE: ShopRedis | None = None


def get_shop_redis() -> ShopRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ShopRedis()
    return _INSTANCE
