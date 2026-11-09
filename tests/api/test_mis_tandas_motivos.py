"""GET /api/v1/mis-tandas/motivos y la herramienta `motivos_semaforo`. Sin red."""

from __future__ import annotations

import time

import pytest

from src.api.dependencies import get_web_user
from src.mis_tandas import servicio


@pytest.fixture
def con_semaforos(app_client, monkeypatch):
    datos = {
        "ness": {
            "rv|1": {"color": "rojo", "motivo": "El molde cambia entre clips", "at": time.time() - 3600},
            "largo|a|b|1|": {"color": "ambar", "motivo": "Kit de varias piezas", "at": time.time() - 90 * 86400},
            "largo|a|b|2|": {"color": "verde", "motivo": "taza lisa", "at": time.time()},
        },
        "ana": {},
    }
    monkeypatch.setattr(servicio, "semaforos", lambda u: datos.get(u, {}))
    app_client.app.dependency_overrides[get_web_user] = lambda: "ness"
    yield app_client
    app_client.app.dependency_overrides.pop(get_web_user, None)


def test_motivos_del_usuario(con_semaforos):
    r = con_semaforos.get("/api/v1/mis-tandas/motivos")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["colores"] == {"verde": 1, "ambar": 1, "rojo": 1}
    assert d["rojo"][0]["categoria"] == "cambia_entre_clips" and d["rojo"][0]["ejemplos"][0]["id"] == "rv|1"

    d = con_semaforos.get("/api/v1/mis-tandas/motivos?dias=30").json()
    assert d["colores"]["ambar"] == 0 and d["dias"] == 30

    assert con_semaforos.get("/api/v1/mis-tandas/motivos?dias=-1").status_code == 422


def test_cada_usuario_ve_solo_lo_suyo(con_semaforos):
    con_semaforos.app.dependency_overrides[get_web_user] = lambda: "ana"
    assert con_semaforos.get("/api/v1/mis-tandas/motivos").json()["revisados"] == 0
