"""Wrapper Upstash REST del publicador Multiplataforma (prefijo `multiplataforma:`).

Copia el patrón de `src/viralizacion/repos/redis_base.py` — namespace aislado
propio, no se reutiliza el de otro programa."""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

import requests

from src.multiplataforma.config import redis_prefix


class MultiplataformaRedis:
    """Si Redis no está configurado, devuelve valores neutros y avisa."""

    def __init__(self) -> None:
        self.url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
        self.token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
        self.prefix = redis_prefix()

    def is_available(self) -> bool:
        return bool(self.url and self.token)

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
        except Exception as e:  # noqa: BLE001
            print(f"[MultiplataformaRedis] GET {path} error: {e}")
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
        except Exception as e:  # noqa: BLE001
            print(f"[MultiplataformaRedis] POST {path} error: {e}")
            return None

    def get_json(self, key: str) -> Any:
        raw = self._get(f"get/{self._enc(self._full_key(key))}")
        if raw is None:
            return None
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: dict | list) -> bool:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return self._post(f"set/{self._enc(self._full_key(key))}", body=body) == "OK"

    def delete(self, key: str) -> bool:
        return self._post(f"del/{self._enc(self._full_key(key))}") is not None

    def sadd(self, key: str, member: str) -> bool:
        return self._post(f"sadd/{self._enc(self._full_key(key))}/{self._enc(member)}") is not None

    def srem(self, key: str, member: str) -> bool:
        return self._post(f"srem/{self._enc(self._full_key(key))}/{self._enc(member)}") is not None

    def smembers(self, key: str) -> list[str]:
        return list(self._get(f"smembers/{self._enc(self._full_key(key))}") or [])


_INSTANCE: MultiplataformaRedis | None = None


def get_redis() -> MultiplataformaRedis:
    """Singleton perezoso (los tests lo sustituyen poniendo `_INSTANCE`)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MultiplataformaRedis()
    return _INSTANCE
