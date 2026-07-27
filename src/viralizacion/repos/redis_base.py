"""Wrapper Upstash REST especializado para Viralización (prefijo `viralizacion:`).

Copia el patrón de `src/tiktok_shop/repos/redis_base.py:ShopRedis` — namespace
aislado propio, NO se reutiliza `ShopRedis` directamente (aislamiento entre
programas, ver CLAUDE.md)."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import requests

from src.viralizacion.config import redis_prefix


class ViralizacionRedis:
    """Cliente Redis con prefijo `viralizacion:` por defecto.

    Si Upstash no está configurado, las funciones devuelven valores neutros
    (None / [] / False) y logean un warning — el caller debe degradar
    limpiamente (aquí: el allocator lanza error claro en vez de asumir pool
    infinito, ver `services/usage_tracker.py`)."""

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
            print(f"[ViralizacionRedis] GET {path} error: {e}")
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
            print(f"[ViralizacionRedis] POST {path} error: {e}")
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

    def sadd(self, key: str, member: str) -> bool:
        result = self._post(f"sadd/{self._enc(self._full_key(key))}/{self._enc(member)}")
        return result is not None

    def srem(self, key: str, member: str) -> bool:
        result = self._post(f"srem/{self._enc(self._full_key(key))}/{self._enc(member)}")
        return result is not None

    def smembers(self, key: str) -> list[str]:
        result = self._get(f"smembers/{self._enc(self._full_key(key))}")
        return list(result or [])

    def sismember(self, key: str, member: str) -> bool:
        result = self._get(f"sismember/{self._enc(self._full_key(key))}/{self._enc(member)}")
        return bool(result)


# Singleton perezoso
_INSTANCE: ViralizacionRedis | None = None


def get_viralizacion_redis() -> ViralizacionRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ViralizacionRedis()
    return _INSTANCE
