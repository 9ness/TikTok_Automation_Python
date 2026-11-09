"""Wrapper Upstash REST del publicador Multiplataforma (prefijo `multiplataforma:`).

Copia el patrón de `src/viralizacion/repos/redis_base.py` — namespace aislado
propio, no se reutiliza el de otro programa."""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

import requests

from src.rutas_drive import a_absoluta, a_relativa, absolutizar, relativizar

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
            return absolutizar(json.loads(raw) if isinstance(raw, str) else raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: dict | list) -> bool:
        body = json.dumps(relativizar(value), ensure_ascii=False).encode("utf-8")
        return self._post(f"set/{self._enc(self._full_key(key))}", body=body) == "OK"

    def delete(self, key: str) -> bool:
        return self._post(f"del/{self._enc(self._full_key(key))}") is not None

    def sadd(self, key: str, member: str) -> bool:
        return self._post(f"sadd/{self._enc(self._full_key(key))}/{self._enc(a_relativa(member))}") is not None

    def srem(self, key: str, member: str) -> bool:
        return self._post(f"srem/{self._enc(self._full_key(key))}/{self._enc(a_relativa(member))}") is not None

    def smembers(self, key: str) -> list[str]:
        return [a_absoluta(x) for x in (self._get(f"smembers/{self._enc(self._full_key(key))}") or [])]

    # ---- contadores y cerrojos (enlace corto, «Comenta SÍ») ----
    def hincrby(self, key: str, campo: str, n: int = 1) -> int:
        r = self._post(f"hincrby/{self._enc(self._full_key(key))}/{self._enc(campo)}/{int(n)}")
        return int(r or 0)

    def hgetall(self, key: str) -> dict[str, int]:
        plano = self._get(f"hgetall/{self._enc(self._full_key(key))}") or []
        out: dict[str, int] = {}
        for i in range(0, len(plano) - 1, 2):
            try:
                out[str(plano[i])] = int(plano[i + 1])
            except (TypeError, ValueError):
                continue
        return out

    def incr_ttl(self, key: str, ttl_s: int) -> int:
        """INCR + EXPIRE (contador de una ventana, p. ej. tope por hora)."""
        k = self._enc(self._full_key(key))
        n = int(self._post(f"incr/{k}") or 0)
        if n == 1:
            self._post(f"expire/{k}/{int(ttl_s)}")
        return n

    def set_nx(self, key: str, ttl_s: int, valor: str = "1") -> bool:
        """SET NX EX: True solo la PRIMERA vez (deduplicar)."""
        k = self._enc(self._full_key(key))
        return self._post(f"set/{k}/{self._enc(valor)}/nx/ex/{int(ttl_s)}") == "OK"


_INSTANCE: MultiplataformaRedis | None = None


def get_redis() -> MultiplataformaRedis:
    """Singleton perezoso (los tests lo sustituyen poniendo `_INSTANCE`)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MultiplataformaRedis()
    return _INSTANCE
