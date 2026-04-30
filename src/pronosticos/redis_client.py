"""Wrapper mínimo sobre Upstash Redis REST API.

Solo se cubren los comandos que necesita el pipeline de Pronósticos:
GET, HGET, SET, HSET. Cualquier otro caso se puede añadir on-demand.
"""

from __future__ import annotations

import os
import json
from typing import Any

import requests
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


class UpstashRedis:
    def __init__(self, url: str | None = None, token: str | None = None, prefix: str | None = None):
        self.url = (url or os.environ.get("UPSTASH_REDIS_REST_URL", "")).rstrip("/")
        self.token = token or os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
        self.prefix = prefix if prefix is not None else os.environ.get("REDIS_PREFIX", "betai:")
        if not self.url or not self.token:
            raise EnvironmentError(
                "Faltan UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN en el entorno."
            )

    def _full_key(self, key: str) -> str:
        if self.prefix and not key.startswith(self.prefix):
            return f"{self.prefix}{key}"
        return key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, key: str) -> Any:
        r = requests.get(f"{self.url}/get/{self._full_key(key)}", headers=self._headers(), timeout=10)
        r.raise_for_status()
        return r.json().get("result")

    def hget(self, key: str, field: str) -> Any:
        r = requests.get(
            f"{self.url}/hget/{self._full_key(key)}/{field}",
            headers=self._headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result")

    def set(self, key: str, value: Any) -> Any:
        body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        r = requests.post(
            f"{self.url}/set/{self._full_key(key)}",
            headers={**self._headers(), "Content-Type": "text/plain"},
            data=body.encode("utf-8"),
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result")

    def hset(self, key: str, field: str, value: Any) -> Any:
        body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        r = requests.post(
            f"{self.url}/hset/{self._full_key(key)}/{field}",
            headers={**self._headers(), "Content-Type": "text/plain"},
            data=body.encode("utf-8"),
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result")

    def ping(self) -> bool:
        try:
            r = requests.get(f"{self.url}/ping", headers=self._headers(), timeout=5)
            return r.ok and r.json().get("result") == "PONG"
        except Exception:
            return False
