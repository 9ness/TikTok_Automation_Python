"""Calendario de campañas: qué dice la franja y el MCP según el día."""

from datetime import date

from src.cuotas import campanas


def test_lejos_no_se_ve():
    e = campanas.estado(date(2026, 8, 1))
    assert not e["visible"]
    assert e["avisos"] == []


def test_hoy_cuenta_atras_sin_aviso():
    e = campanas.estado(date(2026, 9, 30))
    assert e["visible"] and e["activa"] is None
    assert e["proxima"]["id"] == "bf_front" and e["proxima"]["dias_para"] == 42
    assert e["avisos"] == []
    assert campanas.contexto_guion(date(2026, 9, 30)) == ""


def test_aviso_dos_semanas_antes():
    e = campanas.estado(date(2026, 10, 28))
    assert len(e["avisos"]) == 1 and "Black Friday" in e["avisos"][0]
    assert "Black Friday" in campanas.contexto_guion(date(2026, 10, 28))


def test_durante_el_pico():
    e = campanas.estado(date(2026, 11, 27))
    assert e["activa"]["id"] == "bf_peak"
    assert e["proxima"]["id"] == "cyber"
    ctx = campanas.contexto_guion(date(2026, 11, 27))
    assert "Black Friday Peak" in ctx and "promoción incoherente" in ctx


def test_semanas_como_el_oficial():
    s = campanas.estado(date(2026, 11, 1))["semanas"]
    assert len(s) == 5
    assert [len(x["dias"]) for x in s] == [7, 7, 7, 7, 8]
    assert s[0]["dias"][0] == {"fecha": "2026-11-11", "dia": "Mié", "campana": "bf_front",
                               "destacado": False}
    assert s[-1]["dias"][-1]["fecha"] == "2026-12-16"


def test_se_acaba():
    e = campanas.estado(date(2026, 12, 17))
    assert e["terminado"] and not e["visible"]
    assert e["activa"] is None and e["proxima"] is None
