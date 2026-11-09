"""Tests de los endpoints WhatsApp del Editor Auto, el proxy al bot y el aviso."""

from __future__ import annotations

import httpx
import pytest

from src.editor_auto.services import whatsapp_notify as notify
from src.editor_auto.services import whatsapp_vinculo as vinculo

ENVS = ("EDITOR_WHATSAPP_BOT_URL", "EDITOR_WHATSAPP_BOT_TOKEN", "EDITOR_WHATSAPP_AVISOS")


@pytest.fixture(autouse=True)
def _limpia_env(monkeypatch):
    for k in ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("API_KEY", raising=False)


def _con_bot(monkeypatch):
    monkeypatch.setenv("EDITOR_WHATSAPP_BOT_URL", "http://bot.test:9000/")
    monkeypatch.setenv("EDITOR_WHATSAPP_BOT_TOKEN", "TOK-SECRETO")


def test_endpoints_vinculo(app_client, monkeypatch):
    monkeypatch.setattr(vinculo, "pedir_codigo", lambda t, e: {"ok": True, "t": t, "e": e})
    monkeypatch.setattr(vinculo, "confirmar_codigo", lambda t, c: {"ok": False, "motivo": "codigo", "c": c})
    monkeypatch.setattr(vinculo, "desvincular", lambda t: True)
    monkeypatch.setattr(vinculo, "resumen_cliente", lambda t, queue=None: {"vinculado": False, "t": t})
    c = app_client
    assert c.post("/api/v1/editor-auto/whatsapp/vincular/pedir",
                  json={"telefono": "612", "email": "a@b.c"}).json() == {"ok": True, "t": "612", "e": "a@b.c"}
    assert c.post("/api/v1/editor-auto/whatsapp/vincular/confirmar",
                  json={"telefono": "612", "codigo": "1"}).json()["motivo"] == "codigo"
    assert c.post("/api/v1/editor-auto/whatsapp/desvincular", json={"telefono": "612"}).json() == {"ok": True}
    assert c.get("/api/v1/editor-auto/whatsapp/cliente?telefono=612").json() == {"vinculado": False, "t": "612"}


def test_auth_exigida(app_client, monkeypatch):
    monkeypatch.setenv("API_KEY", "k")
    from src.api.config import get_settings
    get_settings.cache_clear()
    try:
        r = app_client.get("/api/v1/editor-auto/whatsapp/bot/diagnostico")
        assert r.status_code == 401
        r = app_client.get("/api/v1/editor-auto/whatsapp/bot/diagnostico", headers={"X-API-Key": "k"})
        assert r.status_code == 200
    finally:
        get_settings.cache_clear()


def test_coste(app_client):
    r = app_client.post("/api/v1/editor-auto/whatsapp/coste", json={
        "modelo": "claude-haiku-5-5", "input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["usd"] == pytest.approx(0.60)


def test_proxy_sin_configurar(app_client):
    j = app_client.get("/api/v1/editor-auto/whatsapp/bot/diagnostico").json()
    assert j == {"configurado": False, "faltan": ["EDITOR_WHATSAPP_BOT_URL", "EDITOR_WHATSAPP_BOT_TOKEN"]}


def test_proxy_ok_y_reenvio(app_client, monkeypatch):
    _con_bot(monkeypatch)
    vistos = []

    def falso(metodo, url, **kw):
        vistos.append((metodo, url, kw))
        return httpx.Response(200, json={"hola": 1}, request=httpx.Request(metodo, url))

    monkeypatch.setattr(httpx, "request", falso)
    base = "/api/v1/editor-auto/whatsapp/bot"
    j = app_client.get(f"{base}/conversaciones?limite=5").json()
    assert j == {"configurado": True, "alcanzable": True, "datos": {"hola": 1}}
    assert vistos[0][:2] == ("GET", "http://bot.test:9000/admin/conversaciones")
    assert vistos[0][2]["params"] == {"limite": 5}
    assert vistos[0][2]["headers"]["Authorization"] == "Bearer TOK-SECRETO"
    app_client.get(f"{base}/conversacion?wa_id=34600")
    assert vistos[1][1].endswith("/admin/conversacion") and vistos[1][2]["params"] == {"wa_id": "34600"}
    for n in ("plantillas", "suscribir", "prueba", "pausa", "reanudar"):
        app_client.post(f"{base}/{n}", json={"x": n})
        assert vistos[-1][:2] == ("POST", f"http://bot.test:9000/admin/{n}")
        assert vistos[-1][2]["json"] == {"x": n}
    assert vistos[-1][2]["timeout"] == 20.0


def test_proxy_bot_caido_y_error_http(app_client, monkeypatch):
    _con_bot(monkeypatch)

    def caido(metodo, url, **kw):
        raise httpx.ConnectError("no conecta a http://bot.test Bearer TOK-SECRETO")

    monkeypatch.setattr(httpx, "request", caido)
    r = app_client.get("/api/v1/editor-auto/whatsapp/bot/diagnostico")
    assert r.json() == {"configurado": True, "alcanzable": False, "error": "ConnectError"}
    assert "TOK-SECRETO" not in r.text

    monkeypatch.setattr(httpx, "request", lambda m, u, **kw: httpx.Response(
        500, json={}, request=httpx.Request(m, u)))
    j = app_client.get("/api/v1/editor-auto/whatsapp/bot/diagnostico").json()
    assert j["alcanzable"] is False and "HTTPStatusError" in j["error"]


def test_proxy_sin_rutas_arbitrarias(app_client):
    assert app_client.get("/api/v1/editor-auto/whatsapp/bot/otra").status_code == 404


# ─────────── aviso al bot ───────────

def test_aviso_apagado(monkeypatch):
    llamadas = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: llamadas.append(a))
    assert notify.avisar_bot("x", {}) is False            # sin AVISOS=1
    monkeypatch.setenv("EDITOR_WHATSAPP_AVISOS", "1")
    assert notify.avisar_bot("x", {}) is False            # sin url/token
    _con_bot(monkeypatch)
    monkeypatch.setattr(vinculo, "telefono_de", lambda e, **k: "")
    assert notify.avisar_videos_listos(email="a@b.c", nombre="A", dia="2026-11-09", listos=2) is False
    assert llamadas == []


def test_aviso_encendido(monkeypatch):
    _con_bot(monkeypatch)
    monkeypatch.setenv("EDITOR_WHATSAPP_AVISOS", "1")
    monkeypatch.setattr(vinculo, "telefono_de", lambda e, **k: "34612345678")
    vistos = []

    def falso(url, **kw):
        vistos.append((url, kw))
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", falso)
    assert notify.avisar_videos_listos(email="a@b.c", nombre="Ana", dia="2026-11-09",
                                       listos=2, caduca="2026-11-16") is True
    url, kw = vistos[0]
    assert url == "http://bot.test:9000/interno/aviso"
    assert kw["headers"]["Authorization"] == "Bearer TOK-SECRETO" and kw["timeout"] == 5.0
    assert kw["json"] == {"evento": "videos_listos", "telefono": "34612345678", "nombre": "Ana",
                          "dia": "2026-11-09", "listos": 2, "caduca": "2026-11-16"}


def test_aviso_nunca_lanza(monkeypatch):
    _con_bot(monkeypatch)
    monkeypatch.setenv("EDITOR_WHATSAPP_AVISOS", "1")
    monkeypatch.setattr(vinculo, "telefono_de", lambda e, **k: "346")

    def boom(*a, **k):
        raise httpx.ConnectError("x")

    monkeypatch.setattr(httpx, "post", boom)
    assert notify.avisar_videos_listos(email="a@b.c", nombre="A", dia="d", listos=1) is False
