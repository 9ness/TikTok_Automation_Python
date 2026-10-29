"""Contador de subidas (`/api/v1/subidas`): sumar, fijar, totales y permisos.

Redis falso en memoria (mismo patrón que `tests/test_estadisticas.py`) y el
usuario web forzado con `dependency_overrides` de `get_web_user`.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.api.dependencies import get_web_user
from src.subidas import repo


class _FakeRedis:
    prefix = "subidas:"

    def __init__(self):
        self.d: dict = {}

    def is_available(self):
        return True

    def get_json(self, k):
        return self.d.get(k)

    def set_json(self, k, v):
        self.d[k] = v
        return True


# Un "hoy" fijo para que los totales no dependan de la fecha en que se pasa.
_HOY = dt.datetime(2026, 11, 10, 12, 0, tzinfo=repo.ZONA)


@pytest.fixture
def fake(monkeypatch):
    f = _FakeRedis()
    monkeypatch.setattr(repo, "_redis", lambda: f)
    monkeypatch.setattr(repo, "ahora", lambda: _HOY)
    return f


@pytest.fixture
def como(app_client):
    """`como("ana")` hace que las peticiones lleguen como ese usuario."""
    def _como(usuario: str):
        app_client.app.dependency_overrides[get_web_user] = lambda: usuario
        return app_client
    yield _como
    app_client.app.dependency_overrides.pop(get_web_user, None)


def test_sumar_acumula_y_fecha_por_defecto_hoy(fake, como):
    c = como("nes_bugallo")
    r = c.post("/api/v1/subidas", json={"carruseles": 15, "nota": "tanda 00:00"})
    assert r.status_code == 200, r.text
    assert r.json()["dia"]["fecha"] == "2026-11-10"
    r = c.post("/api/v1/subidas", json={"videos": 6, "nota": "vídeos"})
    dia = r.json()["dia"]
    assert (dia["videos"], dia["carruseles"]) == (6, 15)
    assert dia["nota"] == "tanda 00:00 · vídeos"
    assert "nes_bugallo:2026-11" in fake.d


def test_fijar_sustituye(fake, como):
    c = como("nes_bugallo")
    c.post("/api/v1/subidas", json={"fecha": "2026-11-02", "videos": 5, "carruseles": 20})
    r = c.post("/api/v1/subidas", json={"fecha": "2026-11-02", "videos": 3, "carruseles": 18,
                                        "modo": "fijar"})
    dia = r.json()["dia"]
    assert (dia["videos"], dia["carruseles"]) == (3, 18)


def test_totales_del_mes(fake, como):
    c = como("nes_bugallo")
    c.post("/api/v1/subidas", json={"fecha": "2026-11-01", "videos": 5, "carruseles": 15})
    c.post("/api/v1/subidas", json={"fecha": "2026-11-03", "videos": 10, "carruseles": 45})
    c.post("/api/v1/subidas", json={"fecha": "2026-10-31", "videos": 1})  # otro mes
    r = c.get("/api/v1/subidas", params={"mes": "2026-11"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["fecha"] for x in d["dias"]] == ["2026-11-01", "2026-11-03"]
    t = d["totales"]
    assert (t["videos"], t["carruseles"], t["total"]) == (15, 60, 75)
    assert t["dias_con_subida"] == 2
    assert t["dias_transcurridos"] == 10  # hoy es el 10
    assert t["media_dia"] == {"videos": 1.5, "carruseles": 6.0, "total": 7.5}
    # Un mes pasado cuenta entero.
    t = c.get("/api/v1/subidas", params={"mes": "2026-10"}).json()["totales"]
    assert (t["dias_transcurridos"], t["videos"]) == (31, 1)


def test_validaciones(fake, como):
    c = como("nes_bugallo")
    assert c.post("/api/v1/subidas", json={"videos": -1}).status_code == 422
    assert c.post("/api/v1/subidas", json={"fecha": "2026-13-01", "videos": 1}).status_code == 400
    assert c.post("/api/v1/subidas", json={"videos": 1, "modo": "restar"}).status_code == 400
    assert c.get("/api/v1/subidas", params={"mes": "noviembre"}).status_code == 400


def test_permisos(fake, como):
    # Ana no tiene contador.
    c = como("ana")
    assert c.get("/api/v1/subidas").status_code == 403
    assert c.post("/api/v1/subidas", json={"videos": 1}).status_code == 403
    # Bugallo no puede mirar ni escribir el de otro.
    c = como("nes_bugallo")
    assert c.get("/api/v1/subidas", params={"usuario": "ness"}).status_code == 403
    assert c.post("/api/v1/subidas", json={"videos": 1, "usuario": "ness"}).status_code == 403
    # ness (admin) sí, en el de Bugallo, y no se mezcla con el suyo.
    c = como("ness")
    r = c.post("/api/v1/subidas", json={"carruseles": 7, "usuario": "nes_bugallo"})
    assert r.status_code == 200 and r.json()["usuario"] == "nes_bugallo"
    assert c.get("/api/v1/subidas", params={"usuario": "nes_bugallo"}).json()["totales"]["carruseles"] == 7
    assert c.get("/api/v1/subidas").json()["totales"]["carruseles"] == 0
    # Pero no en el de quien no tiene contador.
    assert c.get("/api/v1/subidas", params={"usuario": "ana"}).status_code == 400


def test_estadisticas_bugallo_si_ana_no(como, monkeypatch):
    from src.estadisticas import repo as est

    f = _FakeRedis()
    monkeypatch.setattr(est, "_redis", lambda: f)
    assert como("nes_bugallo").get("/api/v1/estadisticas").status_code == 200
    assert como("ana").get("/api/v1/estadisticas").status_code == 403


def test_bugallo_pasa_el_corte_de_rol_sin_abrirlo_a_otros_pro():
    """El middleware de `src/api/main.py`: a Bugallo se le abren Subidas y
    Estadísticas; a los demás `pro`, no."""
    from src.api import main, users

    assert users.rol_de("nes_bugallo") == users.PRO
    extra = main._PREFIJOS_POR_USUARIO["nes_bugallo"]
    assert "/api/v1/subidas" in extra and "/api/v1/estadisticas" in extra
    assert not any(p.startswith(("/api/v1/subidas", "/api/v1/estadisticas"))
                   for p in main._PREFIJOS_PRO)
    assert set(main._PREFIJOS_POR_USUARIO) == {"nes_bugallo"}


def test_mcp_registrar_y_ver_subidas_con_el_token_de_bugallo(app_client, fake):
    """Las herramientas del MCP actúan como el usuario del token."""
    pytest.importorskip("mcp")
    import json

    from src.agente_mcp import config

    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

    def rpc(metodo, params=None):
        r = app_client.post(url, headers=h, json={"jsonrpc": "2.0", "id": 1, "method": metodo,
                                                  "params": params or {}})
        assert r.status_code == 200, r.text
        return r.json()["result"]

    url = f"/api/mcp/{config.token_de('nes_bugallo')}"
    nombres = {t["name"] for t in rpc("tools/list")["tools"]}
    assert {"registrar_subidas", "ver_subidas"} <= nombres
    res = rpc("tools/call", {"name": "registrar_subidas",
                             "arguments": {"carruseles": 15, "videos": 5, "nota": "tanda 00:00"}})
    assert not res.get("isError"), res
    assert json.loads(res["content"][0]["text"])["usuario"] == "nes_bugallo"
    res = rpc("tools/call", {"name": "ver_subidas", "arguments": {"mes": "2026-11"}})
    assert json.loads(res["content"][0]["text"])["totales"]["total"] == 20
    res = rpc("tools/call", {"name": "guia", "arguments": {"menu": "subidas"}})
    assert not res.get("isError") and "registrar_subidas" in res["content"][0]["text"]
    # Bugallo no puede escribir en el de ness.
    res = rpc("tools/call", {"name": "registrar_subidas", "arguments": {"videos": 1, "usuario": "ness"}})
    assert res["isError"]
