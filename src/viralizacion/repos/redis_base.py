"""Wrapper Upstash REST especializado para Viralización (prefijo `viralizacion:`).

Copia el patrón de `src/tiktok_shop/repos/redis_base.py:ShopRedis` — namespace
aislado propio, NO se reutiliza `ShopRedis` directamente (aislamiento entre
programas, ver CLAUDE.md)."""

from __future__ import annotations

import contextlib
import copy
import json
import threading
import urllib.parse
from typing import Any, Iterator

import requests

from src.rutas_drive import a_absoluta, a_relativa, absolutizar, relativizar

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

    # ---- prelectura ----
    # Una pantalla que lee 5 documentos sueltos hace 5 viajes seguidos a
    # Redis REST. Con `prelectura` se piden de golpe en un MGET y, mientras
    # dure el bloque y SOLO en este hilo, `get_json` de esas claves sale de
    # memoria. Lo que se escribe o borra dentro del bloque se olvida, así que
    # una lectura posterior vuelve a Redis y nunca devuelve algo viejo.
    _local = threading.local()

    @contextlib.contextmanager
    def prelectura(self, keys: list[str]) -> Iterator[None]:
        previa = getattr(self._local, "docs", None)
        docs: dict[str, Any] = dict(previa or {})
        if self.is_available():
            faltan = [k for k in dict.fromkeys(keys) if self._full_key(k) not in docs]
            if faltan:
                encoded = "/".join(self._enc(self._full_key(k)) for k in faltan)
                raw_list = self._get(f"mget/{encoded}")
                # Si el MGET falla no se guarda nada: cada get_json va a Redis
                # como siempre.
                if isinstance(raw_list, list) and len(raw_list) == len(faltan):
                    for k, raw in zip(faltan, raw_list):
                        docs[self._full_key(k)] = raw
        self._local.docs = docs
        try:
            yield
        finally:
            self._local.docs = previa

    def _olvidar(self, key: str) -> None:
        docs = getattr(self._local, "docs", None)
        if docs:
            docs.pop(self._full_key(key), None)

    def _decodificar(self, raw: Any) -> dict | None:
        if raw is None:
            return None
        try:
            return absolutizar(json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw))
        except json.JSONDecodeError:
            return None

    # ---- comandos ----
    def get_json(self, key: str) -> dict | None:
        docs = getattr(self._local, "docs", None)
        if docs and self._full_key(key) in docs:
            return self._decodificar(docs[self._full_key(key)])
        raw = self._get(f"get/{self._enc(self._full_key(key))}")
        if raw is None:
            return None
        try:
            return absolutizar(json.loads(raw) if isinstance(raw, str) else raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: dict | list) -> bool:
        self._olvidar(key)
        body = json.dumps(relativizar(value), ensure_ascii=False).encode("utf-8")
        result = self._post(f"set/{self._enc(self._full_key(key))}", body=body)
        return result == "OK"

    def delete(self, key: str) -> bool:
        self._olvidar(key)
        result = self._post(f"del/{self._enc(self._full_key(key))}")
        return result is not None

    def sadd(self, key: str, member: str) -> bool:
        result = self._post(f"sadd/{self._enc(self._full_key(key))}/{self._enc(a_relativa(member))}")
        return result is not None

    def srem(self, key: str, member: str) -> bool:
        result = self._post(f"srem/{self._enc(self._full_key(key))}/{self._enc(a_relativa(member))}")
        return result is not None

    def smembers(self, key: str) -> list[str]:
        result = self._get(f"smembers/{self._enc(self._full_key(key))}")
        return [a_absoluta(x) for x in (result or [])]

    def sismember(self, key: str, member: str) -> bool:
        result = self._get(f"sismember/{self._enc(self._full_key(key))}/{self._enc(a_relativa(member))}")
        if not result and a_relativa(member) != member:
            # Dato viejo sin migrar: el miembro se guardó como ruta absoluta.
            result = self._get(f"sismember/{self._enc(self._full_key(key))}/{self._enc(a_absoluta(member))}")
        return bool(result)


# Singleton perezoso
_INSTANCE: ViralizacionRedis | None = None


def get_viralizacion_redis() -> ViralizacionRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ViralizacionRedis()
    return _INSTANCE
