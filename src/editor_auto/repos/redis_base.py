"""Wrapper Upstash REST con prefijo `editor_auto:`.

Aislado de TikTok Shop (`tiktok_shop:`) y Pronósticos (`betai:`) para que
los datos del programa Editor Auto no colisionen con los otros nichos.

El esqueleto es idéntico al de `src/tiktok_shop/repos/redis_base.py` —
duplicamos en vez de refactorizar para mantener el aislamiento entre
programas que exige `CLAUDE.md` (un cambio en Shop no debe romper Editor).
"""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

import requests

from src.editor_auto.config import redis_prefix


class EditorRedis:
    """Cliente Redis Upstash con prefijo `editor_auto:` por defecto.

    Si Upstash no está configurado (URL/token vacíos), todos los métodos
    devuelven valores neutros (None/[]) y emiten print a stderr — la UI
    degrada limpiamente sin romper.
    """

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
        except Exception as e:
            print(f"[EditorRedis] GET {path} error: {e}")
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
            print(f"[EditorRedis] POST {path} error: {e}")
            return None

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


_INSTANCE: EditorRedis | None = None


def get_editor_redis() -> EditorRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = EditorRedis()
    return _INSTANCE
