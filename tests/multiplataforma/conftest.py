"""FakeRedis + transporte httpx simulado para el publicador Multiplataforma."""

from __future__ import annotations

import json

import httpx
import pytest

from src.multiplataforma.repos import redis_base


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict = {}
        self.sets: dict[str, set] = {}

    def is_available(self) -> bool:
        return True

    def get_json(self, k):
        v = self.data.get(k)
        return json.loads(json.dumps(v)) if v is not None else None

    def set_json(self, k, v):
        self.data[k] = json.loads(json.dumps(v))
        return True

    def delete(self, k):
        self.data.pop(k, None)
        return True

    def sadd(self, k, m):
        self.sets.setdefault(k, set()).add(m)
        return True

    def srem(self, k, m):
        self.sets.get(k, set()).discard(m)
        return True

    def smembers(self, k):
        return list(self.sets.get(k, set()))


@pytest.fixture(autouse=True)
def redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(redis_base, "_INSTANCE", r)
    monkeypatch.delenv("MULTIPLATAFORMA_DRY_RUN", raising=False)
    return r


class Grabadora:
    """Transporte que responde con `rutas` [(metodo, trozo_url, respuesta|callable)]
    y apunta cada petición. Si nada casa, falla el test."""

    def __init__(self, rutas):
        self.rutas = rutas
        self.peticiones: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.peticiones.append(request)
        for metodo, trozo, resp in self.rutas:
            if request.method == metodo and trozo in str(request.url):
                if callable(resp):
                    resp = resp(request)
                if isinstance(resp, httpx.Response):
                    return resp
                return httpx.Response(200, json=resp)
        raise AssertionError(f"Petición inesperada: {request.method} {request.url}")

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def prohibido(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"No debía tocar la red: {request.method} {request.url}")


@pytest.fixture()
def sin_red():
    return httpx.Client(transport=httpx.MockTransport(prohibido))


def form(request: httpx.Request) -> dict:
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
