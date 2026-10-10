from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.exceptions import register_exception_handlers
from src.api.routers.multiplataforma import router_publico
from src.multiplataforma.services import video_url


def test_firma_y_caducidad():
    tok = video_url.firmar("/tmp/v.mp4", ttl=60, ahora=1000)
    assert video_url.verificar(tok, ahora=1030) == "/tmp/v.mp4"
    assert video_url.verificar(tok, ahora=2000) is None
    cuerpo, _, firma = tok.partition(".")
    assert video_url.verificar(cuerpo + "." + "0" * len(firma), ahora=1030) is None


def test_no_firma_lo_que_no_es_video():
    import pytest

    with pytest.raises(ValueError):
        video_url.firmar("/app/.env")


def test_endpoint_publico(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTIPLATAFORMA_DRIVE_ROOT", str(tmp_path))
    f = tmp_path / "v.mp4"
    f.write_bytes(b"video")
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_publico)
    c = TestClient(app)
    tok = video_url.firmar(str(f))
    r = c.get(f"/api/v1/multiplataforma/archivo/{tok}")
    assert r.status_code == 200 and r.content == b"video"
    # El robot de Instagram hace HEAD antes de bajar la foto del carrusel
    h = c.head(f"/api/v1/multiplataforma/archivo/{tok}")
    assert h.status_code == 200 and h.headers["content-type"] == "video/mp4"
    assert r.headers["content-disposition"].startswith("inline")
    assert c.get("/api/v1/multiplataforma/archivo/basura.firma").status_code == 403
