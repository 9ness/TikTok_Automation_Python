"""Threads por OAuth: state firmado, canje del code y renovación en el tick."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.multiplataforma.models import CuentaDestino
from src.multiplataforma.repos import cuentas_repo
from src.multiplataforma.services import conectar_meta as cm


@pytest.fixture()
def red(monkeypatch):
    def responder(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth/access_token" in url:
            cuerpo = parse_qs(request.content.decode())
            assert cuerpo["code"] == ["ABC"] and cuerpo["client_secret"] == ["s" * 32]
            return httpx.Response(200, json={"access_token": "corto", "user_id": 7})
        if "th_exchange_token" in url:
            return httpx.Response(200, json={"access_token": "largo", "expires_in": 5184000})
        if "refresh_access_token" in url:
            return httpx.Response(200, json={"access_token": "renovado"})
        if "/me" in url:
            return httpx.Response(200, json={"id": "7", "username": "ama_shop_es"})
        raise AssertionError(url)

    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    monkeypatch.setattr(cm.httpx, "get", cliente.get)
    monkeypatch.setattr(cm.httpx, "post", cliente.post)
    cuentas_repo.guardar(CuentaDestino(slug="ama_shop", threads_user_id="7"))


def test_oauth_completo_guarda_token_largo(red):
    cm.guardar_app_threads("29125302800614653", "s" * 32)
    url = cm.url_autorizar("ness")
    q = parse_qs(urlparse(url).query)
    assert q["redirect_uri"] == [cm.url_retorno()] and "threads_basic" in q["scope"][0]
    r = cm.completar_oauth("ABC#_", q["state"][0])
    assert r == {"cuenta": "ama_shop", "usuario": "ama_shop_es"}
    assert cuentas_repo.get("ama_shop").tokens["threads"] == "largo"


def test_state_falso_o_caducado(red, monkeypatch):
    cm.guardar_app_threads("1", "s" * 32)
    with pytest.raises(cm.TokenInvalido):
        cm.completar_oauth("ABC", "x.y")
    state = parse_qs(urlparse(cm.url_autorizar("ness")).query)["state"][0]
    luego = time.time() + 3600
    monkeypatch.setattr(cm.time, "time", lambda: luego)
    with pytest.raises(cm.TokenInvalido):
        cm.completar_oauth("ABC", state)


def test_sin_app_no_hay_url(red):
    with pytest.raises(cm.TokenInvalido):
        cm.url_autorizar("ness")


def test_renovacion_semanal(red):
    cuentas_repo.set_tokens("ama_shop", {"threads": "viejo"})
    assert cm.renovar_tokens_threads() == {"ama_shop": "renovado"}
    assert cuentas_repo.get("ama_shop").tokens["threads"] == "renovado"
    assert cm.renovar_tokens_threads() == {}  # ya renovado esta semana


def test_estado_lista_cuentas_sin_secreto(red):
    cm.guardar_app_threads("1", "s" * 32)
    e = cm.estado_app_threads()
    assert e["configurada"] and "app_secret" not in e
    assert e["cuentas"][0]["cuenta"] == "ama_shop" and e["cuentas"][0]["conectada"] is False
