"""Editor rápido: títulos gancho, original y estadísticas del usuario."""
from __future__ import annotations

import json
import time
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_queue
from src.api.exceptions import APIError
from src.api.routers.editor_auto import rapido as r
from src.api.web_ticket import make_ticket
from src.editor_auto.api import claude_client
from src.editor_auto.rapido import extras as ex
from src.editor_auto.rapido import servicio as svc
from tests.tiktok_shop.conftest import FakeRedis

BASE = "/api/v1/editor-auto/rapido"
EMAIL = "ana@example.com"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_UPLOAD_SECRET", "x" * 40)
    monkeypatch.setenv("EDITOR_RAPIDO_DIR", str(tmp_path / "datos"))
    redis = FakeRedis()
    redis.prefix = "editor_auto:"
    monkeypatch.setattr(svc, "get_editor_redis", lambda: redis)
    app = FastAPI()
    app.include_router(r.router)

    @app.exception_handler(APIError)
    async def _h(request, exc):  # noqa: ANN001
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": exc.message if hasattr(exc, "message") else str(exc)}, status_code=exc.status_code)

    app.dependency_overrides[get_queue] = lambda: None
    hdr = {"Authorization": "Bearer " + make_ticket(EMAIL, "", scope="rapido")}
    return TestClient(app), hdr


def _ficha(estado="listo", **kw):
    f = svc.nueva_ficha(EMAIL, "clip.mp4", 100.0, 10)
    f.update(estado=estado, **kw)
    svc.guardar_ficha(f)
    return f


def _palabras(vid):
    svc.ruta_palabras(vid).write_text(json.dumps(
        [{"word": "mira", "start": 0, "end": 1}, {"word": "esto", "start": 1, "end": 2}]), encoding="utf-8")


def _claude(monkeypatch, titulos=None, llamadas=None):
    monkeypatch.setattr(claude_client, "activo", lambda: True)

    def fake(**kw):
        if llamadas is not None:
            llamadas.append(kw)
        return {"titulos": titulos if titulos is not None else
                [{"texto": "x" * 90, "tipo": "pov"}, {"texto": "¿Sabías esto?", "tipo": "raro"}]}
    monkeypatch.setattr(claude_client, "analyze_transcript_json", fake)


def test_titulos_ok_guarda_y_limita(ctx, monkeypatch):
    c, hdr = ctx
    f = _ficha()
    _palabras(f["id"])
    llamadas = []
    _claude(monkeypatch, llamadas=llamadas)
    j = c.post(f"{BASE}/videos/{f['id']}/titulos", headers=hdr).json()
    assert j["restantes"] == 2
    assert j["titulos"][0] == {"texto": "x" * 60, "tipo": "pov"}
    assert j["titulos"][1]["tipo"] == "curiosidad"
    assert llamadas[0]["modelo_forzado"] == ex.MODELO_TITULOS == "claude-haiku-5-5"
    assert svc.cargar_ficha(f["id"])["titulos"] == j["titulos"]
    for esperado in (1, 0):
        assert c.post(f"{BASE}/videos/{f['id']}/titulos", headers=hdr).json()["restantes"] == esperado
    assert c.post(f"{BASE}/videos/{f['id']}/titulos", headers=hdr).status_code == 429
    assert len(llamadas) == 3


def test_titulos_sin_transcripcion_409_y_ajeno_404(ctx, monkeypatch):
    c, hdr = ctx
    _claude(monkeypatch)
    f = _ficha()
    assert c.post(f"{BASE}/videos/{f['id']}/titulos", headers=hdr).status_code == 409
    assert svc.cargar_ficha(f["id"]).get("titulos_n", 0) == 0
    otro = {"Authorization": "Bearer " + make_ticket("otro@x.com", "", scope="rapido")}
    assert c.post(f"{BASE}/videos/{f['id']}/titulos", headers=otro).status_code == 404
    assert c.post(f"{BASE}/videos/{f['id']}/titulos").status_code == 401


def test_titulos_fallo_ia_502_no_cuenta(ctx, monkeypatch):
    c, hdr = ctx
    f = _ficha()
    _palabras(f["id"])
    monkeypatch.setattr(claude_client, "activo", lambda: True)
    monkeypatch.setattr(claude_client, "analyze_transcript_json", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert c.post(f"{BASE}/videos/{f['id']}/titulos", headers=hdr).status_code == 502
    assert svc.cargar_ficha(f["id"]).get("titulos_n", 0) == 0


def test_original_sirve_y_404(ctx):
    c, hdr = ctx
    f = _ficha()
    assert c.get(f"{BASE}/videos/{f['id']}/original", headers=hdr).status_code == 404
    (svc.carpeta(f["id"]) / "original.mp4").write_bytes(b"0123456789")
    resp = c.get(f"{BASE}/videos/{f['id']}/original", headers=hdr)
    assert resp.status_code == 200 and resp.content == b"0123456789"
    assert resp.headers["content-type"] == "video/mp4"
    parcial = c.get(f"{BASE}/videos/{f['id']}/original", headers={**hdr, "Range": "bytes=0-3"})
    assert parcial.status_code == 206 and parcial.content == b"0123"
    assert c.get(f"{BASE}/videos/{f['id']}/original?t={hdr['Authorization'][7:]}").status_code == 200


def test_estadisticas(ctx):
    c, hdr = ctx
    assert c.get(f"{BASE}/estadisticas", headers=hdr).json() == {
        "videos_editados": 0, "segundos_quitados": 0.0, "racha_dias": 0, "dias_activos_30": 0,
        "media_pct_mas_corto": 0.0}
    hoy = svc.datetime.now(svc.TZ).date()
    d = lambda n: (hoy - timedelta(days=n)).isoformat()  # noqa: E731
    svc.get_editor_redis().set_json(svc._k_hist(EMAIL), {"dias": {
        d(0): {"videos": 2}, d(1): {"videos": 1}, d(2): {"videos": 1}, d(4): {"videos": 3}, d(40): {"videos": 1}}})
    _ficha(duracion_final_s=80.0)   # sin cortes.json: quitó 20 s de 100 (20 %)
    _ficha(duracion_final_s=60.0)   # 40 s (40 %)
    _ficha(estado="cola")           # no cuenta
    j = c.get(f"{BASE}/estadisticas", headers=hdr).json()
    assert j == {"videos_editados": 8, "segundos_quitados": 60.0, "racha_dias": 3, "dias_activos_30": 4,
                 "media_pct_mas_corto": 30.0}


def test_estadisticas_racha_desde_ayer(ctx):
    c, hdr = ctx
    hoy = svc.datetime.now(svc.TZ).date()
    svc.get_editor_redis().set_json(svc._k_hist(EMAIL), {"dias": {
        (hoy - timedelta(days=1)).isoformat(): {"videos": 1}, (hoy - timedelta(days=2)).isoformat(): {"videos": 1}}})
    assert c.get(f"{BASE}/estadisticas", headers=hdr).json()["racha_dias"] == 2
