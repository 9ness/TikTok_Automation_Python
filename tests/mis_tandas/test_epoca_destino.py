"""Época por vídeo y cuentas que en TikTok solo suben hablados (oct 2026)."""

from __future__ import annotations

import pytest

from src.mis_tandas import config, servicio
from tests.mis_tandas.test_servicio import FakeRedis


def _f(i, nicho="mm", modo="mm_espejo", label="Espejo", uploaded=False):
    return {"id": i, "nicho": nicho, "modo": modo, "modo_label": label, "uploaded": uploaded}


def test_habla():
    assert servicio.habla(_f("a", nicho="alea", modo="tienda_colores"))
    assert servicio.habla(_f("b", nicho="largo", modo="dolor"))
    assert servicio.habla(_f("c", modo="mm_habla_calle_1"))
    assert servicio.habla(_f("d", modo="mm_zapatillas_pov20"))
    assert servicio.habla(_f("e", modo="mm_bolso_coche20"))
    assert not servicio.habla(_f("f", modo="mm_espejo"))
    assert not servicio.habla(_f("g", modo="mm_bolso_1"))


def test_epoca(monkeypatch):
    r = FakeRedis()
    filas = {"x": _f("x", label="🍂 Vintage Botas 1"), "y": _f("y")}
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    monkeypatch.setattr(servicio, "_fila_de", lambda u, i: filas[i])
    assert servicio._epoca_defecto(filas["x"]) == "otono"
    assert servicio._epoca_defecto(filas["y"]) == "neutro"
    assert servicio.poner_epoca("ana", "y", "Navidad")["epoca"] == "navidad"
    assert servicio.epocas("ana") == {"y": "navidad"}
    assert servicio.poner_epoca("ana", "y", "")["epoca"] == "neutro"
    with pytest.raises(servicio.ErrorTanda):
        servicio.poner_epoca("ana", "y", "verano")


def test_por_tanda():
    assert config.por_tanda("ana") == 6
    assert config.por_tanda("ness") == config.POR_TANDA
