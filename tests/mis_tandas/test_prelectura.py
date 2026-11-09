"""Prelectura de ViralizacionRedis: un MGET sirve los get_json del bloque."""

from __future__ import annotations

import json

from src.viralizacion.repos.redis_base import ViralizacionRedis


def _cliente(monkeypatch, datos: dict):
    r = ViralizacionRedis()
    r.url, r.token, r.prefix = "http://x", "t", ""
    llamadas: list[str] = []

    def _get(path, timeout=10):
        llamadas.append(path)
        if path.startswith("mget/"):
            return [datos.get(k) for k in path[5:].split("/")]
        return datos.get(path[4:])

    monkeypatch.setattr(r, "_get", _get)
    monkeypatch.setattr(r, "_post", lambda path, body=None, timeout=10: "OK")
    return r, llamadas


def test_un_mget_sirve_las_lecturas_del_bloque(monkeypatch):
    r, llamadas = _cliente(monkeypatch, {"a": json.dumps({"ids": [1]}), "b": None})
    with r.prelectura(["a", "b"]):
        assert r.get_json("a") == {"ids": [1]}
        assert r.get_json("b") is None
        r.get_json("a")["ids"].append(2)  # mutar lo devuelto no ensucia la caché
        assert r.get_json("a") == {"ids": [1]}
    assert llamadas == ["mget/a/b"]
    r.get_json("a")  # fuera del bloque vuelve a Redis
    assert llamadas[-1] == "get/a"


def test_lo_escrito_dentro_del_bloque_se_relee(monkeypatch):
    r, llamadas = _cliente(monkeypatch, {"a": json.dumps({"v": 1})})
    with r.prelectura(["a"]):
        r.set_json("a", {"v": 2})
        r.get_json("a")
    assert llamadas == ["mget/a", "get/a"]


def test_si_falla_el_mget_cada_lectura_va_a_redis(monkeypatch):
    r, llamadas = _cliente(monkeypatch, {"a": json.dumps({"v": 1})})
    monkeypatch.setattr(r, "_get", lambda p, timeout=10: llamadas.append(p) or (None if p.startswith("mget") else json.dumps({"v": 1})))
    with r.prelectura(["a"]):
        assert r.get_json("a") == {"v": 1}
    assert llamadas == ["mget/a", "get/a"]
