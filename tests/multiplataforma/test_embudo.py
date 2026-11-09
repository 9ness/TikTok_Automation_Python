"""Embudo de la página de la bio: visitas y clics por producto (solo contadores)."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.exceptions import register_exception_handlers
from src.api.routers.multiplataforma import router_publico
from src.multiplataforma import config
from src.multiplataforma.repos import enlaces_repo
from src.multiplataforma.services import embudo, informe, tandas

PERSONA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Instagram 350.0"
DIA = dt.datetime(2026, 11, 9, 12, 0).timestamp()


@pytest.fixture()
def pagina(monkeypatch):
    """La página pública de `ama_shop` con dos productos; otra cuenta no existe."""
    def falsa(slug):
        if slug != "ama_shop":
            raise tandas.ErrorTandas("No existe", status=404)
        return {"productos": [{"id": "aaaa1111"}, {"id": "bbbb2222"}]}

    monkeypatch.setattr(tandas, "links_publicos", falsa)


def test_cuenta_visitas_y_clics_por_producto(pagina, redis):
    assert embudo.registrar("ama_shop", "visita", user_agent=PERSONA, ahora=DIA)
    assert embudo.registrar("ama_shop", "visita", user_agent=PERSONA, ahora=DIA)
    assert embudo.registrar("ama_shop", "clic", "aaaa1111", user_agent=PERSONA, ahora=DIA)
    assert embudo.registrar("ama_shop", "clic", "bbbb2222", user_agent=PERSONA, ahora=DIA + 86400)
    assert embudo.registrar("ama_shop", "clic", "bbbb2222", user_agent=PERSONA, ahora=DIA + 86400)
    d = embudo.leer("ama_shop", DIA - 86400, DIA + 86400)
    assert (d["visitas"], d["clics"]) == (2, 3)
    assert d["productos"] == {"aaaa1111": 1, "bbbb2222": 2}
    assert d["por_dia"] == {"2026-11-09": {"visitas": 2, "clics": 1}, "2026-11-10": {"visitas": 0, "clics": 2}}
    # Fuera de la ventana no entra.
    assert embudo.leer("ama_shop", DIA, DIA + 86400)["visitas"] == 0


def test_no_cuenta_bots_ni_cosas_raras(pagina, redis):
    assert not embudo.registrar("ama_shop", "visita", user_agent="facebookexternalhit/1.1", ahora=DIA)
    assert not embudo.registrar("ama_shop", "visita", user_agent="", ahora=DIA)
    assert not embudo.registrar("ama_shop", "compra", user_agent=PERSONA, ahora=DIA)
    assert not embudo.registrar("ama_shop", "clic", "no-esta", user_agent=PERSONA, ahora=DIA)
    assert not embudo.registrar("otra", "visita", user_agent=PERSONA, ahora=DIA)
    assert not embudo.registrar("../x", "visita", user_agent=PERSONA, ahora=DIA)
    assert embudo.leer("ama_shop", DIA - 86400, DIA) == {"visitas": 0, "clics": 0, "por_dia": {}, "productos": {}}


def test_tope_por_minuto(pagina, redis, monkeypatch):
    monkeypatch.setattr(config, "EMBUDO_TOPE_MINUTO", 3)
    hechos = [embudo.registrar("ama_shop", "visita", user_agent=PERSONA, ahora=DIA) for _ in range(5)]
    assert hechos == [True, True, True, False, False]
    assert embudo.registrar("ama_shop", "visita", user_agent=PERSONA, ahora=DIA + 60)  # otro minuto


def test_cambio_de_mes_y_resumen_con_titulos(pagina, redis):
    fin_mes = dt.datetime(2026, 11, 30, 23, 0).timestamp()
    embudo.registrar("ama_shop", "clic", "aaaa1111", user_agent=PERSONA, ahora=fin_mes)
    embudo.registrar("ama_shop", "clic", "bbbb2222", user_agent=PERSONA, ahora=fin_mes + 7200)  # 1 de diciembre
    embudo.registrar("ama_shop", "clic", "bbbb2222", user_agent=PERSONA, ahora=fin_mes + 7200)
    enlaces_repo.guardar("ama_shop", "bbbb2222", {"enlace": "https://es.shein.com/x", "titulo": "Bolso rojo"})
    r = embudo.resumen("ama_shop", fin_mes - 86400, fin_mes + 7200)
    assert r["clics"] == 3
    assert r["productos"] == [{"id": "bbbb2222", "titulo": "Bolso rojo", "clics": 2}, {"id": "aaaa1111", "titulo": "", "clics": 1}]


def test_si_redis_falla_no_rompe(pagina, redis, monkeypatch):
    monkeypatch.setattr(redis, "hincrby", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caído")))
    assert embudo.registrar("ama_shop", "visita", user_agent=PERSONA, ahora=DIA) is False


def test_endpoint_siempre_204(pagina, redis):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_publico)
    c = TestClient(app)
    url = "/api/v1/multiplataforma/links/ama_shop/evento"
    cab = {"user-agent": PERSONA, "content-type": "text/plain"}
    assert c.post(url, content='{"tipo": "visita"}', headers=cab).status_code == 204
    assert c.post(url, content='{"tipo": "clic", "producto": "aaaa1111"}', headers=cab).status_code == 204
    assert c.post(url, content="no es json", headers=cab).status_code == 204
    assert c.post(url, content="[1, 2]", headers=cab).status_code == 204
    assert c.post("/api/v1/multiplataforma/links/otra/evento", content='{"tipo": "visita"}', headers=cab).status_code == 204
    ahora = dt.datetime.now().timestamp()
    d = embudo.leer("ama_shop", ahora - 86400, ahora)
    assert (d["visitas"], d["clics"]) == (1, 1)


def test_informe_saca_la_pagina_de_la_bio():
    ultimo = {"cuentas": {
        "ama_shop": {"embudo": {"visitas": 40, "clics": 10, "productos": [{"id": "bbbb2222", "titulo": "Bolso rojo", "clics": 7}]}},
        "viva_shop": {"embudo": {"visitas": 0, "clics": 0, "productos": []}},
        "viva_salud": {"embudo": None},
    }}
    texto = "\n".join(informe.seccion_embudo(ultimo))
    assert "| ama_shop | 40 | 10 | 25 % |" in texto
    assert "| viva_shop | 0 | 0 | — |" in texto
    assert "viva_salud" not in texto
    assert "| ama_shop | 7 | Bolso rojo |" in texto
    assert informe.seccion_embudo({"cuentas": {"ama_shop": {}}}) == []
