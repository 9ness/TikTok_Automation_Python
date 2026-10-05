"""Semáforo de revisión de «Mis tandas»."""

from __future__ import annotations

import pytest

from src.mis_tandas import servicio
from tests.mis_tandas.test_servicio import FakeRedis


@pytest.fixture()
def entorno(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    filas = {"largo|a|b|1|": {"id": "largo|a|b|1|", "video_listo_at": 100.0, "puede_rehacer": True, "rehacer": False}}
    monkeypatch.setattr(servicio, "_fila_de", lambda u, i: filas[i])
    marcados = []
    monkeypatch.setattr(servicio, "marcar", lambda u, i, **kw: marcados.append((i, kw)) or {"ok": True})
    return r, filas, marcados


def test_guarda_y_vale_solo_para_ese_montaje(entorno):
    r, filas, _ = entorno
    out = servicio.poner_semaforo("ness", "largo|a|b|1|", "verde", "producto sencillo", "agente")
    assert out["semaforo"]["color"] == "verde"
    s = servicio.semaforos("ness")["largo|a|b|1|"]
    assert servicio._semaforo_vigente(s, filas["largo|a|b|1|"])["motivo"] == "producto sencillo"
    # se vuelve a montar: el color viejo ya no vale
    assert servicio._semaforo_vigente(s, {"video_listo_at": 200.0}) is None


def test_rojo_marca_rehacer_y_ambar_no(entorno):
    _, _, marcados = entorno
    servicio.poner_semaforo("ness", "largo|a|b|1|", "ámbar", "producto complejo")
    assert marcados == []
    servicio.poner_semaforo("ness", "largo|a|b|1|", "rojo", "envase distinto entre clips")
    assert marcados and marcados[0][1]["rehacer"] is True and "envase" in marcados[0][1]["rehacer_nota"]


def test_quitar_y_color_invalido(entorno):
    servicio.poner_semaforo("ness", "largo|a|b|1|", "verde")
    servicio.poner_semaforo("ness", "largo|a|b|1|", "")
    assert servicio.semaforos("ness") == {}
    with pytest.raises(servicio.ErrorTanda):
        servicio.poner_semaforo("ness", "largo|a|b|1|", "azul")
