"""Wrapper Upstash REST especializado para Cuotas diarias (`cuotas:`).

Copia el patrón de `src/viralizacion/repos/redis_base.py` — namespace aislado
propio, NO se reutiliza el cliente de otro programa (aislamiento entre
programas, ver CLAUDE.md)."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import requests

from src.cuotas.config import REDIS_PREFIX


class CuotasRedis:
    """Cliente Redis con prefijo `cuotas:` por defecto.

    Si Upstash no está configurado devuelve valores neutros (None / [] /
    False); el caller decide si degrada o falla duro."""

    def __init__(self) -> None:
        import os

        self.url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
        self.token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
        self.prefix = REDIS_PREFIX

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
            print(f"[CuotasRedis] GET {path} error: {e}")
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
            print(f"[CuotasRedis] POST {path} error: {e}")
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

    def mget_json(self, keys: list[str]) -> list[dict | None]:
        """MGET en un solo roundtrip. Con Upstash REST, N `get_json` son N
        latencias seguidas; esto las convierte en una.

        Devuelve una lista paralela a `keys`: dict decodificado o None.
        """
        if not keys:
            return []
        encoded = "/".join(self._enc(self._full_key(k)) for k in keys)
        raw_list = self._get(f"mget/{encoded}")
        if not raw_list:
            return [None] * len(keys)
        out: list[dict | None] = []
        for raw in raw_list:
            if raw is None:
                out.append(None)
                continue
            try:
                out.append(json.loads(raw) if isinstance(raw, str) else raw)
            except (json.JSONDecodeError, TypeError):
                out.append(None)
        return out

    def set_json(self, key: str, value: dict | list) -> bool:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        result = self._post(f"set/{self._enc(self._full_key(key))}", body=body)
        return result == "OK"

    def set_nx(self, key: str, value: str, ttl_s: int) -> bool:
        """SET key value NX EX ttl. True si lo cogió (no existía).

        Es la primitiva de cerrojo: el TTL evita que un proceso muerto deje
        la llave puesta para siempre.
        """
        k = self._enc(self._full_key(key))
        result = self._post(f"set/{k}/{self._enc(value)}/nx/ex/{int(ttl_s)}")
        return result == "OK"

    def delete(self, key: str) -> bool:
        return self._post(f"del/{self._enc(self._full_key(key))}") is not None

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
_INSTANCE: CuotasRedis | None = None


def get_cuotas_redis() -> CuotasRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = CuotasRedis()
    return _INSTANCE
